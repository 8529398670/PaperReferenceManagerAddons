"""Adding papers to a library: what the Zotero plugin (zotero-plugin/) sends.

A paper saved in desktop Zotero (by the Zotero Connector, say) arrives here
as Zotero's own JSON for the item, its attachments and notes, and the
collections it is filed in, then its files in pieces. All of it is passed on
to a ZoteroWebDAV library, keys unchanged, and nothing is kept here: the
library's watcher (app/library/service.py) then reads it back like any other
change, so the paper is searchable seconds later with no reindex.

Which library (target_for):
  - the caller's own, when they connected one on the Account screen;
  - else the server's library (library.source remote), for admins only --
    its remote_key can write, and a plain user must not fill it;
  - never a local Zotero folder: PRMA only ever reads zotero.sqlite.

Only the standard library and app.library.remote are needed here. The
remote address and key never go into a reply, an error or a log line.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from app.library.remote import Remote, RemoteError, RemoteLibrary, safe_name

ITEMS_PATH = "/api/bulk/library/items"
COLLECTIONS_PATH = "/api/bulk/library/collections"
UPLOAD_PATH = "/api/library/attachments/upload"
# The server's chunk_bytes: every piece but the last is exactly this long.
UPLOAD_PIECE = 4 * 1024 * 1024
BULK_MAX = 100  # the server's BulkMaxItems
MAX_ITEMS = 200  # one paper is a parent and its children: plenty
MAX_COLLECTIONS = 200
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
# A proxy's passing failure: sending the same thing again is harmless.
RETRY_STATUSES = (502, 503, 504, 520, 522, 524)
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


class IngestError(Exception):
    """A refusal, with the status the route answers. Never holds the
    remote's address or key."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Target:
    """Where a caller's papers go: the remote to write and the library
    service to wake once it is written."""

    remote: Remote
    kind: str  # "own" or "server"
    service: Any = None

    def poke(self) -> None:
        """Have the library ask the server on its next turn, rather than
        after remote_poll_seconds (the server's own library holds a request
        open and hears at once anyway)."""
        library = getattr(self.service, "library", None)
        if isinstance(library, RemoteLibrary):
            library.poll_now()


def target_for(libraries: Any, user: Any, is_admin: bool, secret_key: str, server_source: str) -> Target:
    """The library this caller's papers go to, or IngestError.

    libraries is the registry (app/library/registry.py); is_admin the
    request's effective role, so a user-scoped key held by an admin cannot
    write the server's library; server_source is library.source."""
    from app.models import user_library

    source = user_library.source_of(user, secret_key)
    if source is not None:
        service = libraries.for_user(user)
        library = getattr(service, "library", None)
        if service is libraries.server or not isinstance(library, RemoteLibrary):
            raise IngestError(409, "your own library cannot be opened: check it on the Account screen")
        return Target(library.remote, "own", service)
    if not is_admin:
        raise IngestError(403, "connect your own library on the Account screen first: only admins add to the server's library")
    if server_source != "remote":
        if server_source == "local":
            raise IngestError(409, "the server's library is a local Zotero folder, which PRMA only reads: add the paper in Zotero")
        raise IngestError(409, "the server has no library (library.source none)")
    service = libraries.server
    library = getattr(service, "library", None)
    if not isinstance(library, RemoteLibrary):
        raise IngestError(409, "the server's library is not a ZoteroWebDAV server")
    return Target(library.remote, "server", service)


# -- checking what was sent --------------------------------------------------


