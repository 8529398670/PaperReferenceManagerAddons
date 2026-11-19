"""Reading a Zotero library from a ZoteroWebDAV server instead of a folder.

library.source: remote in config.yaml. The server keeps each item as Zotero's
own JSON, with a change feed (GET /api/library/changes?since=<rev>), and the
attachment files as the .zip/.prop pairs Zotero's WebDAV sync writes. This
module mirrors the feed into one JSON file under the cache and builds the
same Item objects zotero.Library does, so the catalogue cannot tell the two
apart.

Only GET requests are made: nothing here writes to the server.

PDFs are not fetched up front. An attachment's Item.pdfs entry is the path
its file will have in the cache,

    <cache>/remote-files/<attachment key>/<md5 or 0>/<file name>

and the file is downloaded the first time something needs it: the PDF route
(ensure_pdf) or the worker, before figures or OCR (fetch_file). The md5 in
the path makes a changed file a new path, so the content queue's signature
(content.service.pdf_signature) changes with the file and not with whether
it has been downloaded yet.

Only the standard library is imported, because the worker (whose venv has
none of the web stack) uses fetch_file too.

The API key never goes into an error, a log line or a file other than
config.yaml.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.library.zotero import Item, normalize_doi, synthetic_key, year_of

REMOTE_FILES_DIR = "remote-files"
MIRROR_FILE = "remote-library.json"
MIRROR_VERSION = 1
USER_AGENT = "prma-remote-library/1"
TIMEOUT_SECONDS = 30
# How long a GET /api/library/changes?wait= is held open (the server allows
# 25 and has a 30 s write deadline); the read timeout is a little longer.
WAIT_SECONDS = 25
WAIT_TIMEOUT_SECONDS = WAIT_SECONDS + 10
DOWNLOAD_TIMEOUT_SECONDS = 120
PAGE_LIMIT = 1000
# The attachment index (which files the server holds, and their md5) is
# refreshed whenever the feed moved, and at least this often otherwise:
# Zotero uploads a file separately from its item.
ATTACHMENTS_REFRESH_SECONDS = 600
# With a server that says what files changed (files_stamp), the whole index
# is still read this often: a removed file leaves no row to report.
ATTACHMENTS_FULL_SECONDS = 3600
# Zotero's link modes, as the JSON API spells them and as numbers. Only
# imported files are ever on the WebDAV server; linked files live on the
# machine that linked them.
IMPORTED_LINK_MODES = {"imported_file", "imported_url", 0, 1, "0", "1"}
SKIPPED_TYPES = {"attachment", "note", "annotation"}
_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
_UNSAFE_NAME_RE = re.compile(r"[\x00-\x1f/\\]")

# url -> (status, headers, body). Replaced in tests.
Opener = Callable[[urllib.request.Request, int], tuple[int, dict[str, str], bytes]]


class RemoteError(Exception):
    """A request that failed, said without the address or the key."""


def _urlopen(request: urllib.request.Request, timeout: int) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, b""


def _describe(error: BaseException) -> str:
    """Why a request failed, without the URL (urllib puts it in some)."""
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        name = type(reason).__name__ if isinstance(reason, BaseException) else "URLError"
        detail = getattr(reason, "strerror", None) or ""
        return f"{name}{': ' + detail if detail else ''}"
    return type(error).__name__


def _status_error(status: int) -> RemoteError:
    if status in (401, 403):
        return RemoteError(f"the remote library refused the API key (HTTP {status})")
    if status == 404:
        return RemoteError("the remote library has no such library or file (HTTP 404)")
    if status == 429:
        return RemoteError("the remote library is rate limiting (HTTP 429)")
    return RemoteError(f"the remote library answered HTTP {status}")


class Remote:
    """The server's address, key and library name, GET, and the one POST
    (mend.py)."""

    def __init__(self, base_url: str, api_key: str, library: str = "", opener: Opener | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self.library = library
        self.opener = opener or _urlopen

    def url(self, path: str, params: dict[str, Any] | None = None) -> str:
        merged = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        if self.library:
            merged["library"] = self.library
        query = ("?" + urllib.parse.urlencode(merged)) if merged else ""
        return self.base_url + path + query

    def get(self, path: str, params: dict[str, Any] | None = None, timeout: int = TIMEOUT_SECONDS, accept: str = "application/json",
            gzipped: bool = False) -> bytes:
        headers = {"Authorization": "Bearer " + self._key, "Accept": accept, "User-Agent": USER_AGENT}
        if gzipped:
            headers["Accept-Encoding"] = "gzip"
        request = urllib.request.Request(self.url(path, params), headers=headers)
        try:
            status, answer_headers, body = self.opener(request, timeout)
        except (OSError, ValueError) as error:
            raise RemoteError(f"the remote library could not be reached ({_describe(error)})") from None
        if status != 200:
            error = _status_error(status)
            error.status = status  # type: ignore[attr-defined]
            raise error
        if (answer_headers.get("content-encoding") or "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except (OSError, EOFError):
                raise RemoteError("the remote library sent a broken gzip body") from None
        return body

    def post_json(self, path: str, body: dict[str, Any], timeout: int = TIMEOUT_SECONDS) -> dict[str, Any]:
        """A write (mend.py's key moves): JSON in, JSON out."""
        headers = {"Authorization": "Bearer " + self._key, "Accept": "application/json", "User-Agent": USER_AGENT,
                   "Content-Type": "application/json"}
        request = urllib.request.Request(self.url(path), data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            status, _, answer = self.opener(request, timeout)
        except (OSError, ValueError) as error:
            raise RemoteError(f"the remote library could not be reached ({_describe(error)})") from None
        if status != 200:
            error = _status_error(status)
            error.status = status  # type: ignore[attr-defined]
            raise error
        try:
            data = json.loads(answer)
        except ValueError:
            raise RemoteError("the remote library answered something that is not JSON") from None
        if not isinstance(data, dict):
            raise RemoteError("the remote library answered something unexpected")
        return data

    def post_bytes(self, path: str, params: dict[str, Any], data: bytes, timeout: int = TIMEOUT_SECONDS) -> dict[str, Any]:
        """A raw upload (mend.py's file pieces): bytes in, JSON out."""
        headers = {"Authorization": "Bearer " + self._key, "Accept": "application/json", "User-Agent": USER_AGENT,
                   "Content-Type": "application/octet-stream"}
        request = urllib.request.Request(self.url(path, params), data=data, headers=headers, method="POST")
        try:
            status, _, answer = self.opener(request, timeout)
        except (OSError, ValueError) as error:
            raise RemoteError(f"the remote library could not be reached ({_describe(error)})") from None
        if status != 200:
            error = _status_error(status)
            error.status = status  # type: ignore[attr-defined]
            raise error
        try:
            reply = json.loads(answer)
        except ValueError:
            raise RemoteError("the remote library answered something that is not JSON") from None
        return reply if isinstance(reply, dict) else {}

    def get_json(self, path: str, params: dict[str, Any] | None = None, timeout: int = TIMEOUT_SECONDS, gzipped: bool = False) -> dict[str, Any]:
        body = self.get(path, params, timeout=timeout, gzipped=gzipped)
        try:
            data = json.loads(body)
        except ValueError:
            raise RemoteError("the remote library answered something that is not JSON") from None
        if not isinstance(data, dict):
            raise RemoteError("the remote library answered something unexpected")
        return data


# -- files -------------------------------------------------------------------


def safe_name(name: str) -> str:
    """A file name that stays one path component."""
    cleaned = _UNSAFE_NAME_RE.sub("_", os.path.basename(str(name or "")).strip()).lstrip(".")
    if not cleaned:
        cleaned = "file.pdf"
    if len(cleaned) > 180:
        stem, dot, ext = cleaned.rpartition(".")
        cleaned = (stem[:170] + dot + ext[:9]) if dot else cleaned[:180]
    return cleaned


def file_path(files_dir: Path, attach_key: str, md5: str, filename: str) -> Path:
    return files_dir / attach_key / (md5 or "0") / safe_name(filename)


def attachment_of(path: str | Path) -> str | None:
    """The attachment key of a path file_path made, else None."""
    parts = Path(path).parts
    if len(parts) >= 4 and parts[-4] == REMOTE_FILES_DIR and _KEY_RE.match(parts[-3]):
        return parts[-3]
    return None


def is_remote_path(path: str | Path) -> bool:
    return attachment_of(path) is not None


def fetch_file(remote: Remote, attach_key: str, dest: Path) -> Path:
    """Download an attachment's main file to dest, atomically: a reader sees
    the whole file or none. Two processes fetching the same file at once
    both succeed; the second rename wins with identical bytes."""
    if not _KEY_RE.match(attach_key):
        raise RemoteError("not an attachment key")
    body = remote.get(
        f"/api/library/attachments/{attach_key}/file", {"inline": "true"},
        timeout=DOWNLOAD_TIMEOUT_SECONDS, accept="application/pdf,*/*",
    )
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(body)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


# -- the library -------------------------------------------------------------


def _stamp_time(iso: str) -> str:
    """2026-11-19T07:09:49.5699Z -> 2026-11-19 07:09:49, Zotero's own form."""
    iso = str(iso or "")
    if "T" not in iso:
        return iso
    day, _, rest = iso.partition("T")
    return f"{day} {rest[:8]}"


def _item_id(zkey: str) -> int:
    """A stable number for an item that has no database row: its key read
    as base 36 (8 characters fit easily in 64 bits)."""
    try:
        return int(zkey, 36)
    except ValueError:
        return 0


class RemoteLibrary:
    """The library on a ZoteroWebDAV server. Same face as zotero.Library:
    stamp() is cheap and None when there is no library at all; read()
    returns every item keyed by paper key."""

    def __init__(self, remote: Remote, cache_dir: Path, poll_seconds: int = 30) -> None:
        self.remote = remote
        self.cache_dir = cache_dir
        self.mirror_path = cache_dir / MIRROR_FILE
        self.files_dir = cache_dir / REMOTE_FILES_DIR
        self.poll_seconds = poll_seconds
        self.read_fell_back = False
        # Why the last look failed, for the catalogue's status. Never holds
        # the address or the key.
        self.error = ""
        self._lock = threading.Lock()
        self._fetch_locks: dict[str, threading.Lock] = {}
        self._loaded = False
        self._rev = 0
        self._items: dict[str, dict[str, Any]] = {}
        self._collections: dict[str, str] = {}
        self._attachments: dict[str, dict[str, Any]] = {}
        self._attachments_at = 0.0
        # The server's files_stamp as of _attachments (None: the server does
        # not have it, or we have not asked yet), and whether it holds a
        # changes request open (wait=) -- both from newer servers.
        self._files_stamp: int | None = None
        self._waits = False
        # False: never hold a request open, even when the server can -- a
        # user's own library (app/library/registry.py) asks at poll_seconds,
        # so many of them cannot fill the thread pool with waiting requests.
        self.long_poll = True
        self._polled_at = 0.0
        self._stamp: tuple[Any, ...] | None = None
        self.clock: Callable[[], float] = time.monotonic

    @property
    def sqlite_path(self) -> str:
        # The catalogue names this when there is no library; say what it is.
        return "the remote library"

    # -- the mirror ----------------------------------------------------------

    def _load_mirror(self) -> None:
        self._loaded = True
        try:
            data = json.loads(self.mirror_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != MIRROR_VERSION:
            return
        # A mirror of another server or library is not this one's.
        if data.get("source") != self._source_id():
            return
        self._rev = int(data.get("rev") or 0)
        self._items = dict(data.get("items") or {})
        self._collections = dict(data.get("collections") or {})
        self._attachments = dict(data.get("attachments") or {})
        stamp = data.get("files_stamp")
        self._files_stamp = int(stamp) if isinstance(stamp, int) else None

    def _source_id(self) -> str:
        # Which server and library, without the key. Kept in the mirror so
        # pointing remote_url elsewhere starts over instead of mixing two.
        # A hash, so the cache does not hold the address either.
        return hashlib.sha256(f"{self.remote.base_url}#{self.remote.library}".encode()).hexdigest()[:16]

    def _save_mirror(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": MIRROR_VERSION,
            "source": self._source_id(),
            "rev": self._rev,
            "items": self._items,
            "collections": self._collections,
            "attachments": self._attachments,
            "files_stamp": self._files_stamp,
        }
        tmp = self.mirror_path.with_name(self.mirror_path.name + ".tmp")
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, separators=(",", ":"))
        os.replace(tmp, self.mirror_path)

    # -- pulling -------------------------------------------------------------
    #
    # Network first, with no lock held (a held-open changes request must not
    # keep the PDF route waiting), then the answers are applied under the
    # lock in one go. Only one pull runs at a time: the catalogue's sync
    # lock sees to that.

    def _pull(self, rev: int, have_items: bool, files_stamp: int | None, attachments_due: bool, latest_file: str) -> dict[str, Any]:
        """What changed on the server, as {reset, records, rev, files_stamp,
        attachments, attachments_merge}."""
        pulled: dict[str, Any] = {"reset": False, "records": [], "rev": rev, "attachments": None, "attachments_merge": False}
        if not have_items:
            snapshot = self._snapshot()
            if snapshot is not None:
                return snapshot
        restarted = False
        wait = self._waits and have_items and self.long_poll
        while True:
            params: dict[str, Any] = {"since": pulled["rev"], "limit": PAGE_LIMIT}
            if wait:
                params["wait"] = WAIT_SECONDS
                if files_stamp is not None:
                    params["files"] = files_stamp
            page = self.remote.get_json("/api/library/changes", params, timeout=WAIT_TIMEOUT_SECONDS if wait else TIMEOUT_SECONDS)
            wait = False  # only the first request waits
            if page.get("full_resync") and not restarted:
                # The server forgot tombstones older than our rev: start over.
                restarted = True
                snapshot = self._snapshot()
                if snapshot is not None:
                    return snapshot
                pulled.update(reset=True, records=[], rev=0)
                continue
            pulled["records"].extend(page.get("records") or [])
            pulled["rev"] = int(page.get("rev") or pulled["rev"])
            if "files_stamp" in page:
                pulled["files_stamp"] = int(page["files_stamp"])
            if not page.get("more"):
                break
        self._waits = "files_stamp" in pulled
        moved = bool(pulled["records"]) or pulled["reset"]
        server_stamp = pulled.get("files_stamp")
        if attachments_due or files_stamp is None or server_stamp is None:
            # An older server, a first look, or the hourly full read.
            if attachments_due or moved or server_stamp is None or files_stamp is None:
                pulled["attachments"] = self._attachment_rows({})
        elif server_stamp != files_stamp:
            pulled["attachments"] = self._attachment_rows({"since": latest_file} if latest_file else {})
            pulled["attachments_merge"] = bool(latest_file)
        return pulled

    def _snapshot(self) -> dict[str, Any] | None:
        """The whole library in one gzipped answer (newer servers); None
        when the server does not have GET /api/library/snapshot."""
        try:
            data = self.remote.get_json("/api/library/snapshot", None, timeout=DOWNLOAD_TIMEOUT_SECONDS, gzipped=True)
        except RemoteError as error:
            if getattr(error, "status", 0) == 404:
                return None
            raise
        # A server with the snapshot can hold a changes request open too.
        self._waits = "files_stamp" in data
        records = [dict(r, kind="item") for r in data.get("items") or []]
        records += [dict(r, kind="collection") for r in data.get("collections") or []]
        return {
            "reset": True,
            "records": records,
            "rev": int(data.get("rev") or 0),
            "files_stamp": int(data["files_stamp"]) if "files_stamp" in data else None,
            "attachments": {row["key"]: _attachment(row) for row in data.get("attachments") or [] if row.get("key")},
            "attachments_merge": False,
            "snapshot": True,
        }

    def _attachment_rows(self, extra: dict[str, Any]) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        offset = 0
        while True:
            page = self.remote.get_json("/api/library/attachments", {"limit": PAGE_LIMIT, "offset": offset, **extra})
            rows = page.get("attachments") or []
            for row in rows:
                if row.get("key"):
                    found[str(row["key"])] = _attachment(row)
            following = page.get("next")
            if not rows or not following or int(following) <= offset:
                break
            offset = int(following)
        return found

    def _merge(self, pulled: dict[str, Any], now: float) -> bool:
        """Apply a pull. True when anything changed. Under the lock."""
        moved = False
        if pulled["reset"]:
            self._items, self._collections = {}, {}
            moved = True
        for record in pulled["records"]:
            self._apply(record)
            moved = True
        self._rev = pulled["rev"]
        rows = pulled.get("attachments")
        if rows is not None:
            merged = {**self._attachments, **rows} if pulled.get("attachments_merge") else rows
            if merged != self._attachments:
                self._attachments = merged
                moved = True
            if not pulled.get("attachments_merge"):
                self._attachments_at = now
        if "files_stamp" in pulled and pulled["files_stamp"] != self._files_stamp and (rows is not None or pulled.get("snapshot")):
            self._files_stamp = pulled["files_stamp"]
            moved = True
        return moved

    def _apply(self, record: dict[str, Any]) -> None:
        key = str(record.get("key") or "")
        if not key:
            return
        if record.get("kind") == "collection":
            if record.get("deleted"):
                self._collections.pop(key, None)
            else:
                data = record.get("data") or {}
                self._collections[key] = str(data.get("name") or record.get("title") or "")
            return
        if record.get("deleted"):
            self._items.pop(key, None)
            return
        self._items[key] = {
            "rev": int(record.get("rev") or 0),
            "updated": str(record.get("updated_at") or ""),
            "data": record.get("data") or {},
        }

    # -- change detection ----------------------------------------------------

    def stamp(self) -> tuple[Any, ...] | None:
        """Asks the server what changed: at most every poll_seconds, or, with
        a server that can hold the request open, as soon as anything does
        (each call then waits up to WAIT_SECONDS). None while there has
        never been a library to show."""
        with self._lock:
            if not self._loaded:
                self._load_mirror()
            now = self.clock()
            if self._stamp is not None and not (self._waits and self.long_poll) and now - self._polled_at < self.poll_seconds:
                return self._stamp
            self._polled_at = now
            full_every = ATTACHMENTS_FULL_SECONDS if self._files_stamp is not None else ATTACHMENTS_REFRESH_SECONDS
            state = (
                self._rev,
                bool(self._items),
                self._files_stamp,
                not self._attachments or now - self._attachments_at >= full_every,
                max((row.get("updated") or "" for row in self._attachments.values()), default=""),
            )
        try:
            pulled = self._pull(*state)
        except RemoteError as error:
            with self._lock:
                self.error = str(error)
                print(f"[library] remote: {self.error}", flush=True)
                self._waits = False  # ask plainly next time, at poll_seconds
                if not self._items:
                    return None
                if self._stamp is None:
                    self._stamp = self._make_stamp()
                return self._stamp
        with self._lock:
            moved = self._merge(pulled, now)
            try:
                if moved or not self.mirror_path.exists():
                    self._save_mirror()
                self.error = ""
            except OSError as error:
                self.error = f"could not write the remote library's cache ({type(error).__name__})"
                print(f"[library] remote: {self.error}", flush=True)
            self._stamp = self._make_stamp()
            return self._stamp

    def _make_stamp(self) -> tuple[Any, ...]:
        return (self._rev, len(self._items), hash(json.dumps(self._attachments, sort_keys=True)))

    def poll_now(self) -> None:
        """Make the next stamp() ask the server, however recent the last."""
        self._polled_at = float("-inf")

    # -- reading -------------------------------------------------------------

    def read(self) -> dict[str, Item]:
        with self._lock:
            if not self._loaded:
                self._load_mirror()
            return self._read()

    def _read(self) -> dict[str, Item]:
        parents: dict[str, list[tuple[int, str, str]]] = {}
        for attach_key, entry in self._items.items():
            data = entry["data"]
            if data.get("itemType") != "attachment" or data.get("deleted"):
                continue
            parent = str(data.get("parentItem") or "")
            if not parent or data.get("linkMode") not in IMPORTED_LINK_MODES:
                continue
            filename = str(data.get("filename") or "")
            is_pdf = data.get("contentType") == "application/pdf" or filename.lower().endswith(".pdf")
            held = self._attachments.get(attach_key)
            if not is_pdf or not held or not held.get("ok"):
                continue
            path = file_path(self.files_dir, attach_key, held.get("md5") or "", filename or "file.pdf")
            parents.setdefault(parent, []).append((entry.get("rev") or 0, attach_key, str(path)))

        ordered = sorted(self._items.items(), key=lambda pair: (pair[1].get("rev") or 0, pair[0]))
        items: dict[str, Item] = {}
        for zkey, entry in ordered:
            data = entry["data"]
            kind = str(data.get("itemType") or "")
            if not kind or kind in SKIPPED_TYPES or data.get("deleted"):
                continue
            # The same rule as zotero.Library, so a paper keeps its key across sources.
            doi = normalize_doi(data.get("DOI")) or ""
            title = str(data.get("title") or "").strip()
            pdfs = [path for _, _, path in sorted(parents.get(zkey, []))]
            if not title and not doi and not pdfs:
                continue
            key = doi or synthetic_key(zkey)
            if key in items:
                continue  # the same DOI twice: the first wins, as in zotero.Library
            creators = [_creator(c) for c in data.get("creators") or [] if isinstance(c, dict)]
            authors = [" ".join(p for p in (c["first"], c["last"]) if p) for c in creators if c["type"] == "author"]
            updated = _stamp_time(entry.get("updated") or "")
            items[key] = Item(
                key=key,
                zkey=zkey,
                item_id=_item_id(zkey),
                type=kind,
                title=title or doi,
                doi=doi,
                year=year_of(data.get("date")),
                journal=str(data.get("publicationTitle") or data.get("bookTitle") or data.get("proceedingsTitle") or "").strip(),
                abstract=str(data.get("abstractNote") or "").strip(),
                url=str(data.get("url") or "").strip(),
                date_added=_stamp_time(data.get("dateAdded") or "") or updated,
                date_modified=_stamp_time(data.get("dateModified") or "") or updated,
                authors=[name for name in authors if name],
                creators=creators,
                tags=sorted({str(t.get("tag") or "") for t in data.get("tags") or [] if isinstance(t, dict) and t.get("tag")}),
                collections=sorted({self._collections[c] for c in data.get("collections") or [] if self._collections.get(c)}),
                pdfs=pdfs,
                # The zips carry no .zotero-ft-cache: the text comes from the
                # worker (its text layer, else OCR).
                fulltext_files=[],
                text_known=False,
            )
        return items

    # -- files ---------------------------------------------------------------

    def ensure_pdf(self, path: str | Path) -> Path | None:
        """The file at path, downloading it first if it is not cached yet.
        None when path is not one of this library's files or the download
        failed."""
        path = Path(path)
        attach_key = attachment_of(path)
        if attach_key is None or self.files_dir not in path.parents:
            return None
        if path.is_file():
            return path
        with self._lock:
            lock = self._fetch_locks.setdefault(attach_key, threading.Lock())
        with lock:
            if path.is_file():
                return path
            try:
                return fetch_file(self.remote, attach_key, path)
            except (RemoteError, OSError) as error:
                print(f"[library] remote: could not fetch {attach_key}: {error}", flush=True)
                return None


def _attachment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "md5": str(row.get("md5") or ""),
        "mtime": int(row.get("mtime") or 0),
        "ok": bool(row.get("has_zip")) and bool(row.get("has_prop")),
        "updated": str(row.get("updated_at") or ""),
    }


def _creator(raw: dict[str, Any]) -> dict[str, str]:
    last = raw.get("lastName")
    if last is None:
        last = raw.get("name")  # a one-field name (an institution)
    return {"type": str(raw.get("creatorType") or ""), "first": str(raw.get("firstName") or ""), "last": str(last or "")}

