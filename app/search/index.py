"""The search index: a SQLite file of its own, updated one paper at a time.

It holds two things:

  docs      one row per paper: its key, the signatures of what was indexed
            (metadata and full text, separately), and the paper's record as
            JSON, so a restart has the whole catalogue without reading Zotero's
            full text again.
  body_fts  an FTS5 table of each paper's folded full text, rowid = docs.id.

Titles, authors and abstracts are matched in memory (see catalogue.py); only
the full text, 180 MB for a few thousand papers, needs an index. Adding,
changing or removing one paper touches one row of each -- there is no rebuild.

This file is derived data. It lives under <app dir>/cache/, outside storage/,
so backups leave it out; delete it and the next start fills it again from
Zotero. It is not encrypted: the text is the papers' own, and encrypted rows
cannot be searched.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1


class Index:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = NORMAL")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            # Derived data: a different shape is simply rebuilt.
            self._db.execute("DROP TABLE IF EXISTS docs")
            self._db.execute("DROP TABLE IF EXISTS body_fts")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, "
            "meta_sig TEXT NOT NULL, text_sig TEXT NOT NULL, data TEXT NOT NULL)"
        )
        self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS body_fts USING fts5(body, tokenize = 'unicode61 remove_diacritics 2')")
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- reading ---------------------------------------------------------------

    def load(self) -> list[tuple[int, str, str, str, dict[str, Any]]]:
        """(id, key, meta_sig, text_sig, record) for every paper."""
        with self._lock:
            rows = self._db.execute("SELECT id, key, meta_sig, text_sig, data FROM docs").fetchall()
        return [(row[0], row[1], row[2], row[3], json.loads(row[4])) for row in rows]

    def body_match(self, expression: str) -> set[int]:
        """The doc ids whose full text matches an FTS5 expression."""
        with self._lock:
            rows = self._db.execute("SELECT rowid FROM body_fts WHERE body_fts MATCH ?", (expression,)).fetchall()
        return {row[0] for row in rows}

    # -- writing ---------------------------------------------------------------

    def put_meta(self, key: str, meta_sig: str, record: dict[str, Any]) -> int:
        """Insert or update a paper's record. A new paper starts with no text
        (text_sig ""), which put_text fills in when it gets there. Answers the
        doc id."""
        data = json.dumps(record, separators=(",", ":"))
        with self._lock:
            self._db.execute(
                "INSERT INTO docs (key, meta_sig, text_sig, data) VALUES (?, ?, '', ?) "
                "ON CONFLICT (key) DO UPDATE SET meta_sig = excluded.meta_sig, data = excluded.data",
                (key, meta_sig, data),
            )
            return self._db.execute("SELECT id FROM docs WHERE key = ?", (key,)).fetchone()[0]

    def put_text(self, doc_id: int, text_sig: str, folded_body: str) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute("DELETE FROM body_fts WHERE rowid = ?", (doc_id,))
                if folded_body:
                    self._db.execute("INSERT INTO body_fts (rowid, body) VALUES (?, ?)", (doc_id, folded_body))
                self._db.execute("UPDATE docs SET text_sig = ? WHERE id = ?", (text_sig, doc_id))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def delete(self, keys: Iterable[str]) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for key in keys:
                    row = self._db.execute("SELECT id FROM docs WHERE key = ?", (key,)).fetchone()
                    if row is None:
                        continue
                    self._db.execute("DELETE FROM body_fts WHERE rowid = ?", (row[0],))
                    self._db.execute("DELETE FROM docs WHERE id = ?", (row[0],))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")


def fts_phrase(term: str, prefix: bool) -> str:
    """One folded term as an FTS5 phrase. Folded text is only [a-z0-9 ], so
    it never needs escaping; the quotes keep a term like "or" literal."""
    expression = '"' + term + '"'
    return expression + " *" if prefix else expression
