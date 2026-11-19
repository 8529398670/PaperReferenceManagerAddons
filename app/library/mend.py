"""Mend a remote library's keys from the local Zotero.

A ZoteroWebDAV library imported from an export (Zotero RDF, RIS, CSV) has
keys the import made up, and no dateAdded: an export carries neither. PRMA
names a paper with no DOI by its Zotero key, so those papers are different
papers in remote mode than in local mode. This pairs every record on the
server with the local item it stands for and asks the server to move it to
the real key and set its dates (POST /api/library/items/move), which also
moves the attachment's files. Nothing is uploaded again. Collections go
the same way (POST /api/library/collections/move), which also files every
item under the collection's real key.

Pairing, the way the server's own import matches (zotio.Match): a top item
by DOI, else by title and year; a child (attachment, note) under its paired
parent, by file name, title or URL, or a note by its text. A group of
identical papers is told apart by its attachments' md5s, else their file
names and notes; copies alike in all of that are paired in key order (each
ends up the same whichever way), and anything else unclear is left as it is
and reported.

plan() only reads; apply() sends the moves, a paper and its children always
in the same call.
"""
from __future__ import annotations

import html
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.library.remote import Remote, RemoteError
from app.library.zotero import Library, normalize_doi, year_of

MOVE_PATH = "/api/library/items/move"
COLLECTION_MOVE_PATH = "/api/library/collections/move"
BATCH = 900  # the server takes 1000 moves a call
CHILD_TYPES = ("attachment", "note")


@dataclass
class Record:
    key: str
    type: str
    parent: str = ""
    title: str = ""
    doi: str = ""
    date: str = ""
    filename: str = ""
    url: str = ""
    note: str = ""
    added: str = ""
    modified: str = ""
    md5: str = ""
    link: str = ""


@dataclass
class Plan:
    moves: list[dict[str, Any]] = field(default_factory=list)
    paired: int = 0
    rekeyed: int = 0
    dated: int = 0
    unpaired_server: list[str] = field(default_factory=list)
    unpaired_local: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    twins: int = 0
    trees: list[list[dict[str, Any]]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "paired": self.paired, "rekeyed": self.rekeyed, "dated": self.dated, "moves": len(self.moves),
            "unpaired_server": len(self.unpaired_server), "unpaired_local": len(self.unpaired_local),
            "ambiguous": len(self.ambiguous), "twins": self.twins,
        }


# -- reading -------------------------------------------------------------------


