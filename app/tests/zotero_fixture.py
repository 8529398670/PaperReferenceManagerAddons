"""A small Zotero library on disk, for the tests: the tables and columns
app/library/zotero.py reads, and a storage/ folder with PDFs and Zotero's
extracted-text files. Nothing here touches a real Zotero."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT, dateAdded TEXT, dateModified TEXT,
                    clientDateModified TEXT, libraryID INT, key TEXT);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
CREATE TABLE itemCreators (itemID INT, creatorID INT, creatorTypeID INT, orderIndex INT);
CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, linkMode INT, contentType TEXT, path TEXT);
CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE itemTags (itemID INT, tagID INT);
CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT);
CREATE TABLE collectionItems (collectionID INT, itemID INT);
INSERT INTO itemTypes VALUES (1, 'journalArticle'), (2, 'attachment'), (3, 'note');
INSERT INTO fields VALUES (1, 'title'), (2, 'DOI'), (3, 'date'), (4, 'publicationTitle'), (5, 'abstractNote');
INSERT INTO creatorTypes VALUES (1, 'author'), (2, 'editor');
"""


class FakeZotero:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.storage = folder / "storage"
        self.storage.mkdir(parents=True, exist_ok=True)
        self.path = folder / "zotero.sqlite"
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        self._next = 1

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def _id(self) -> int:
        self._next += 1
        return self._next

    def add(
        self,
        title: str,
        doi: str = "",
        year: str = "2020",
        journal: str = "",
        abstract: str = "",
        authors: tuple[tuple[str, str], ...] = (),
        tags: tuple[str, ...] = (),
        text: str | None = None,
        added: str = "2026-01-01 00:00:00",
    ) -> str:
        """Adds a paper (and a PDF with extracted text when text is given).
        Answers its Zotero key."""
        item_id = self._id()
        key = f"ITEM{item_id:04d}"
        with self.connect() as c:
            c.execute("INSERT INTO items VALUES (?, 1, ?, ?, ?, 1, ?)", (item_id, added, added, added, key))
            for field_id, value in ((1, title), (2, doi), (3, year), (4, journal), (5, abstract)):
                if value:
                    value_id = self._id()
                    c.execute("INSERT INTO itemDataValues VALUES (?, ?)", (value_id, value))
                    c.execute("INSERT INTO itemData VALUES (?, ?, ?)", (item_id, field_id, value_id))
            for order, (first, last) in enumerate(authors):
                creator_id = self._id()
                c.execute("INSERT INTO creators VALUES (?, ?, ?)", (creator_id, first, last))
                c.execute("INSERT INTO itemCreators VALUES (?, ?, 1, ?)", (item_id, creator_id, order))
            for name in tags:
                tag_id = self._id()
                c.execute("INSERT INTO tags VALUES (?, ?)", (tag_id, name))
                c.execute("INSERT INTO itemTags VALUES (?, ?)", (item_id, tag_id))
            if text is not None:
                attach_id = self._id()
                attach_key = f"ATT{attach_id:05d}"
                c.execute("INSERT INTO items VALUES (?, 2, ?, ?, ?, 1, ?)", (attach_id, added, added, added, attach_key))
                c.execute("INSERT INTO itemAttachments VALUES (?, ?, 0, 'application/pdf', ?)", (attach_id, item_id, "storage:paper.pdf"))
                folder = self.storage / attach_key
                folder.mkdir()
                (folder / "paper.pdf").write_bytes(b"%PDF-1.4 test")
                (folder / ".zotero-ft-cache").write_text(text)
        return key

    def set_title(self, key: str, title: str, modified: str) -> None:
        with self.connect() as c:
            item_id = c.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()[0]
            value_id = self._id()
            c.execute("INSERT INTO itemDataValues VALUES (?, ?)", (value_id, title))
            c.execute("UPDATE itemData SET valueID = ? WHERE itemID = ? AND fieldID = 1", (value_id, item_id))
            c.execute("UPDATE items SET dateModified = ? WHERE itemID = ?", (modified, item_id))

    def delete(self, key: str) -> None:
        with self.connect() as c:
            item_id = c.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()[0]
            c.execute("INSERT INTO deletedItems VALUES (?)", (item_id,))

    def fulltext_path(self, key: str) -> Path:
        with self.connect() as c:
            item_id = c.execute("SELECT itemID FROM items WHERE key = ?", (key,)).fetchone()[0]
            attach = c.execute(
                "SELECT items.key FROM itemAttachments JOIN items ON items.itemID = itemAttachments.itemID WHERE parentItemID = ?",
                (item_id,),
            ).fetchone()[0]
        return self.storage / attach / ".zotero-ft-cache"


def sample(folder: Path) -> FakeZotero:
    """Three papers, two with full text."""
    zotero = FakeZotero(folder)
    zotero.add(
        "Temporal Autocorrelation in Univariate Linear Modeling of FMRI Data",
        doi="10.1006/nimg.2001.0931",
        year="2001",
        journal="NeuroImage",
        authors=(("Mark", "Woolrich"), ("Brian", "Ripley")),
        text="We describe prewhitening of the residuals. The decoding of inner speech is not discussed.",
        added="2026-01-01 10:00:00",
    )
    zotero.add(
        "MindAlign: Decoding Inner Speech from fMRI Signals",
        doi="10.48550/arXiv.2606.20696",
        year="2026",
        abstract="A transformer that aligns brain activity with text embeddings.",
        authors=(("Muxuan", "Liu"),),
        tags=("inner speech",),
        text="Participants imagined sentences in the scanner. EEG was not recorded.",
        added="2026-02-01 10:00:00",
    )
    zotero.add("A paper with no DOI about Ørsted and naïve café models", added="2026-03-01 10:00:00")
    return zotero
