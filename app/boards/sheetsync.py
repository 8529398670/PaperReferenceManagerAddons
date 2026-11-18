"""Lists mirrored to Google Sheets: one spreadsheet per list, made the first
time the list is switched on. Ported from the old prma src/server/sheetsync.py.

Each list has its own switch and mode, set from its list menu:

  off       not mirrored
  one-way   the list is pushed to the sheet push_delay seconds after a change
            (a burst of edits is one push)
  two-way   the same, and the sheet is read back every poll_seconds and
            before every push, so a push never writes over something typed
            there since the last read. What changed in the sheet -- against
            the grid as last pushed, never against the list
            (app/boards/sheetmirror.py) -- runs on the list as ops
            by "Google Sheet": one new version, in the history, merged with
            whatever the list did meanwhile.

A read-back is refused (and nothing applied) when a fixed header or the Key
column is gone, or more than max_remove rows vanished at once; it waits while
the list is view-only.

Each list's mirror -- mode, spreadsheet, the grid last pushed, the last push
and pull and error -- is a record in db.BUCKET_SHEET_MIRRORS by slug, moved
along when the list is renamed.

Everything that talks to Google runs on one thread, one list at a time; the
request threads only flip settings and say "this list changed" (BoardService
tells every listener). Known gap, as before: two-way reads then writes a
second or so apart, and a cell typed in that second is overwritten -- the
list's history has every version.
"""
from __future__ import annotations

import copy
import threading
import time
import traceback
from typing import Any, Callable

from app.boards import board, sheetmirror
from app.boards import store as boards
from app.boards.gsheets import Client, GoogleError
from app.core import db
from app.models import to_iso, utc_now

MODES = ("off", "one-way", "two-way")
TAB = "List"
BY = "Google Sheet"


def _now() -> str:
    return to_iso(utc_now())


def canon(rows: list[list[Any]] | None) -> list[list[str]]:
    """A grid as a read-back of it gives it: text cells, no trailing blanks."""
    out = []
    for row in rows or []:
        cells = [sheetmirror.norm(c) for c in row]
        while cells and cells[-1] == "":
            cells.pop()
        out.append(cells)
    while out and not out[-1]:
        out.pop()
    return out