def _text(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _fold(value: Any) -> str:
    """Case, spacing and punctuation left out, as the server's normalTitle."""
    return "".join(ch for ch in _text(value).lower() if ch.isalnum())


_TAG = re.compile(r"<[^>]+>")


def _note_text(note: str) -> str:
    """A note as text: Zotero wraps it in <div class="zotero-note ...">, an
    export does not."""
    return _fold(html.unescape(_TAG.sub(" ", note or "")))


def _api_time(value: str) -> str:
    """Zotero's "2020-01-02 03:04:05" (UTC) as the web API writes it."""
    value = (value or "").strip()
    if len(value) == 19 and value[10] == " ":
        return value.replace(" ", "T") + "Z"
    return value


def read_local(library: Library) -> dict[str, Record]:
    """Every live item of the local Zotero, attachments and notes too."""
    connection = library._open()  # noqa: SLF001 -- the same safe copy the catalogue reads
    try:
        connection.row_factory = sqlite3.Row
        types = "itemTypesCombined" if _has_table(connection, "itemTypesCombined") else "itemTypes"
        records: dict[int, Record] = {}
        keys: dict[int, str] = {}
        for row in connection.execute(
            f"""SELECT items.itemID, items.key, t.typeName, items.dateAdded, items.dateModified FROM items
                JOIN {types} t ON t.itemTypeID = items.itemTypeID
                LEFT JOIN deletedItems d ON d.itemID = items.itemID
                WHERE d.itemID IS NULL AND t.typeName != 'annotation'"""
        ):
            records[row["itemID"]] = Record(key=row["key"], type=row["typeName"], added=_api_time(row["dateAdded"]),
                                            modified=_api_time(row["dateModified"]))
            keys[row["itemID"]] = row["key"]
        fields = "fieldsCombined" if _has_table(connection, "fieldsCombined") else "fields"
        for row in connection.execute(
            f"""SELECT itemData.itemID, f.fieldName, v.value FROM itemData
                JOIN {fields} f ON f.fieldID = itemData.fieldID JOIN itemDataValues v ON v.valueID = itemData.valueID
                WHERE f.fieldName IN ('title', 'DOI', 'date', 'url')"""
        ):
            record = records.get(row["itemID"])
            if record is not None:
                setattr(record, {"title": "title", "DOI": "doi", "date": "date", "url": "url"}[row["fieldName"]], _text(row["value"]))
        hashed = "storageHash" in {r[1] for r in connection.execute("PRAGMA table_info(itemAttachments)")}
        for row in connection.execute(f"SELECT itemID, parentItemID, path{', storageHash' if hashed else ''} FROM itemAttachments"):
            record = records.get(row["itemID"])
            if record is None:
                continue
            record.md5 = (row["storageHash"] or "").lower() if hashed else ""
            record.parent = keys.get(row["parentItemID"], "") if row["parentItemID"] else ""
            path = _text(row["path"])
            record.filename = path[len("storage:"):] if path.startswith("storage:") else Path(path).name if path else ""
        if _has_table(connection, "itemNotes"):
            for row in connection.execute("SELECT itemID, parentItemID, note FROM itemNotes"):
                record = records.get(row["itemID"])
                if record is not None:
                    record.parent = keys.get(row["parentItemID"], "") if row["parentItemID"] else ""
                    record.note = row["note"] or ""
        return {record.key: record for record in records.values()}
    finally:
        connection.close()


@dataclass
class Collection:
    key: str
    name: str
    parent: str = ""


def read_local_collections(library: Library) -> dict[str, Collection]:
    """Every live collection of the local Zotero."""
    connection = library._open()  # noqa: SLF001
    try:
        connection.row_factory = sqlite3.Row
        deleted = "LEFT JOIN deletedCollections d ON d.collectionID = c.collectionID" if _has_table(connection, "deletedCollections") else ""
        where = "WHERE d.collectionID IS NULL" if deleted else ""
        rows = list(connection.execute(f"SELECT c.collectionID, c.key, c.collectionName, c.parentCollectionID FROM collections c {deleted} {where}"))
        keys = {row["collectionID"]: row["key"] for row in rows}
        return {row["key"]: Collection(row["key"], _text(row["collectionName"]), keys.get(row["parentCollectionID"], "") if row["parentCollectionID"] else "")
                for row in rows}
    finally:
        connection.close()


def read_server_collections(remote: Remote) -> dict[str, Collection]:
    """Every live collection on the server, from the change feed (small)."""
    since, live = 0, {}
    while True:
        page = remote.get_json("/api/library/changes", {"since": since, "limit": 1000})
        for row in page.get("records") or []:
            if row.get("kind") == "collection":
                live[row["key"]] = row
        since = int(page.get("rev") or since)
        if not page.get("more"):
            break
    out: dict[str, Collection] = {}
    for row in live.values():
        if row.get("deleted"):
            continue
        data = row.get("data") or {}
        parent = data.get("parentCollection") or ""
        out[row["key"]] = Collection(row["key"], _text(data.get("name")), parent if isinstance(parent, str) else "")
    return out


def plan_collections(local: dict[str, Collection], server: dict[str, Collection]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Moves taking each server collection to the local one of the same name
    under the same (paired) parent, top down. A name twice under one parent
    on either side is left alone."""
    paired: dict[str, str] = {"": ""}  # server key -> local key
    moves: list[dict[str, str]] = []
    unclear = 0
    pending = True
    while pending:
        pending = False
        for parent_server, parent_local in list(paired.items()):
            server_kids = [c for c in server.values() if c.parent == parent_server and c.key not in paired]
            if not server_kids:
                continue
            local_kids = [c for c in local.values() if c.parent == parent_local]
            for kid in server_kids:
                same_server = [c for c in server_kids if _fold(c.name) == _fold(kid.name)]
                same_local = [c for c in local_kids if _fold(c.name) == _fold(kid.name)]
                if len(same_server) != 1 or len(same_local) != 1:
                    unclear += 1 if same_local else 0
                    paired[kid.key] = None  # type: ignore[assignment] -- seen, not paired
                    continue
                paired[kid.key] = same_local[0].key
                pending = True
                if kid.key != same_local[0].key:
                    moves.append({"from": kid.key, "to": same_local[0].key})
    matched = {k for k, v in paired.items() if k and v}
    counts = {"paired": len(matched), "rekeyed": len(moves), "unclear": unclear,
              "unpaired_server": len([k for k in server if k not in matched]),
              "unpaired_local": len([k for k in local if k not in set(paired.values())])}
    # A local key some other server collection already holds would be refused.
    taken = set(server)
    moves = [m for m in moves if m["to"] not in taken]
    return moves, counts


def apply_collections(remote: Remote, moves: list[dict[str, str]], dry_run: bool = False) -> dict[str, Any]:
    counts: dict[str, int] = {}
    refusals: list[str] = []
    filed = 0
    for start in range(0, len(moves), BATCH):
        reply = remote.post_json(COLLECTION_MOVE_PATH, {"collections": moves[start:start + BATCH], "dry_run": dry_run}, timeout=300)
        for row in reply.get("results") or []:
            counts[row.get("status", "?")] = counts.get(row.get("status", "?"), 0) + 1
            filed += int(row.get("children") or 0)
            if row.get("error") and len(refusals) < 20:
                refusals.append(f"{row.get('from')} -> {row.get('to')}: {row['error']}")
    return {"statuses": counts, "children": filed, "errors": refusals, "dry_run": dry_run}


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def read_server(remote: Remote) -> dict[str, Record]:
    """Every live item on the server: the snapshot, else the change feed."""
    rows: list[dict[str, Any]] = []
    md5s: dict[str, str] = {}
    try:
        snapshot = remote.get_json("/api/library/snapshot", None, timeout=300, gzipped=True)
        rows = snapshot.get("items") or []
        md5s = {a["key"]: (a.get("md5") or "").lower() for a in snapshot.get("attachments") or [] if a.get("key")}
    except RemoteError as error:
        if getattr(error, "status", 0) != 404:
            raise
        since, live = 0, {}
        while True:
            page = remote.get_json("/api/library/changes", {"since": since, "limit": 1000})
            for row in page.get("records") or []:
                if row.get("kind") == "item":
                    live[row["key"]] = row
            since = int(page.get("rev") or since)
            if not page.get("more"):
                break
        rows = list(live.values())
        offset = 0
        while True:
            page = remote.get_json("/api/library/attachments", {"limit": 1000, "offset": offset})
            listed = page.get("attachments") or []
            md5s.update({a["key"]: (a.get("md5") or "").lower() for a in listed if a.get("key")})
            following = page.get("next")
            if not listed or not following or int(following) <= offset:
                break
            offset = int(following)
    out: dict[str, Record] = {}
    for row in rows:
        data = row.get("data") or {}
        if row.get("deleted") or not row.get("key"):
            continue
        path = _text(data.get("path"))
        out[row["key"]] = Record(
            key=row["key"], type=data.get("itemType") or "", parent=data.get("parentItem") or "",
            title=_text(data.get("title")), doi=_text(data.get("DOI")), date=_text(data.get("date")),
            filename=_text(data.get("filename")) or (Path(path).name if path else ""), url=_text(data.get("url")),
            note=data.get("note") or "", added=data.get("dateAdded") or "", modified=data.get("dateModified") or "",
            md5=md5s.get(row["key"], ""), link=data.get("linkMode") or "",
        )
    return out


# -- pairing -------------------------------------------------------------------


def _tops(records: dict[str, Record]) -> list[Record]:
    return [r for r in records.values() if not r.parent or r.parent not in records]


def _children(records: dict[str, Record]) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = {}
    for record in records.values():
        if record.parent and record.parent in records:
            out.setdefault(record.parent, []).append(record)
    return out


def _top_signatures(record: Record) -> list[str]:
    signatures = []
    doi = (normalize_doi(record.doi) or "").lower()
    if doi:
        signatures.append("doi:" + doi)
    if record.type == "note":
        signatures.append("note:" + _note_text(record.note)[:500])
    elif record.type == "attachment":
        signatures.append("file:" + _fold(record.filename or record.title or record.url))
    elif _fold(record.title):
        signatures.append(f"title:{_fold(record.title)}|{year_of(record.date) or ''}")
    return signatures


def _same_child(local: Record, server: Record) -> bool:
    if local.type != server.type:
        return False
    if local.type == "note":
        return _note_text(local.note) == _note_text(server.note)
    if local.md5 and server.md5 and local.md5 != server.md5:
        return False
    for left, right in ((local.filename, server.filename), (local.url, server.url), (local.title, server.title)):
        if left and _fold(left) == _fold(right):
            return True
    return False


def plan(local: dict[str, Record], server: dict[str, Record]) -> Plan:
    result = Plan()
    server_children, local_children = _children(server), _children(local)
    by_signature: dict[str, list[str]] = {}
    for record in _tops(server):
        for signature in _top_signatures(record):
            by_signature.setdefault(signature, []).append(record.key)
    local_by_signature: dict[str, list[str]] = {}
    for record in _tops(local):
        for signature in _top_signatures(record):
            local_by_signature.setdefault(signature, []).append(record.key)

    taken: set[str] = set()
    paired_local: set[str] = set()
    pairs: list[tuple[Record, Record]] = []
    # Already under its own key, and the same paper: nothing to pair.
    for record in _tops(local):
        same = server.get(record.key)
        if same is not None and same.key not in taken and set(_top_signatures(record)) & set(_top_signatures(same)):
            taken.add(same.key)
            paired_local.add(record.key)
            pairs.append((record, same))
    for record in sorted(_tops(local), key=lambda r: r.key):
        if record.key in paired_local:
            continue
        found = None
        for signature in _top_signatures(record):
            free = [key for key in by_signature.get(signature, []) if key not in taken]
            if not free:
                continue
            if len(free) > 1 or len(local_by_signature.get(signature, [])) > 1:
                # Copies of one paper: told apart by their children's files.
                def names(children: list[Record], by_md5: bool) -> set[str]:
                    return {(c.md5 if by_md5 and c.type == "attachment" else _fold(c.filename) or _note_text(c.note)) for c in children}

                fitting, twins = [], []
                # The files' md5s first, where every attachment on both sides
                # has one (copies of a paper often share a file name, rarely
                # a file), then the file names and notes.
                for by_md5 in (True, False):
                    unpaired = [k for k in local_by_signature.get(signature, []) if k not in paired_local]
                    group = [local_children.get(k, []) for k in unpaired]
                    group += [server_children.get(k, []) for k in free]
                    if by_md5 and not all(c.md5 for children in group for c in children if c.type == "attachment"):
                        continue
                    mine = names(local_children.get(record.key, []), by_md5)
                    fitting = [k for k in free if names(server_children.get(k, []), by_md5) == mine]
                    twins = [k for k in unpaired if names(local_children.get(k, []), by_md5) == mine]
                    if len(fitting) == 1 and len(twins) == 1:
                        break
                if len(fitting) >= 2 and len(fitting) == len(twins):
                    # Copies alike in every way the two sides can see:
                    # whichever goes where, each ends up the same.
                    result.twins += 1
                    fitting = sorted(fitting)[:1]
                elif len(fitting) != 1 or len(twins) != 1:
                    result.ambiguous.append(record.key)
                    found = None
                    break
                free = fitting
            found = server[free[0]]
            break
        if found is None:
            if record.key not in result.ambiguous:
                result.unpaired_local.append(record.key)
            continue
        taken.add(found.key)
        paired_local.add(record.key)
        pairs.append((record, found))

    for local_top, server_top in pairs:
        tree = [(local_top, server_top)]
        free_children = list(server_children.get(server_top.key, []))
        for child in sorted(local_children.get(local_top.key, []), key=lambda c: c.key not in server):
            same = next((c for c in free_children if c.key == child.key and _same_child(child, c)), None)
            match = same or next((c for c in free_children if _same_child(child, c)), None)
            if match is not None:
                free_children.remove(match)
                tree.append((child, match))
        moves = []
        for local_record, server_record in tree:
            result.paired += 1
            move: dict[str, Any] = {"from": server_record.key}
            if local_record.key != server_record.key:
                move["to"] = local_record.key
                result.rekeyed += 1
            dates = {name: value for name, value in (("dateAdded", local_record.added), ("dateModified", local_record.modified))
                     if value and value != getattr(server_record, "added" if name == "dateAdded" else "modified")}
            if dates:
                move["set"] = dates
                result.dated += 1
            if "to" in move or "set" in move:
                moves.append(move)
            taken.add(server_record.key)
        if moves:
            result.trees.append(moves)
            result.moves.extend(moves)
    result.unpaired_server = sorted(key for key in server if key not in taken)
    return result


# -- sending -------------------------------------------------------------------


def apply(remote: Remote, mended: Plan, dry_run: bool = False) -> dict[str, Any]:
    """Send the moves, whole trees per call. -> counts by status, and the
    first few refusals."""
    counts: dict[str, int] = {}
    refusals: list[str] = []
    files = 0
    batch: list[dict[str, Any]] = []

    def send() -> None:
        nonlocal files
        if not batch:
            return
        reply = remote.post_json(MOVE_PATH, {"items": batch, "dry_run": dry_run}, timeout=300)
        for row in reply.get("results") or []:
            counts[row.get("status", "?")] = counts.get(row.get("status", "?"), 0) + 1
            files += 1 if row.get("files") else 0
            if row.get("error") and len(refusals) < 20:
                refusals.append(f"{row.get('from')} -> {row.get('to')}: {row['error']}")
        batch.clear()

    for tree in mended.trees:
        if len(batch) + len(tree) > BATCH:
            send()
        batch.extend(tree)
    send()
    return {"statuses": counts, "files": files, "errors": refusals, "dry_run": dry_run}


UPLOAD_PATH = "/api/library/attachments/upload"
UPLOAD_PIECE = 4 * 1024 * 1024  # the server's chunk_bytes


def _stored_file(storage: Path, key: str, filename: str) -> Path | None:
    """The local Zotero's file for an attachment: storage/<KEY>/<filename>,
    matched however the disk wrote its accents."""
    folder = storage / key
    if not folder.is_dir() or not filename:
        return None
    wanted = unicodedata.normalize("NFC", filename)
    for entry in folder.iterdir():
        if entry.is_file() and unicodedata.normalize("NFC", entry.name) == wanted:
            return entry
    return None


def plan_files(local: dict[str, Record], server: dict[str, Record], storage: Path) -> list[tuple[str, Path]]:
    """Server attachments that only link to a file (an import that did not
    carry it) whose file the local Zotero has under the same key."""
    out = []
    for key, record in sorted(server.items()):
        if record.type != "attachment" or record.link != "linked_file" or key not in local:
            continue
        found = _stored_file(storage, key, local[key].filename)
        if found is not None:
            out.append((key, found))
    return out


def upload_files(remote: Remote, files: list[tuple[str, Path]]) -> dict[str, Any]:
    """Each file in pieces; the last piece makes the item an imported file."""
    done, errors = 0, []
    for key, path in files:
        data = path.read_bytes()
        name = unicodedata.normalize("NFC", path.name)
        try:
            for offset in range(0, max(len(data), 1), UPLOAD_PIECE):
                params = {"key": key, "filename": name, "size": len(data), "offset": offset, "mtime": int(path.stat().st_mtime * 1000)}
                try:
                    reply = remote.post_bytes(UPLOAD_PATH, params, data[offset:offset + UPLOAD_PIECE], timeout=300)
                except RemoteError as error:
                    if getattr(error, "status", 0) not in (502, 503, 504, 520, 522, 524):
                        raise
                    # A proxy's passing failure: the same piece again is harmless.
                    reply = remote.post_bytes(UPLOAD_PATH, params, data[offset:offset + UPLOAD_PIECE], timeout=300)
            done += 1 if reply.get("done") else 0
        except RemoteError as error:
            if len(errors) < 20:
                errors.append(f"{key}: {error}")
    return {"uploaded": done, "errors": errors}


def mend(cfg: Any, send: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """The whole job from config.yaml: library.zotero_dir is the local
    Zotero, library.remote_* the server. send=False only plans; with send,
    dry_run asks the server what it would do without changing anything."""
    import tempfile

    library = cfg.library
    if not library.remote_url or not library.remote_key:
        raise RemoteError("library.remote_url and library.remote_key are not set")
    remote = Remote(library.remote_url, library.remote_key, library.remote_library)
    with tempfile.TemporaryDirectory(prefix="prma-mend-") as scratch:
        # A copy of zotero.sqlite of its own, apart from the server's.
        local_library = Library(library.zotero_dir, Path(scratch))
        local = read_local(local_library)
        local_collections = read_local_collections(local_library)
    server = read_server(remote)
    mended = plan(local, server)
    report: dict[str, Any] = {"local": len(local), "server": len(server), **mended.summary()}
    collection_moves, collection_counts = plan_collections(local_collections, read_server_collections(remote))
    report["collections"] = {"local": len(local_collections), **collection_counts, "moves": len(collection_moves)}
    if send and mended.moves:
        report["sent"] = apply(remote, mended, dry_run=dry_run)
    if send and collection_moves:
        report["collections"]["sent"] = apply_collections(remote, collection_moves, dry_run=dry_run)
    # Files only once every key is mended: they pair by key.
    files = plan_files(local, server, Path(library.zotero_dir).expanduser() / "storage") if not mended.moves else []
    report["linked_files"] = {"found_locally": len(files)}
    if send and files and not dry_run:
        report["linked_files"]["sent"] = upload_files(remote, files)
    return report
