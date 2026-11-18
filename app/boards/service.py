"""The running lists: how ops reach the library, and the live stream that
tells every open page "list X is at rev N now" so it fetches the list again.
"""
from __future__ import annotations

import asyncio
import copy
import json
import threading
from typing import Any, Callable

from app.boards import board, cite, ops, refs, sync, store as boards
from app.core import db, sse
from app.models import to_iso, utc_now
from app.library.catalogue import Catalogue
from app.search import query as q

RESOLVE_THRESHOLD = 96
# Who an auto-added paper's version is by, in a list's history.
AUTO_ADD_BY = "Zotero auto-add"
# The built-in Library list: every paper in Zotero, newest added first,
# read-only. It is not stored; it is made from the catalogue when asked for.
LIBRARY = "library"
LIBRARY_NAME = "Library"


class BoardService:
    def __init__(self, store: db.Store, catalogue: Catalogue) -> None:
        self.store = store
        self.catalogue = catalogue
        self.hub = sse.Hub(max_clients=32)
        self._loop: asyncio.AbstractEventLoop | None = None
        # The content service (app/content/), for modality tags and the
        # Code/Datasets links; main sets it. None in tests that need neither.
        self.content: Any = None
        # Told after any list changed (the review screener's candidates).
        self.on_changed: Any = None
        # Told what changed, from whichever thread changed it: {slug, rev, by,
        # locked?, deleted?, renamed_from?} (the Google Sheets mirror).
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        # The built-in Library list as last built: {"record", "view"}. Building
        # it reads every paper's scan results, so it is kept until a list,
        # Zotero or a paper's content changes (library_stale).
        self._library: dict[str, Any] = {}
        # One auto_add at a time: two syncs close together must not both add.
        self._auto_add_lock = threading.Lock()

    def library_stale(self) -> None:
        """Something the Library list shows changed: build it again when next asked."""
        self._library = {}

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    def stop(self) -> None:
        self.hub.close()

    def changed(self, slug: str, rev: int, by: str, locked: bool | None = None, deleted: bool = False, renamed_from: str | None = None) -> None:
        """Tell open pages. Safe from any thread. locked rides along when the
        view-only switch moved (rev does not move for that); deleted and
        renamed_from when the list itself went or moved."""
        self.library_stale()
        data: dict[str, Any] = {"slug": slug, "rev": rev, "by": by}
        if locked is not None:
            data["locked"] = locked
        if deleted:
            data["deleted"] = True
        if renamed_from:
            data["renamed_from"] = renamed_from
        message = sse.event("list", json.dumps(data))
        if self.on_changed is not None:
            self.on_changed()
        for listener in self.listeners:
            try:
                listener(dict(data))
            except Exception as error:  # noqa: BLE001 -- a listener never fails the write that told it
                print(f"[lists] a listener failed: {error!r}", flush=True)
        if self._loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self.hub.publish(message)
        else:
            sse.publish_from_thread(self._loop, self.hub, message)

    # -- what ops need from outside the document ---------------------------------

    def resolve(self, spec: str) -> dict[str, Any]:
        """The paper an `add` names: a key, a DOI, a Zotero key, or a title
        close enough to be that paper (96, as the old app). Raises OpError
        naming the closest titles when it is none of those."""
        paper = self.catalogue.find(spec)
        if paper is None and self.content is not None and spec.strip()[:1] == "W" and spec.strip()[1:].isdigit():
            # An OpenAlex id: a paper the library cites or is cited by.
            work = self.content.pool.work(spec.strip())
            if work is not None:
                return {
                    "key": work["doi"] or work["wid"], "title": work["title"], "doi": work["doi"], "year": work["year"],
                    "journal": work["journal"], "wid": work["wid"], "pdf": work["oa_pdf"], "authors": ", ".join(work["authors"][:6]),
                    "in_library": False,
                }
        if paper is None and len(spec) >= 8:
            result = self.catalogue.search(spec, mode="title")
            best = result.rows[0] if result.rows else None
            if best is not None:
                from rapidfuzz import fuzz

                if best.title_f == q.fold(spec) or fuzz.token_sort_ratio(best.title_f, q.fold(spec)) >= RESOLVE_THRESHOLD:
                    paper = best
            if paper is None:
                near = ", ".join(repr(p.record.get("title", "")[:80]) for p in result.rows[:3])
                raise ops.OpError(f"no paper in the library matches {spec!r}" + (f" -- closest: {near}" if near else ""))
        if paper is None:
            raise ops.OpError(f"no paper in the library is {spec!r}")
        record = paper.record
        return {
            "key": record["key"],
            "title": record.get("title", ""),
            "doi": record.get("doi", ""),
            "year": record.get("year"),
            "journal": record.get("journal", ""),
            "in_library": True,
        }

    def meta(self, keys: list[str], mods: bool = False, links: bool = False, titles: dict | None = None) -> dict[str, Any]:
        """What ops ask about papers: whether each is in the library, its
        modality tags (mods) and the code and dataset links found in it
        (links), as the content stages have them so far."""
        out = {}
        here = [key for key in keys if self.catalogue.get(key) is not None]
        found = self.content.meta(here, links) if (self.content is not None and (mods or links)) else {}
        for key in here:
            out[key] = {"in_library": True, **found.get(key, {})}
        return out

    def parse_refs(self, text: str) -> list[dict[str, Any]]:
        return refs.resolve(self.catalogue, text)

    def purge_job(self) -> tuple[str, str]:
        """The lists-purge job: deleted lists past their 30 days go for good."""
        gone = boards.purge_deleted(self.store)
        return (f"removed {gone} deleted list(s)" if gone else ""), ""

    # -- the built-in Library list -------------------------------------------------

    def library_record(self) -> dict[str, Any]:
        """Every paper in Zotero as a list record, newest added first, locked.

        A paper is the same paper on every list, so each row says what the
        lists say about it: its tags and every cell (Notes, Methods summary,
        Code, Datasets, any column a list added), the columns coming with them
        (sync.fill, the same rule a paper arriving on a list follows; the
        sharing lists first). A cell no list has filled gets the Code and
        Datasets links the scans found (ops.prefill), and a paper with no tags
        its modality tags, as an import does. Nothing is folded away: the
        Library cannot change, so its Columns menu cannot unfold one.

        Its rows are what an add would make, so copying from it (import_list
        from "library") lands them like any other list's. Kept until stale:
        callers only read it."""
        cached = self._library.get("record")
        if cached is not None:
            return cached
        doc = board.default_doc()
        papers = sorted(self.catalogue.all(), key=lambda paper: paper.record.get("date_added") or "", reverse=True)
        items = []
        for paper in papers:
            record = paper.record
            row = ops.new_item(doc, {"key": record["key"], "title": record.get("title", ""), "doi": record.get("doi", ""),
                                     "year": record.get("year"), "journal": record.get("journal", ""), "in_library": True})
            row["added_at"] = record.get("date_added") or ""
            items.append(row)
        doc["items"] = items
        keys = [row["key"] for row in items]
        stored = [record["doc"] for _, record in self.store.all(db.BUCKET_BOARDS) if not record.get("deleted")]
        stored.sort(key=lambda other: not sync.sends(other))
        if stored:
            sync.fill(doc, keys, stored)
        meta = self.meta(keys, mods=True, links=True)
        for row in items:
            found = meta.get(row["key"]) or {}
            ops.prefill(doc, row, found)
            if not row.get("tags") and found.get("mods"):
                row["tags"] = list(found["mods"])
                ops.sort_tags(row)
            for tag in row.get("tags") or []:
                ops.remember_tag(doc, tag)
        for row in items:
            for column in doc.get("columns") or []:
                row.setdefault("fields", {}).setdefault(column["id"], "")
        doc.setdefault("options", {})["fold_cols"] = []
        record = {"slug": LIBRARY, "name": LIBRARY_NAME, "rev": 0, "locked": True, "builtin": True, "doc": doc}
        self._library = {"record": record}
        return record

    def find(self, slug: str) -> dict[str, Any]:
        """A list to read: the built-in Library, or a stored one (following a
        rename). Raises BoardError."""
        if slug == LIBRARY:
            return self.library_record()
        return boards.find_board(self.store, slug)

    # -- the other lists, as ops see them ----------------------------------------

    def list_doc(self, slug: str) -> dict[str, Any]:
        """Another list's document ("" is the main one, "library" every paper
        in Zotero), following a rename."""
        try:
            return self.find(slug or boards.MAIN)["doc"]
        except boards.BoardError as refusal:
            raise ops.OpError(str(refusal)) from None

    def tiers_doc(self, slug: str = "") -> dict[str, Any]:
        """The tier list pull_tiers reads: the one named, else the first list
        with sections."""
        if slug:
            return self.list_doc(slug)
        for row in boards.list_boards(self.store):
            if row["sections"]:
                record = boards.get_board(self.store, row["slug"])
                if record is not None:
                    return record["doc"]
        raise ops.OpError("no list has tiers (sections) switched on")

    def shared_docs(self) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for _, record in self.store.all(db.BUCKET_BOARDS):
            if not record.get("deleted") and sync.sends(record.get("doc")):
                out.append((record.get("name", record["slug"]), record["doc"]))
        return out

    def remaining(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        """Every library paper not on `doc` (list or shelf), newest added
        first, as an add would take it, each with its modality tags (mods) as
        the content stages have them."""
        here = ops._here(doc)
        out = []
        mods = {}
        if self.content is not None:
            mods = {key: entry.get("mods") or [] for key, entry in self.content.meta([p.key for p in self.catalogue.all()], False).items()}
        for paper in self.catalogue.all():
            record = paper.record
            row = {"key": record["key"], "title": record.get("title", ""), "doi": record.get("doi", ""), "year": record.get("year"),
                   "journal": record.get("journal", ""), "in_library": True, "mods": mods.get(record["key"], []), "added": record.get("date_added") or ""}
            if not ops._is_here(here, row):
                out.append(row)
        out.sort(key=lambda row: row["added"], reverse=True)
        return out

    def ctx(self) -> ops.Ctx:
        return ops.Ctx(
            resolve=self.resolve, meta=self.meta, parse_refs=self.parse_refs, cite_styles=cite.usable(),
            list_doc=self.list_doc, tiers_doc=self.tiers_doc, shared_docs=self.shared_docs, remaining=self.remaining,
            modalities=self.content.vocab.labels if self.content is not None else [],
        )

    # -- one paper, the same on every list (app/boards/sync.py) -----------------

    def absorb(self, slug: str, change: Callable[[dict[str, Any]], int], by: str) -> int | str:
        """Make `change` to a list's document as one new version, without
        passing it on (an absorbed edit does not cascade). -> how many papers
        changed, or "locked" / "gone"."""
        with self.store.transaction() as tx:
            record = tx.get(db.BUCKET_BOARDS, slug)
            if record is None or record.get("deleted"):
                return "gone"
            if record.get("locked"):
                return "locked"
            before = record["doc"]
            doc = copy.deepcopy(before)
            did = change(doc)
            doc = board.normalize(doc)
            if not did or doc == before:
                return 0
            rev = int(record.get("rev", 0))
            boards.keep_version(tx, record)
            record["doc"] = doc
            record["rev"] = rev + 1
            record["updated_at"] = to_iso(utc_now())
            record["updated_by"] = by
            tx.put(db.BUCKET_BOARDS, slug, record)
        self.changed(slug, rev + 1, by)
        return did

    def mirror(self, slug: str, before: dict[str, Any], after: dict[str, Any], by: str) -> list[dict[str, Any]]:
        """After a write to `slug` (before -> after): papers it newly holds get
        what the two-way lists already say about them (when it receives), and
        its tag and cell edits are made on every other list holding those
        papers (when it sends). -> one entry per list reached."""
        out: list[dict[str, Any]] = []
        others = [record for _, record in self.store.all(db.BUCKET_BOARDS) if not record.get("deleted") and record["slug"] != slug]
        new = sync.arrivals(before, after) if sync.receives(after) else []
        if new:
            rows = {r["key"]: r for r in (after.get("items") or []) + (after.get("staging") or [])}
            probe = {k: {"doi": str(rows[k].get("doi") or "").strip().lower()} for k in new if k in rows}
            sources = [record for record in others if sync.sends(record["doc"]) and sync.touches(record["doc"], probe)]
            if sources:
                names = [record.get("name", record["slug"]) for record in sources]
                did = self.absorb(slug, lambda doc: sync.fill(doc, new, [record["doc"] for record in sources]), by)
                if isinstance(did, int) and did:
                    out.append({"slug": slug, "name": "", "filled": did, "from": names})
        changes = sync.changes(before, after)
        if not changes or not sync.sends(after):
            return out
        for record in others:
            doc = record["doc"]
            if not sync.receives(doc) or not sync.touches(doc, changes):
                continue
            entry = {"slug": record["slug"], "name": record.get("name", record["slug"])}
            if record.get("locked"):
                out.append({**entry, "skipped": "locked"})
                continue
            did = self.absorb(record["slug"], lambda doc: sync.apply(doc, changes, after), by)
            if isinstance(did, str):
                out.append({**entry, "skipped": did})
            elif did:
                out.append({**entry, "papers": did})
        return out

    # -- papers newly saved to Zotero joining a list (options.auto_add) ----------

    def auto_add(self) -> list[dict[str, Any]]:
        """Put the papers saved to Zotero since each list's auto_add_since on
        every list with auto_add on, at its top or bottom, oldest first (so at
        the top the newest ends up first), and move the mark past them. Called
        after every library sync; a no-op when nothing is new. A locked list
        keeps its mark, so it catches up once unlocked. -> {slug, added} per
        list changed."""
        with self._auto_add_lock:
            out: list[dict[str, Any]] = []
            lists = [record for _, record in self.store.all(db.BUCKET_BOARDS) if not record.get("deleted") and not record.get("locked")]
            wanted = [(record, (record["doc"].get("options") or {})) for record in lists]
            wanted = [(record, opts) for record, opts in wanted if opts.get("auto_add") in ("top", "bottom")]
            if not wanted:
                return out
            papers = sorted(
                ((paper.record.get("date_added") or "", paper.key) for paper in self.catalogue.all()),
            )
            for record, opts in wanted:
                since = opts.get("auto_add_since") or ""
                if not since:
                    continue
                new = [(added, key) for added, key in papers if added > since]
                if not new:
                    continue
                try:
                    added = self._auto_add_one(record["slug"], opts["auto_add"], new)
                except boards.BoardError as refusal:
                    print(f"[lists] auto-add to {record['slug']!r} failed: {refusal}", flush=True)
                    continue
                if added:
                    out.append({"slug": record["slug"], "added": added})
            return out

    def _auto_add_one(self, slug: str, where: str, new: list[tuple[str, str]]) -> int:
        """One list's share of auto_add. An add that fails (a paper the library
        no longer finds) is left out and the rest go on. -> papers added."""
        new = new[: ops.MAX_OPS - 1]  # the rest come with the next sync, the mark stopping short of them
        # The options op is a no-op that keeps the batch from ever being empty,
        # so the mark still moves when every add was skipped.
        batch = [{"op": "add", "paper": key, "at": where, "if_absent": True} for _, key in new] + [{"op": "options", "auto_add": where}]
        mark = {"auto_add_since": new[-1][0]}
        while True:
            try:
                applied = boards.apply_ops(self.store, slug, batch, self.ctx(), AUTO_ADD_BY, set_options=mark)
                break
            except boards.BoardError as refusal:
                index = refusal.extra.get("index")
                if refusal.status != 400 or not isinstance(index, int) or not 0 <= index < len(batch) - 1:
                    raise
                print(f"[lists] auto-add to {slug!r} skipped {batch[index]['paper']!r}: {refusal}", flush=True)
                batch.pop(index)
        if applied.changed:
            self.changed(slug, applied.rev, AUTO_ADD_BY)
            self.mirror(slug, applied.before or {}, applied.doc, AUTO_ADD_BY)
        return sum(1 for result in applied.results if result.get("op") == "add" and not result.get("skipped"))

    # -- citations ---------------------------------------------------------------

    def cite_style(self, doc: dict[str, Any] | None, default: str) -> str:
        """The style a list's citations use: its own, then config's, then the
        bundled default, then the first usable one."""
        own = ((doc or {}).get("options") or {}).get("cite_style") or ""
        return cite.resolve_style(own, default)

    def cites(self, style: str, rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        """key -> {intext, full} for list rows (or bare {key} dicts)."""
        out = {}
        for row in rows:
            key = row.get("key") or ""
            if not key:
                continue
            paper = self.catalogue.get(key)
            out[key] = cite.render(style, key, paper.record if paper is not None else None, row)
        return out

    # -- the rows as the page draws them ---------------------------------------

    def papers_for(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Per row key, what the library knows now: whether it is there, has a
        PDF, has searchable text, and what of its content is ready (the badges).
        The row itself keeps what it was added with, so a paper deleted from
        Zotero still reads right on the list."""
        out = {}
        rows = (doc.get("items") or []) + (doc.get("staging") or [])
        badges = self.content.badges([row.get("key", "") for row in rows]) if self.content is not None else {}
        for row in rows:
            paper = self.catalogue.get(row.get("key", ""))
            if paper is None:
                out[row["key"]] = {"in_library": False}
            else:
                out[row["key"]] = {
                    "in_library": True,
                    "has_pdf": bool(paper.record.get("pdfs")),
                    "has_text": paper.has_text,
                    "authors": paper.record.get("authors", [])[:3],
                    "n_authors": len(paper.record.get("authors", [])),
                    "content": badges.get(row["key"]),
                }
        return out

    def view(self, record: dict[str, Any]) -> dict[str, Any]:
        if record.get("builtin") and self._library.get("record") is record and "view" in self._library:
            return self._library["view"]
        doc = record["doc"]
        out = {**boards.summary(record), "doc": doc, "papers": self.papers_for(doc)}
        if record.get("builtin") and self._library.get("record") is record:
            self._library["view"] = out
        return out
