"""Reading a Zotero library, while Zotero has it open.

Zotero holds its database locked while it runs, so even a read-only sqlite
connection to the live file fails. The only way in is a byte copy, and a copy
is not atomic, so this module copies the main file together with whichever
sidecar holds the latest commits (the -wal in WAL mode, the -journal in
rollback mode) and checks a few header bytes either side of the copy to know
whether Zotero wrote while it was being read. A copy that never settles is
integrity-checked before it is trusted. Ported from the old prma
src/zotero/zotero.py, which learned all of this the hard way.

Nothing here writes to the Zotero folder.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

NO_DOI_PREFIX = "nodoi-"
SOURCE_ZOTERO = "zotero"

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
_DOI_TRAIL_RE = re.compile(
    r"/(figures?|tables?|abstract|full|epdf|pdf|fullpdf|references?|metrics|supplementary|suppl|media)(/.*)?$",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b")
FULLTEXT_CACHE = ".zotero-ft-cache"
# A whole book's text is not worth indexing past this; titles and abstracts
# carry the ranking anyway.
MAX_FULLTEXT_BYTES = 2 * 1024 * 1024


def normalize_doi(raw: Any) -> str | None:
    """A clean DOI found anywhere inside a string, or None. The same rules as
    the old prma, so keys made there still match here."""
    if not raw:
        return None
    value = str(raw).strip().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    match = _DOI_RE.search(value)
    if not match:
        return None
    doi = _DOI_TRAIL_RE.sub("", match.group(0))
    return doi.rstrip("./;:)")


def synthetic_key(item_key: Any) -> str:
    """The key of a paper with no DOI: nodoi-zotero-<item key>."""
    safe = re.sub(r"[^A-Za-z0-9]+", "-", str(item_key or "")).strip("-")
    return f"{NO_DOI_PREFIX}{SOURCE_ZOTERO}-{safe}"


def year_of(raw: Any) -> int | None:
    match = _YEAR_RE.search(str(raw or ""))
    return int(match.group(1)) if match else None


@dataclass
class Item:
    """One bibliographic item, as the app sees it."""

    key: str  # the paper's key: its DOI, or nodoi-zotero-<zkey>
    zkey: str
    item_id: int
    type: str
    title: str
    doi: str
    year: int | None
    journal: str
    abstract: str
    url: str
    date_added: str
    date_modified: str
    authors: list[str] = field(default_factory=list)
    creators: list[dict[str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    pdfs: list[str] = field(default_factory=list)
    # The full text Zotero extracted, one file per PDF attachment.
    fulltext_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "zkey": self.zkey,
            "item_id": self.item_id,
            "type": self.type,
            "title": self.title,
            "doi": self.doi,
            "year": self.year,
            "journal": self.journal,
            "abstract": self.abstract,
            "url": self.url,
            "date_added": self.date_added,
            "date_modified": self.date_modified,
            "authors": self.authors,
            "creators": self.creators,
            "tags": self.tags,
            "collections": self.collections,
            "pdfs": self.pdfs,
            "fulltext_files": self.fulltext_files,
        }

    def meta_signature(self) -> str:
        """Changes whenever anything shown about the paper changes."""
        return "\x1f".join(
            [self.date_modified, self.title, self.doi, self.journal, ",".join(self.tags), ",".join(self.collections), ",".join(self.pdfs)]
        )

    def text_signature(self) -> str:
        """Changes when Zotero (re)extracts a PDF's text, which it can do
        without touching the item itself: the size and mtime of each
        extracted-text file, "-" while there is none yet."""
        parts = []
        for name in self.fulltext_files:
            try:
                stat = os.stat(name)
                parts.append(f"{stat.st_size}:{int(stat.st_mtime)}")
            except OSError:
                parts.append("-")
        return "|".join(parts) or "none"

    def read_fulltext(self) -> str:
        chunks: list[str] = []
        budget = MAX_FULLTEXT_BYTES
        for name in self.fulltext_files:
            try:
                with open(name, "rb") as handle:
                    raw = handle.read(budget)
            except OSError:
                continue
            budget -= len(raw)
            chunks.append(raw.decode("utf-8", errors="replace"))
            if budget <= 0:
                break
        return "\n".join(chunks)


def _is_wal(header: bytes) -> bool:
    # Byte 18 is the file-format write version: 2 means WAL.
    return len(header) > 18 and header[18] == 2


class Library:
    """One Zotero folder. read() returns every item, keyed by paper key."""

    def __init__(self, zotero_dir: Path, copy_dir: Path) -> None:
        self.zotero_dir = zotero_dir
        self.sqlite_path = zotero_dir / "zotero.sqlite"
        self.storage = zotero_dir / "storage"
        self.copy_path = copy_dir / "zotero-copy.sqlite"
        self._lock = threading.Lock()
        # True when the last read had to leave the -wal out: that view can be
        # behind, so it must not be taken as papers having been removed.
        self.read_fell_back = False

    # -- change detection ----------------------------------------------------

    def stamp(self) -> tuple[Any, ...] | None:
        """Cheap: changes whenever Zotero commits. None when there is no
        library at all."""
        parts: list[Any] = []
        for suffix in ("", "-wal", "-journal"):
            try:
                stat = os.stat(str(self.sqlite_path) + suffix)
                parts.append((suffix, stat.st_size, stat.st_mtime_ns))
            except OSError:
                if suffix == "":
                    return None
                parts.append((suffix, None))
        return tuple(parts)

    # -- the copy ------------------------------------------------------------

    def _state_token(self) -> tuple[Any, ...] | None:
        try:
            with open(self.sqlite_path, "rb") as handle:
                header = handle.read(100)
            if len(header) < 100:
                return None
            stat = os.stat(self.sqlite_path)
            token: tuple[Any, ...] = (header[24:28], header[92:96], stat.st_size, stat.st_mtime_ns)
        except OSError:
            return None
        if _is_wal(header):
            try:
                with open(str(self.sqlite_path) + "-wal", "rb") as handle:
                    token += (handle.read(32),)
            except OSError:
                token += (None,)
        return token

    def _copy(self, with_wal: bool, attempts: int = 6) -> bool:
        """Copy the live database (and the sidecar in use). True once a copy
        settled: Zotero did not commit while it was read."""
        self.copy_path.parent.mkdir(parents=True, exist_ok=True)
        live_journal = Path(str(self.sqlite_path) + "-journal")
        live_wal = Path(str(self.sqlite_path) + "-wal")
        for attempt in range(attempts):
            if attempt:
                time.sleep(0.05 * attempt)
            for sidecar in ("-wal", "-shm", "-journal"):
                Path(str(self.copy_path) + sidecar).unlink(missing_ok=True)
            before = self._state_token()
            shutil.copyfile(self.sqlite_path, self.copy_path)
            with open(self.copy_path, "rb") as handle:
                wal_mode = _is_wal(handle.read(20))
            if wal_mode:
                if with_wal and live_wal.exists():
                    try:
                        shutil.copyfile(live_wal, str(self.copy_path) + "-wal")
                    except FileNotFoundError:
                        pass
            elif live_journal.exists():
                try:
                    shutil.copyfile(live_journal, str(self.copy_path) + "-journal")
                except FileNotFoundError:
                    pass
            after = self._state_token()
            if before is not None and before == after:
                return True
        return False

    def _connect(self, verify: bool) -> sqlite3.Connection:
        # Read-write on purpose: a hot -journal is rolled back and a -wal is
        # replayed on the first read, which the probe forces here.
        connection = sqlite3.connect(self.copy_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("SELECT count(*) FROM items").fetchone()
            if verify:
                ok = connection.execute("PRAGMA integrity_check(1)").fetchone()[0]
                if ok != "ok":
                    raise sqlite3.DatabaseError(f"copy taken mid-write fails integrity_check ({ok})")
        except Exception:
            connection.close()
            raise
        return connection

    def _open(self) -> sqlite3.Connection:
        self.read_fell_back = False
        try:
            settled = self._copy(with_wal=True)
            return self._connect(verify=not settled)
        except (OSError, sqlite3.Error) as error:
            print(f"[library] could not read zotero.sqlite with its -wal ({error}); reading the main file only", flush=True)
            self.read_fell_back = True
            settled = self._copy(with_wal=False)
            return self._connect(verify=not settled)

    # -- reading -------------------------------------------------------------

    def read(self) -> dict[str, Item]:
        with self._lock:
            connection = self._open()
            try:
                return self._read(connection)
            finally:
                connection.close()

    def _attachment_path(self, attach_key: str, path: str | None) -> Path | None:
        if not path:
            return None
        if path.startswith("storage:"):
            return self.storage / attach_key / path[len("storage:"):]
        if path.startswith("file:"):
            return Path(unquote(urlparse(path).path))
        if path.startswith("/"):
            return Path(path)
        return None

    def _read(self, connection: sqlite3.Connection) -> dict[str, Item]:
        cursor = connection.cursor()
        raw: dict[int, dict[str, Any]] = {}
        for row in cursor.execute(
            """
            SELECT items.itemID, items.key, itemTypes.typeName, items.dateAdded, items.dateModified
            FROM items
            JOIN itemTypes ON itemTypes.itemTypeID = items.itemTypeID
            LEFT JOIN deletedItems ON deletedItems.itemID = items.itemID
            WHERE deletedItems.itemID IS NULL
              AND itemTypes.typeName NOT IN ('attachment', 'note', 'annotation')
            """
        ):
            raw[row["itemID"]] = {
                "zkey": row["key"],
                "type": row["typeName"],
                "added": row["dateAdded"] or "",
                "modified": row["dateModified"] or "",
                "meta": {},
                "creators": [],
                "tags": [],
                "collections": [],
                "pdfs": [],
                "fulltext": [],
            }

        for row in cursor.execute(
            """
            SELECT itemData.itemID, fields.fieldName, itemDataValues.value
            FROM itemData
            JOIN fields ON fields.fieldID = itemData.fieldID
            JOIN itemDataValues ON itemDataValues.valueID = itemData.valueID
            """
        ):
            entry = raw.get(row["itemID"])
            if entry is not None:
                entry["meta"][row["fieldName"]] = row["value"]

        for row in cursor.execute(
            """
            SELECT itemCreators.itemID, creators.firstName, creators.lastName, creatorTypes.creatorType
            FROM itemCreators
            JOIN creators ON creators.creatorID = itemCreators.creatorID
            JOIN creatorTypes ON creatorTypes.creatorTypeID = itemCreators.creatorTypeID
            ORDER BY itemCreators.itemID, itemCreators.orderIndex
            """
        ):
            entry = raw.get(row["itemID"])
            if entry is not None:
                entry["creators"].append({"type": row["creatorType"], "first": row["firstName"] or "", "last": row["lastName"] or ""})

        for row in cursor.execute(
            """
            SELECT itemAttachments.parentItemID AS parent, items.key AS attach_key,
                   itemAttachments.path AS path, itemAttachments.contentType AS content_type
            FROM itemAttachments
            JOIN items ON items.itemID = itemAttachments.itemID
            LEFT JOIN deletedItems ON deletedItems.itemID = items.itemID
            WHERE deletedItems.itemID IS NULL
            ORDER BY itemAttachments.itemID
            """
        ):
            entry = raw.get(row["parent"])
            if entry is None:
                continue
            file_path = self._attachment_path(row["attach_key"], row["path"])
            is_pdf = (row["content_type"] == "application/pdf") or (file_path is not None and file_path.suffix.lower() == ".pdf")
            if file_path is not None and is_pdf:
                entry["pdfs"].append(str(file_path))
                cache = self.storage / row["attach_key"] / FULLTEXT_CACHE
                entry["fulltext"].append(str(cache))

        for row in cursor.execute("SELECT itemTags.itemID, tags.name FROM itemTags JOIN tags ON tags.tagID = itemTags.tagID"):
            entry = raw.get(row["itemID"])
            if entry is not None:
                entry["tags"].append(row["name"])

        for row in cursor.execute(
            """
            SELECT collectionItems.itemID, collections.collectionName
            FROM collectionItems
            JOIN collections ON collections.collectionID = collectionItems.collectionID
            """
        ):
            entry = raw.get(row["itemID"])
            if entry is not None:
                entry["collections"].append(row["collectionName"])

        items: dict[str, Item] = {}
        for item_id, entry in raw.items():
            meta = entry["meta"]
            doi = normalize_doi(meta.get("DOI")) or ""
            title = (meta.get("title") or "").strip()
            if not title and not doi and not entry["pdfs"]:
                continue  # an empty placeholder: nothing to show or key on
            key = doi or synthetic_key(entry["zkey"] or item_id)
            if key in items:
                # Two Zotero items with the same DOI: the first wins, as it
                # did in the old app. The second is still in Zotero.
                continue
            authors = [
                " ".join(part for part in (creator["first"], creator["last"]) if part)
                for creator in entry["creators"]
                if creator["type"] == "author"
            ]
            items[key] = Item(
                key=key,
                zkey=entry["zkey"] or "",
                item_id=item_id,
                type=entry["type"],
                title=title or doi,
                doi=doi,
                year=year_of(meta.get("date")),
                journal=(meta.get("publicationTitle") or meta.get("bookTitle") or meta.get("proceedingsTitle") or "").strip(),
                abstract=(meta.get("abstractNote") or "").strip(),
                url=(meta.get("url") or "").strip(),
                date_added=entry["added"],
                date_modified=entry["modified"],
                authors=[name for name in authors if name],
                creators=entry["creators"],
                tags=sorted(set(entry["tags"])),
                collections=sorted(set(entry["collections"])),
                pdfs=entry["pdfs"],
                fulltext_files=entry["fulltext"],
            )
        return items