def _record(raw: Any, what: str, need_type: bool) -> tuple[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raise IngestError(400, f"each {what} must be an object with key and data")
    key = str(raw.get("key") or "")
    data = raw.get("data")
    if not KEY_RE.match(key):
        raise IngestError(400, f"{what} key must be a Zotero key: 8 of A-Z and 0-9")
    if not isinstance(data, dict):
        raise IngestError(400, f"{what} {key}: data must be Zotero's JSON object")
    if str(data.get("key") or key) != key:
        raise IngestError(400, f"{what} {key}: data.key says {str(data.get('key'))[:16]}")
    if need_type and not str(data.get("itemType") or ""):
        raise IngestError(400, f"{what} {key}: data has no itemType")
    clean = dict(data, key=key)
    # Zotero's own counters mean nothing on another server.
    clean.pop("version", None)
    return key, clean


def check(items: Any, collections: Any) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    """items and collections as (key, data), collections parents first and
    items parents first, or IngestError(400)."""
    items = items or []
    collections = collections or []
    if not isinstance(items, list) or not isinstance(collections, list):
        raise IngestError(400, "items and collections must be lists")
    if not items and not collections:
        raise IngestError(400, "nothing to add: items is empty")
    if len(items) > MAX_ITEMS or len(collections) > MAX_COLLECTIONS:
        raise IngestError(400, f"at most {MAX_ITEMS} items and {MAX_COLLECTIONS} collections at once")
    checked_items = dict(_record(raw, "item", True) for raw in items)
    checked_collections = dict(_record(raw, "collection", False) for raw in collections)
    return _parents_first(checked_items, "parentItem"), _parents_first(checked_collections, "parentCollection")


def _parents_first(records: dict[str, dict[str, Any]], parent_field: str) -> list[tuple[str, dict[str, Any]]]:
    """Each record after its parent, when its parent is among them; order
    otherwise kept. A loop (which Zotero never makes) is cut, not refused."""
    done: dict[str, dict[str, Any]] = {}

    def place(key: str, seen: set[str]) -> None:
        if key in done or key in seen:
            return
        parent = str(records[key].get(parent_field) or "")
        if parent in records:
            place(parent, seen | {key})
        done[key] = records[key]

    for key in records:
        place(key, set())
    return list(done.items())


# -- writing -----------------------------------------------------------------


def _with_retry(send: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return send()
    except RemoteError as error:
        if getattr(error, "status", 0) not in RETRY_STATUSES:
            raise
    return send()


def _bulk(remote: Remote, path: str, field: str, records: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    shared = {"library": remote.library} if remote.library else {}
    for start in range(0, len(records), BULK_MAX):
        batch = records[start:start + BULK_MAX]
        body = {"items": [{field: key, "data": data} for key, data in batch], "shared": shared}
        reply = _with_retry(lambda: remote.post_json(path, body, timeout=120))
        answers = {int(r.get("index", -1)): r for r in reply.get("results") or [] if isinstance(r, dict)}
        for index, (key, _) in enumerate(batch):
            answer = answers.get(index) or {}
            if answer.get("ok"):
                inner = answer.get("reply") or {}
                results.append({"key": key, "ok": True, "changed": bool(inner.get("changed", True)), "error": ""})
            else:
                results.append({"key": key, "ok": False, "changed": False,
                                "error": str(answer.get("error") or "the library did not say how it went")[:300]})
    return results


def store(target: Target, items: Any, collections: Any) -> dict[str, Any]:
    """Writes the collections, then the items, each parent before its
    children. {results: [{kind, key, ok, changed, error}], stored, failed}."""
    checked_items, checked_collections = check(items, collections)
    results: list[dict[str, Any]] = []
    try:
        if checked_collections:
            results += [dict(r, kind="collection") for r in _bulk(target.remote, COLLECTIONS_PATH, "collection_key", checked_collections)]
        if checked_items:
            results += [dict(r, kind="item") for r in _bulk(target.remote, ITEMS_PATH, "item_key", checked_items)]
    except RemoteError as error:
        raise IngestError(424, f"the library refused or could not be reached: {error}") from None
    finally:
        if results:
            target.poke()
    failed = sum(1 for r in results if not r["ok"])
    return {"results": results, "stored": len(results) - failed, "failed": failed}


def store_piece(target: Target, key: str, filename: str, size: int, offset: int, mtime: int, data: bytes) -> dict[str, Any]:
    """One piece of an attachment's file, passed straight on. The attachment
    item must be stored first (store). {received, done}."""
    if not KEY_RE.match(key or ""):
        raise IngestError(400, "key must be a Zotero key: 8 of A-Z and 0-9")
    if not (filename or "").strip():
        raise IngestError(400, "filename is needed")
    name = safe_name(unicodedata.normalize("NFC", filename))
    if size < 1 or size > MAX_FILE_BYTES:
        raise IngestError(400, "size must be between 1 byte and 2 GB")
    if offset < 0 or offset % UPLOAD_PIECE or offset >= size:
        raise IngestError(400, f"offset must be a multiple of {UPLOAD_PIECE} below size")
    expected = min(UPLOAD_PIECE, size - offset)
    if len(data) != expected:
        raise IngestError(400, f"this piece must be {expected} bytes, not {len(data)}")
    params = {"key": key, "filename": name, "size": size, "offset": offset, "mtime": mtime or int(time.time() * 1000)}
    try:
        reply = _with_retry(lambda: target.remote.post_bytes(UPLOAD_PATH, params, data, timeout=300))
    except RemoteError as error:
        status = getattr(error, "status", 0)
        if status == 404:
            raise IngestError(404, f"the library has no attachment {key}: send its item first") from None
        if status == 409:
            raise IngestError(409, "the library refused this piece: start the file again from offset 0") from None
        raise IngestError(424, f"the library refused or could not be reached: {error}") from None
    done = bool(reply.get("done"))
    if done:
        target.poke()
    return {"received": int(reply.get("received") or 0), "done": done}