class SheetSync:
    def __init__(self, service: Any, settings: Callable[[], Any], client: Client | None = None) -> None:
        """service is the BoardService (store, catalogue, ctx, changed,
        mirror); settings() is config.yaml's google_sheets section."""
        self.service = service
        self.store: db.Store = service.store
        self.settings = settings
        self.client = client or Client(settings)
        self._cv = threading.Condition()
        self._due: dict[str, float] = {}
        self._busy = ""
        self._polled = 0.0
        self._stop = False
        self._thread: threading.Thread | None = None
        self.clock: Callable[[], float] = time.time

    # -- state -----------------------------------------------------------------------

    def available(self) -> bool:
        cfg = self.settings()
        return bool(cfg.enabled and cfg.client_id and cfg.refresh_token)

    def state(self, slug: str) -> dict[str, Any]:
        return self.store.get(db.BUCKET_SHEET_MIRRORS, slug) or {"mode": "off"}

    def _note(self, slug: str, **changes: Any) -> None:
        """Merge results into a list's record: only these fields, so a switch
        flipped on the page meanwhile survives."""
        with self.store.transaction() as tx:
            record = tx.get(db.BUCKET_SHEET_MIRRORS, slug) or {"mode": "off"}
            for name, value in changes.items():
                if value is None:
                    record.pop(name, None)
                else:
                    record[name] = value
            tx.put(db.BUCKET_SHEET_MIRRORS, slug, record)

    def status(self, slug: str) -> dict[str, Any]:
        record = self.state(slug)
        sid = record.get("spreadsheet_id") or ""
        cfg = self.settings()
        with self._cv:
            pending = slug in self._due or self._busy == slug
        return {
            "available": self.available(), "mode": record.get("mode", "off"), "spreadsheet_id": sid,
            "url": f"https://docs.google.com/spreadsheets/d/{sid}" if sid else "",
            "last_push": record.get("last_push") or "", "last_pull": record.get("last_pull") or "",
            "error": record.get("error") or "", "refused": bool(record.get("refused")), "note": record.get("note") or "",
            "pending": pending, "poll_seconds": cfg.poll_seconds, "default_mode": cfg.default_mode,
        }

    def configure(self, slug: str, mode: str | None = None, sync_now: bool = False, overwrite: bool = False) -> dict[str, Any]:
        """The list menu's switch. ValueError for a mode that is not one."""
        if mode is not None and mode not in MODES:
            raise ValueError("mode must be off, one-way or two-way")
        record = self.state(slug)
        changes: dict[str, Any] = {}
        if mode is not None and mode != record.get("mode"):
            changes.update(mode=mode, error=None, refused=None, note=None)
            if mode == "two-way":
                # A read-back starts from what the sheet holds now: edits
                # made there while one-way were never meant for the list.
                changes["base"] = None
        if overwrite:
            changes["force"] = True
        if changes:
            self._note(slug, **changes)
        on = (mode or record.get("mode", "off")) != "off"
        with self._cv:
            if on and (changes or sync_now):
                self._due[slug] = 0
            elif not on:
                self._due.pop(slug, None)
            self._cv.notify()
        return self.status(slug)

    # -- what the boards say ------------------------------------------------------------

    def heard(self, data: dict[str, Any]) -> None:
        """BoardService.changed: a list moved, was renamed or deleted."""
        slug = data.get("slug") or ""
        old = data.get("renamed_from")
        if old and old != slug:
            record = self.store.get(db.BUCKET_SHEET_MIRRORS, old)
            if record is not None:
                record["retitle"] = True
                with self.store.transaction() as tx:
                    tx.put(db.BUCKET_SHEET_MIRRORS, slug, record)
                    tx.delete(db.BUCKET_SHEET_MIRRORS, old)
                with self._cv:
                    self._due.pop(old, None)
                    self._due[slug] = 0
                    self._cv.notify()
            return
        if data.get("deleted"):
            with self._cv:
                self._due.pop(slug, None)
            return
        if (data.get("by") == BY and slug == self._busy) or self.state(slug).get("mode", "off") == "off":
            # The list's own read-back: the round under way pushes it.
            return
        with self._cv:
            if slug not in self._due:
                self._due[slug] = self.clock() + float(self.settings().push_delay)
                self._cv.notify()

    # -- the worker -----------------------------------------------------------------------

    def mirrored(self) -> list[str]:
        return [str(slug) for slug, record in self.store.all(db.BUCKET_SHEET_MIRRORS) if record.get("mode", "off") != "off"]

    def start(self) -> None:
        self._stop = False
        with self._cv:
            for slug in self.mirrored():
                # Catch up with edits made while the server was stopped.
                self._due[slug] = self.clock() + 3
        self._thread = threading.Thread(target=self._loop, name="sheet-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def due_jobs(self) -> list[tuple[str, bool]]:
        """(slug, push) for each list to sync now, and the two-way lists to
        read back when the poll is due. Clears what it hands out."""
        now = self.clock()
        cfg = self.settings()
        due = [slug for slug, at in self._due.items() if at <= now]
        for slug in due:
            self._due.pop(slug, None)
        jobs = [(slug, True) for slug in due]
        if now >= self._polled + float(cfg.poll_seconds):
            self._polled = now
            for slug in self.mirrored():
                if slug not in due and self.state(slug).get("mode") == "two-way":
                    jobs.append((slug, False))
        return jobs

    def _loop(self) -> None:
        while True:
            with self._cv:
                if self._stop:
                    return
                if not self.available():
                    self._cv.wait(timeout=10)
                    continue
                jobs = self.due_jobs()
                if not jobs:
                    upcoming = min([self._polled + float(self.settings().poll_seconds)] + list(self._due.values()))
                    self._cv.wait(timeout=max(0.2, upcoming - self.clock()))
                    continue
            for slug, push in jobs:
                if self._stop:
                    return
                self.run(slug, push)

    def run(self, slug: str, push: bool) -> None:
        """One round for one list, its failure noted on the list."""
        with self._cv:
            self._busy = slug
        try:
            self.sync(slug, push)
        except GoogleError as error:
            self._note(slug, error=str(error))
        except Exception as error:  # noqa: BLE001 -- one list's failure never stops the others
            traceback.print_exc()
            self._note(slug, error=f"{type(error).__name__}: {error}")
        finally:
            with self._cv:
                self._busy = ""

    def _title(self, record: dict[str, Any]) -> str:
        return f"{self.settings().title_prefix}{record.get('name') or record['slug']}"

    def _format(self, sid: str, gid: int) -> None:
        """Header bold and frozen; Key hidden and warning-protected."""
        self.client.batch(sid, [
            {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}},
            {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                                           "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
            {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
                                           "properties": {"pixelSize": 420}, "fields": "pixelSize"}},
            {"addProtectedRange": {"protectedRange": {"range": {"sheetId": gid, "startColumnIndex": 0, "endColumnIndex": 1},
                                                      "warningOnly": True,
                                                      "description": "Key matches each row to the list -- leave it as it is"}}},
        ])

    def _sheet(self, slug: str, record: dict[str, Any], mirror: dict[str, Any]) -> tuple[str, int, dict[str, Any]] | None:
        """The list's spreadsheet and tab, made if it has none. None when the
        spreadsheet was deleted (the mirror is switched off)."""
        cfg = self.settings()
        sid, gid = mirror.get("spreadsheet_id"), mirror.get("gid")
        if not sid:
            sid, gid = self.client.create(self._title(record), TAB)
            self._format(sid, gid)
            for email in cfg.share_with or []:
                try:
                    self.client.share(sid, email)
                except GoogleError as error:
                    print(f"[sheets] sharing with {email} failed ({error})", flush=True)
            if cfg.folder_id:
                try:
                    self.client.move(sid, cfg.folder_id)
                except GoogleError as error:
                    print(f"[sheets] moving into the folder failed ({error})", flush=True)
            self._note(slug, spreadsheet_id=sid, gid=gid, base=None)
            mirror.update(spreadsheet_id=sid, gid=gid)
            mirror.pop("base", None)
        try:
            tabs = self.client.tabs(sid)
        except GoogleError as error:
            if error.status in (403, 404):
                self._note(slug, mode="off", spreadsheet_id=None, gid=None, base=None,
                           error="the spreadsheet is gone (or no longer shared) -- switch the mirror back on to make a new one")
                return None
            raise
        if gid not in tabs:
            gid = next(iter(tabs))
            self._format(sid, gid)
            self._note(slug, gid=gid, base=None)
            mirror.pop("base", None)
        if mirror.get("retitle"):
            self.client.batch(sid, [{"updateSpreadsheetProperties": {"properties": {"title": self._title(record)}, "fields": "title"}}])
            self._note(slug, retitle=None)
        return sid, gid, tabs[gid]

    def _meta(self, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Blank titles, years and DOIs filled from the library, as the page does."""
        out = {}
        for item in doc.get("items") or []:
            paper = self.service.catalogue.get(item["key"])
            if paper is not None:
                out[item["key"]] = {"title": paper.record.get("title"), "year": paper.record.get("year"), "doi": paper.record.get("doi")}
        return out

    def apply_sheet(self, slug: str, ops: list[dict[str, Any]]) -> tuple[int, list[str]]:
        """A read-back's ops on the list, each on its own (one failing does not
        stop the rest), as one new version. -> (applied, errors)."""
        ctx = self.service.ctx()
        with self.store.transaction() as tx:
            record = tx.get(db.BUCKET_BOARDS, slug)
            if record is None or record.get("deleted"):
                return 0, ["the list is gone"]
            before = record["doc"]
            doc = copy.deepcopy(before)
            applied, errors = sheetmirror.apply(doc, ctx, ops)
            doc = board.normalize(doc)
            if not applied or doc == before:
                return applied, errors
            rev = int(record.get("rev", 0))
            boards.keep_version(tx, record)
            record.update(doc=doc, rev=rev + 1, updated_at=_now(), updated_by=BY)
            tx.put(db.BUCKET_BOARDS, slug, record)
        self.service.changed(slug, rev + 1, BY)
        self.service.mirror(slug, before, doc, BY)
        return applied, errors

    def sync(self, slug: str, push: bool) -> None:
        """Read back (two-way), then push when asked or when the read-back
        changed the list."""
        mirror = copy.deepcopy(self.state(slug))
        if mirror.get("mode", "off") == "off":
            return
        record = boards.get_board(self.store, slug)
        if record is None or record.get("deleted"):
            return
        found = self._sheet(slug, record, mirror)
        if found is None:
            return
        sid, gid, tab = found
        mirror = copy.deepcopy(self.state(slug))
        force = mirror.get("force")
        base = mirror.get("base")
        message = None
        pulled = False
        if force:
            self._note(slug, force=None)
        if mirror.get("mode") == "two-way" and base and not force:
            rows = self.client.read(sid, tab["title"])
            if canon(rows) != canon(base["rows"]):
                try:
                    ops = sheetmirror.diff(base, rows, int(self.settings().max_remove))
                except sheetmirror.Refused as error:
                    self._note(slug, error=f"Sheet edits not read back: {error}", refused=True)
                    return
                if record.get("locked"):
                    self._note(slug, note="Sheet edits are waiting: this list is view-only")
                    return
                errors: list[str] = []
                if ops:
                    _, errors = self.apply_sheet(slug, ops)
                message = ("Some sheet edits were skipped: " + " · ".join(errors[:5])) if errors else None
                push = pulled = True
            self._note(slug, last_pull=_now(), note=None, refused=None, error=message)
        if not push and not force:
            return
        record = boards.get_board(self.store, slug) or record
        doc = record["doc"]
        grid = sheetmirror.grid(doc, self._meta(doc))
        if base and not force and not pulled and canon(grid["rows"]) == canon(base["rows"]) and grid["colmap"] == base.get("colmap"):
            if not message:
                self._note(slug, error=None)
            return
        nrows = len(grid["rows"]) + sheetmirror.SPARE_ROWS
        ncols = len(grid["rows"][0]) + sheetmirror.SPARE_COLS
        if (tab["rows"], tab["cols"]) != (nrows, ncols):
            self.client.batch(sid, [{"updateSheetProperties": {
                "properties": {"sheetId": gid, "gridProperties": {"rowCount": nrows, "columnCount": ncols}},
                "fields": "gridProperties.rowCount,gridProperties.columnCount"}}])
        self.client.write(sid, tab["title"], sheetmirror.padded(grid["rows"], nrows, ncols))
        self._note(slug, base={"rows": canon(grid["rows"]), "colmap": grid["colmap"]}, last_push=_now(), refused=None, note=None,
                   error=message)
