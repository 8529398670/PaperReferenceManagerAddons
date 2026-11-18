"""The missing pool: the papers you do not have. Works your library cites
(in bibliographies) and works citing your library (newer / citing), filled
one library paper at a time as its OpenAlex stage lands. There is no build:

  - put_paper(key, refs, citers) replaces that paper's edges, and the
    counters of the works on either side move by one;
  - drop_paper(key) takes them back out; a work nothing points at leaves;
  - a work that turns out to be a library paper (same OpenAlex id, DOI or
    folded title) is marked in_lib and leaves every list, and comes back
    if that paper is removed.

Tables, in search.db beside the library's (derived, rebuilt from the
per-paper network files if the file is deleted):

  works      one row per external work: what a row shows, and its counters.
             lib_cites: how many library papers cite it; cites_lib: how many
             library papers it cites. Connections is their sum.
  edges      (library paper, work, kind): what put_paper replaces.
  works_fts  folded title (column 0) and abstract + journal + authors + DOI
             (column 1), rowid = works.id, for the same boolean search as the
             library.
  filled     which library paper's network is in, at which signature.

Each work also keeps its abstract and its abstract-only review (the Review
screen's Missing pool, app/review/missing.py): rv_sig is the screener rules'
signature it was screened under, '' when it never was or its abstract
changed, so a rules change or a new work is screened again in the
background, a batch at a time, and nothing else is.

Old: src/dashboard/indexer.py, which rebuilt all of this on `prma reindex`.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.search import query as q
from app.search.index import fts_phrase

POOL_VERSION = 2
# The abstract-only review of a work (rv_state).
RV_OUT = 0  # excluded
RV_IN = 1  # included
RV_NEAR = 2  # excluded, failing exactly one criterion
RV_NO_TEXT = 3  # no abstract to screen
MAX_ABSTRACT = 6000  # longer is a parsing accident
REFS = "ref"
CITES = "cite"
POOLS = ("all", "refs", "citing")
# Sortable columns: what the page may name, and the SQL each stands for.
SORTS = {
    "relevance": "h.score",
    "conn": "(w.lib_cites + w.cites_lib)",
    "cited_by": "w.cited_by",
    "title": "w.title_f",
    "year": "coalesce(w.year, 0)",
}
AUTHORS_TOP = 100
AUTHORS_STALE_SECONDS = 20


class Pool:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = NORMAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS pool_meta (name TEXT PRIMARY KEY, value TEXT)")
        row = self._db.execute("SELECT value FROM pool_meta WHERE name = 'version'").fetchone()
        upgrade = row is not None and row[0] == "1"
        if row is None or (row[0] != str(POOL_VERSION) and not upgrade):
            for table in ("works", "edges", "works_fts", "filled"):
                self._db.execute(f"DROP TABLE IF EXISTS {table}")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS works (id INTEGER PRIMARY KEY, wid TEXT UNIQUE NOT NULL, doi TEXT NOT NULL DEFAULT '',"
            " title TEXT NOT NULL DEFAULT '', title_f TEXT NOT NULL DEFAULT '', journal TEXT NOT NULL DEFAULT '', year INTEGER,"
            " pubdate TEXT NOT NULL DEFAULT '', cited_by INTEGER NOT NULL DEFAULT 0, oa_pdf TEXT NOT NULL DEFAULT '',"
            " authors TEXT NOT NULL DEFAULT '[]', lib_cites INTEGER NOT NULL DEFAULT 0, cites_lib INTEGER NOT NULL DEFAULT 0,"
            " in_lib INTEGER NOT NULL DEFAULT 0, abstract TEXT NOT NULL DEFAULT '', rv_sig TEXT NOT NULL DEFAULT '', rv_state INTEGER,"
            " rv_reason TEXT NOT NULL DEFAULT '', rv TEXT NOT NULL DEFAULT '')"
        )
        if upgrade:
            # Version 1 kept no abstract and no review. The columns go in where
            # the works are, and every library paper's network is put in again
            # (backfill, from its network file), which brings the abstracts;
            # the Missing screen keeps working meanwhile.
            have = {r[1] for r in self._db.execute("PRAGMA table_info(works)").fetchall()}
            for column, kind in (("abstract", "TEXT NOT NULL DEFAULT ''"), ("rv_sig", "TEXT NOT NULL DEFAULT ''"), ("rv_state", "INTEGER"),
                                 ("rv_reason", "TEXT NOT NULL DEFAULT ''"), ("rv", "TEXT NOT NULL DEFAULT ''")):
                if column not in have:
                    self._db.execute(f"ALTER TABLE works ADD COLUMN {column} {kind}")
            self._db.execute("CREATE TABLE IF NOT EXISTS filled (lib_key TEXT PRIMARY KEY, sig TEXT NOT NULL)")
            self._db.execute("DELETE FROM filled")
        self._db.execute("CREATE INDEX IF NOT EXISTS works_doi ON works (doi)")
        self._db.execute("CREATE INDEX IF NOT EXISTS works_title ON works (title_f)")
        self._db.execute("CREATE INDEX IF NOT EXISTS works_rv ON works (rv_state, rv_sig)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS edges (lib_key TEXT NOT NULL, wid TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY (lib_key, wid, kind))"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS edges_wid ON edges (wid)")
        self._db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(title, body, tokenize = 'unicode61 remove_diacritics 2')"
        )
        self._db.execute("CREATE TABLE IF NOT EXISTS filled (lib_key TEXT PRIMARY KEY, sig TEXT NOT NULL)")
        self._db.execute("INSERT OR REPLACE INTO pool_meta (name, value) VALUES ('version', ?)", (str(POOL_VERSION),))
        # Who the library is, for dedup: set by the content service from the
        # catalogue, (wids, dois lowercased, folded titles).
        self.library: tuple[set[str], set[str], set[str]] = (set(), set(), set())
        self.rev = 0
        self._authors: list[dict[str, Any]] = []
        self._authors_at = 0.0
        self._authors_rev = -1
        self._authors_skips = 0

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- filling -----------------------------------------------------------------

    def filled(self) -> dict[str, str]:
        with self._lock:
            return dict(self._db.execute("SELECT lib_key, sig FROM filled").fetchall())

    def _is_lib(self, wid: str, doi: str, title_f: str) -> int:
        wids, dois, titles = self.library
        return int(wid in wids or (bool(doi) and doi.lower() in dois) or (bool(title_f) and title_f in titles))

    def put_paper(self, key: str, sig: str, refs: Sequence[dict[str, Any]], citers: Sequence[dict[str, Any]]) -> None:
        """Replace one library paper's edges with these works."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._drop(key)
                for kind, works in ((REFS, refs), (CITES, citers)):
                    column = "lib_cites" if kind == REFS else "cites_lib"
                    seen = set()
                    for work in works:
                        wid = work.get("wid") or ""
                        if not wid.startswith("W") or wid in seen:
                            continue
                        seen.add(wid)
                        self._upsert(work)
                        self._db.execute("INSERT OR IGNORE INTO edges (lib_key, wid, kind) VALUES (?, ?, ?)", (key, wid, kind))
                        self._db.execute(f"UPDATE works SET {column} = {column} + 1 WHERE wid = ?", (wid,))
                self._db.execute("INSERT OR REPLACE INTO filled (lib_key, sig) VALUES (?, ?)", (key, sig))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            self.rev += 1

    def drop_paper(self, keys: Iterable[str]) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for key in keys:
                    self._drop(key)
                    self._db.execute("DELETE FROM filled WHERE lib_key = ?", (key,))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            self.rev += 1

    def _drop(self, key: str) -> None:
        edges = self._db.execute("SELECT wid, kind FROM edges WHERE lib_key = ?", (key,)).fetchall()
        if not edges:
            return
        for wid, kind in edges:
            column = "lib_cites" if kind == REFS else "cites_lib"
            self._db.execute(f"UPDATE works SET {column} = max({column} - 1, 0) WHERE wid = ?", (wid,))
        self._db.execute("DELETE FROM edges WHERE lib_key = ?", (key,))
        orphans = self._db.execute(
            f"SELECT id FROM works WHERE lib_cites = 0 AND cites_lib = 0 AND wid IN ({','.join('?' * len(edges))})",
            [wid for wid, _ in edges],
        ).fetchall() if len(edges) < 900 else self._db.execute("SELECT id FROM works WHERE lib_cites = 0 AND cites_lib = 0").fetchall()
        for (work_id,) in orphans:
            self._db.execute("DELETE FROM works_fts WHERE rowid = ?", (work_id,))
            self._db.execute("DELETE FROM works WHERE id = ?", (work_id,))

    def _upsert(self, work: dict[str, Any]) -> None:
        wid = work["wid"]
        doi = (work.get("doi") or "").lower()
        title = work.get("title") or ""
        title_f = q.fold(title)
        authors = [list(a) for a in (work.get("authors") or [])][:60]
        abstract = str(work.get("abstract") or "").strip()[:MAX_ABSTRACT]
        values = (
            doi, title, title_f, work.get("journal") or "", work.get("year"), work.get("pubdate") or "",
            int(work.get("cited_by") or 0), work.get("oa_pdf") or "", json.dumps(authors, separators=(",", ":")),
            self._is_lib(wid, doi, title_f), abstract,
        )
        row = self._db.execute("SELECT id, title, abstract FROM works WHERE wid = ?", (wid,)).fetchone()
        if row is None:
            cursor = self._db.execute(
                "INSERT INTO works (wid, doi, title, title_f, journal, year, pubdate, cited_by, oa_pdf, authors, in_lib, abstract) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (wid, *values),
            )
            work_id = cursor.lastrowid
        else:
            work_id = row[0]
            # What the review read moved: it is screened again.
            moved = row[1] != title or row[2] != abstract
            self._db.execute(
                "UPDATE works SET doi = ?, title = ?, title_f = ?, journal = ?, year = ?, pubdate = ?, cited_by = ?, oa_pdf = ?, "
                "authors = ?, in_lib = ?, abstract = ?" + (", rv_sig = ''" if moved else "") + " WHERE id = ?",
                (*values, work_id),
            )
            self._db.execute("DELETE FROM works_fts WHERE rowid = ?", (work_id,))
        body = " ".join(
            part for part in (
                q.fold(work.get("abstract")), q.fold(work.get("journal")), q.fold(" ".join(a[1] for a in authors if len(a) > 1)), q.fold(doi),
            ) if part
        )
        self._db.execute("INSERT INTO works_fts (rowid, title, body) VALUES (?, ?, ?)", (work_id, title_f, body))

    # -- the library, for dedup ----------------------------------------------------

    def set_library(self, wids: set[str], dois: set[str], titles: set[str]) -> None:
        """The library's identity moved: mark what is now in it, unmark what
        no longer is. Only the works whose answer changed are touched."""
        old_wids, old_dois, old_titles = self.library
        self.library = (wids, dois, titles)
        gained = [("wid", w) for w in wids - old_wids] + [("doi", d) for d in dois - old_dois] + [("title_f", t) for t in titles - old_titles]
        lost = [("wid", w) for w in old_wids - wids] + [("doi", d) for d in old_dois - dois] + [("title_f", t) for t in old_titles - titles]
        if not gained and not lost:
            return
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for column, value in gained:
                    self._db.execute(f"UPDATE works SET in_lib = 1 WHERE {column} = ? AND in_lib = 0", (value,))
                for column, value in lost:
                    for work_id, wid, doi, title_f in self._db.execute(
                        f"SELECT id, wid, doi, title_f FROM works WHERE {column} = ? AND in_lib = 1", (value,)
                    ).fetchall():
                        if not self._is_lib(wid, doi, title_f):
                            self._db.execute("UPDATE works SET in_lib = 0 WHERE id = ?", (work_id,))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            self.rev += 1

    # -- the abstract-only review ------------------------------------------------------

    def review_due(self, sig: str, limit: int) -> list[tuple[int, str, str]]:
        """(id, title, abstract) of works not screened under these rules."""
        with self._lock:
            return self._db.execute(
                "SELECT id, title, abstract FROM works WHERE in_lib = 0 AND rv_sig != ? LIMIT ?", (sig, limit)
            ).fetchall()

    def review_store(self, sig: str, results: Sequence[tuple[int, int, str, str]]) -> None:
        """(id, state, reason code, summary JSON) per work screened."""
        if not results:
            return
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany(
                    "UPDATE works SET rv_sig = ?, rv_state = ?, rv_reason = ?, rv = ? WHERE id = ?",
                    [(sig, state, reason, rv, work_id) for work_id, state, reason, rv in results],
                )
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def review_tally(self, sig: str) -> dict[str, Any]:
        """How far the screen has got under these rules, and what it found:
        {total, screened, by_state: {state: n}, reasons: {code: n}}."""
        with self._lock:
            total = self._db.execute("SELECT count(*) FROM works WHERE in_lib = 0").fetchone()[0]
            states = self._db.execute(
                "SELECT rv_state, count(*) FROM works WHERE in_lib = 0 AND rv_sig = ? GROUP BY rv_state", (sig,)
            ).fetchall()
            reasons = self._db.execute(
                "SELECT rv_reason, count(*) FROM works WHERE in_lib = 0 AND rv_sig = ? AND rv_state IN (?, ?) GROUP BY rv_reason",
                (sig, RV_OUT, RV_NEAR),
            ).fetchall()
        by_state = {int(s): n for s, n in states if s is not None}
        return {"total": total, "screened": sum(by_state.values()), "by_state": by_state,
                "reasons": dict(sorted(((r or "", n) for r, n in reasons), key=lambda kv: -kv[1]))}

    def review_rows(self, sig: str, state: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        """The works the screen put in one state, nearest your library first
        (connections, then citations, then newest). -> (rows, how many in all)."""
        with self._lock:
            n = self._db.execute(
                "SELECT count(*) FROM works WHERE in_lib = 0 AND rv_sig = ? AND rv_state = ?", (sig, state)
            ).fetchone()[0]
            found = self._db.execute(
                "SELECT wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, lib_cites, cites_lib, rv FROM works "
                "WHERE in_lib = 0 AND rv_sig = ? AND rv_state = ? "
                "ORDER BY (lib_cites + cites_lib) DESC, cited_by DESC, coalesce(year, 0) DESC, id ASC LIMIT ?",
                (sig, state, limit),
            ).fetchall()
        rows = []
        for wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, lib_cites, cites_lib, rv in found:
            try:
                summary = json.loads(rv) if rv else {}
            except ValueError:
                summary = {}
            names = [a[1] for a in json.loads(authors or "[]") if len(a) > 1]
            rows.append({
                "wid": wid, "doi": doi, "title": title, "journal": journal, "year": year, "pubdate": pubdate, "cited_by": cited_by,
                "oa_pdf": oa_pdf, "authors": names[:3], "n_authors": len(names), "lib_cites": lib_cites, "cites_lib": cites_lib,
                "conn": lib_cites + cites_lib, **summary,
            })
        return rows, n

    def work_text(self, wid: str) -> tuple[str, str] | None:
        """(title, abstract) of a work."""
        with self._lock:
            row = self._db.execute("SELECT title, abstract FROM works WHERE wid = ?", (wid,)).fetchone()
        return (row[0], row[1]) if row else None

    # -- searching -------------------------------------------------------------------

    def _match_expression(self, clauses: Sequence[q.Clause]) -> str:
        """The boolean query as one FTS5 expression. A clause with no positive
        term ("-eeg" alone) has nothing to match against in FTS5, so it means
        "everything but", and is answered separately."""
        parts = []
        for clause in clauses:
            if not clause.pos:
                continue
            expression = " AND ".join(fts_phrase(term, prefix=True) for term in clause.pos)
            if clause.neg:
                expression = f"({expression}) NOT ({' OR '.join(fts_phrase(term, prefix=True) for term in clause.neg)})"
            parts.append(f"({expression})")
        return " OR ".join(parts)

    def search(
        self,
        text: str = "",
        pool: str = "all",
        sort: Sequence[tuple[str, bool]] = (("conn", True),),
        skipped: set[str] | None = None,
        show_skipped: bool = False,
        paper: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """A page of the pool, and the tab counts for the same search.
        sort: [(column, descending)], the first one primary."""
        skipped = skipped or set()
        folded = q.fold(text)
        clauses = q.parse(text) if folded else []
        with self._lock:
            self._db.execute("CREATE TEMP TABLE IF NOT EXISTS hits (id INTEGER PRIMARY KEY, score REAL)")
            self._db.execute("DELETE FROM temp.hits")
            searching = bool(clauses)
            if searching:
                expression = self._match_expression(clauses)
                if expression:
                    # bm25 is lower-is-better; the title counts ten times the
                    # body, and an exact or leading title match beats both, as
                    # the library's ranking does.
                    self._db.execute(
                        "INSERT OR REPLACE INTO temp.hits (id, score) SELECT f.rowid, -bm25(works_fts, 10.0, 1.0) "
                        "+ CASE WHEN w.title_f = ? THEN 1000 WHEN w.title_f LIKE ? THEN 100 ELSE 0 END "
                        "FROM works_fts f JOIN works w ON w.id = f.rowid WHERE works_fts MATCH ?",
                        (folded, folded.replace("%", "") + "%", expression),
                    )
                for clause in clauses:
                    if clause.pos or not clause.neg:
                        continue
                    exclude = " OR ".join(fts_phrase(term, prefix=True) for term in clause.neg)
                    self._db.execute(
                        "INSERT OR IGNORE INTO temp.hits (id, score) SELECT id, 0 FROM works WHERE id NOT IN "
                        "(SELECT rowid FROM works_fts WHERE works_fts MATCH ?)",
                        (exclude,),
                    )
            where = ["w.in_lib = 0"]
            args: list[Any] = []
            if searching:
                join = "JOIN temp.hits h ON h.id = w.id"
            else:
                join = "LEFT JOIN temp.hits h ON h.id = w.id"
            if paper:
                where.append("w.wid IN (SELECT wid FROM edges WHERE lib_key = ?)")
                args.append(paper)
            skip_list = sorted(skipped)
            skip_sql = ""
            if skip_list:
                skip_sql = f"w.wid IN ({','.join('?' * len(skip_list))})"
            base_where = " AND ".join(where)
            counts_where = base_where + (f" AND NOT {skip_sql}" if skip_sql and not show_skipped else "")
            counts_args = args + (skip_list if skip_sql and not show_skipped else [])
            row = self._db.execute(
                f"SELECT count(*), coalesce(sum(w.lib_cites > 0), 0), coalesce(sum(w.cites_lib > 0), 0) FROM works w {join} WHERE {counts_where}",
                counts_args,
            ).fetchone()
            counts = {"all": row[0], "refs": row[1], "citing": row[2]}
            skipped_count = 0
            if skip_sql:
                skipped_count = self._db.execute(
                    f"SELECT count(*) FROM works w {join} WHERE {base_where} AND {skip_sql}", args + skip_list
                ).fetchone()[0]
            page_where = counts_where
            if pool == "refs":
                page_where += " AND w.lib_cites > 0"
            elif pool == "citing":
                page_where += " AND w.cites_lib > 0"
            order = []
            for column, descending in sort:
                if column not in SORTS or (column == "relevance" and not searching):
                    continue
                order.append(f"{SORTS[column]} {'DESC' if descending else 'ASC'}")
            order.append("w.id ASC")
            found = self._db.execute(
                f"SELECT w.wid, w.doi, w.title, w.journal, w.year, w.pubdate, w.cited_by, w.oa_pdf, w.authors, w.lib_cites, w.cites_lib, h.score "
                f"FROM works w {join} WHERE {page_where} ORDER BY {', '.join(order)} LIMIT ? OFFSET ?",
                counts_args + [limit, offset],
            ).fetchall()
        rows = []
        for wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, lib_cites, cites_lib, score in found:
            rows.append({
                "wid": wid, "doi": doi, "title": title, "journal": journal, "year": year, "pubdate": pubdate,
                "cited_by": cited_by, "oa_pdf": oa_pdf, "authors": [a[1] for a in json.loads(authors or "[]") if len(a) > 1][:12],
                "lib_cites": lib_cites, "cites_lib": cites_lib, "conn": lib_cites + cites_lib,
                "score": round(score, 2) if searching and score is not None else None, "skipped": wid in skipped,
            })
        return {"rows": rows, "counts": counts, "skipped": skipped_count, "total": counts.get(pool, counts["all"])}

    # Saved searches (app/extras/searches.py) work on row ids: an FTS hit is
    # a rowid already, and sets of ints are cheap to intersect.

    def term_ids(self, term: str) -> set[int]:
        """The works holding one folded term (its last word a prefix) in their
        title, abstract, journal, authors or DOI. Library works included:
        intersect with universe_ids()."""
        folded = q.fold(term)
        if not folded:
            return set()
        with self._lock:
            found = self._db.execute("SELECT rowid FROM works_fts WHERE works_fts MATCH ?", (fts_phrase(folded, prefix=True),)).fetchall()
        return {row[0] for row in found}

    def query_ids(self, text: str) -> set[int]:
        """The works a boolean query matches (the Missing screen's grammar)."""
        clauses = q.parse(text)
        everything = self.universe_ids()
        if not clauses:
            return set(everything)
        hits: set[int] = set()
        cache: dict[str, set[int]] = {}
        for clause in clauses:
            chosen = set(everything)
            for term in clause.pos:
                chosen &= cache.setdefault(term, self.term_ids(term))
            for term in clause.neg:
                chosen -= cache.setdefault(term, self.term_ids(term))
            hits |= chosen
        return hits

    def universe_ids(self) -> frozenset[int]:
        """Every work not in the library, kept until the pool moves."""
        cached = getattr(self, "_universe", None)
        if cached is not None and cached[0] == self.rev:
            return cached[1]
        with self._lock:
            ids = frozenset(row[0] for row in self._db.execute("SELECT id FROM works WHERE in_lib = 0").fetchall())
        self._universe = (self.rev, ids)
        return ids

    def ids_of(self, wids: Iterable[str]) -> set[int]:
        wanted = list(wids)
        out: set[int] = set()
        with self._lock:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                out.update(row[0] for row in self._db.execute(f"SELECT id FROM works WHERE wid IN ({','.join('?' * len(chunk))})", chunk))
        return out

    def top_of(self, ids: Iterable[int], limit: int) -> list[str]:
        """The wids of these works, nearest your library first (connections,
        then citations, then newest), at most limit."""
        with self._lock:
            self._db.execute("CREATE TEMP TABLE IF NOT EXISTS pick (id INTEGER PRIMARY KEY)")
            self._db.execute("DELETE FROM temp.pick")
            self._db.executemany("INSERT OR IGNORE INTO temp.pick (id) VALUES (?)", ((i,) for i in ids))
            found = self._db.execute(
                "SELECT w.wid FROM works w JOIN temp.pick p ON p.id = w.id "
                "ORDER BY (w.lib_cites + w.cites_lib) DESC, w.cited_by DESC, coalesce(w.year, 0) DESC, w.id ASC LIMIT ?", (limit,),
            ).fetchall()
            self._db.execute("DELETE FROM temp.pick")
        return [row[0] for row in found]

    def all_wids(self) -> set[str]:
        with self._lock:
            return {row[0] for row in self._db.execute("SELECT wid FROM works WHERE in_lib = 0").fetchall()}

    def works_by_wid(self, wids: Iterable[str]) -> list[dict[str, Any]]:
        """Rows for these works, as search() makes them (no score)."""
        wanted = list(dict.fromkeys(wids))
        out: list[dict[str, Any]] = []
        with self._lock:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                out.extend(self._db.execute(
                    "SELECT wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, lib_cites, cites_lib FROM works "
                    f"WHERE wid IN ({','.join('?' * len(chunk))})", chunk,
                ).fetchall())
        rows = []
        for wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, lib_cites, cites_lib in out:
            rows.append({
                "wid": wid, "doi": doi, "title": title, "journal": journal, "year": year, "pubdate": pubdate,
                "cited_by": cited_by, "oa_pdf": oa_pdf, "authors": [a[1] for a in json.loads(authors or "[]") if len(a) > 1][:12],
                "lib_cites": lib_cites, "cites_lib": cites_lib, "conn": lib_cites + cites_lib,
            })
        return rows

    def ranked(self, order: str, limit: int, skipped: set[str] | None = None) -> list[dict[str, Any]]:
        """The top works by one order: "conn" (connections, then citations),
        "newest" (publication date) or "cited_by" (OpenAlex citations). Skipped
        works are left out. For the missing.xlsx sheets."""
        orders = {
            "conn": "(lib_cites + cites_lib) DESC, cited_by DESC, coalesce(year, 0) DESC",
            "newest": "pubdate DESC, coalesce(year, 0) DESC, (lib_cites + cites_lib) DESC",
            "cited_by": "cited_by DESC, (lib_cites + cites_lib) DESC",
        }
        skipped = skipped or set()
        with self._lock:
            found = self._db.execute(
                f"SELECT wid FROM works WHERE in_lib = 0 ORDER BY {orders[order]}, id ASC LIMIT ?", (limit + len(skipped),)
            ).fetchall()
        wids = [row[0] for row in found if row[0] not in skipped][:limit]
        by_wid = {row["wid"]: row for row in self.works_by_wid(wids)}
        return [by_wid[w] for w in wids if w in by_wid]

    def work(self, wid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT wid, doi, title, journal, year, cited_by, oa_pdf, authors, lib_cites, cites_lib FROM works WHERE wid = ?", (wid,)
            ).fetchone()
        if row is None:
            return None
        return {"wid": row[0], "doi": row[1], "title": row[2], "journal": row[3], "year": row[4], "cited_by": row[5],
                "oa_pdf": row[6], "authors": [a[1] for a in json.loads(row[7] or "[]") if len(a) > 1], "lib_cites": row[8], "cites_lib": row[9]}

    def network_counts(self, key: str) -> dict[str, int]:
        with self._lock:
            found = self._db.execute(
                "SELECT e.kind, count(*), coalesce(sum(w.in_lib), 0) FROM edges e JOIN works w ON w.wid = e.wid WHERE e.lib_key = ? GROUP BY e.kind",
                (key,),
            ).fetchall()
        out = {"refs": 0, "refs_in_lib": 0, "citers": 0, "citers_in_lib": 0}
        for kind, n, in_lib in found:
            if kind == REFS:
                out["refs"], out["refs_in_lib"] = n, in_lib
            else:
                out["citers"], out["citers_in_lib"] = n, in_lib
        return out

    def totals(self) -> dict[str, int]:
        with self._lock:
            row = self._db.execute(
                "SELECT count(*), coalesce(sum(lib_cites > 0), 0), coalesce(sum(cites_lib > 0), 0) FROM works WHERE in_lib = 0"
            ).fetchone()
            papers = self._db.execute("SELECT count(*) FROM filled").fetchone()[0]
        return {"all": row[0], "refs": row[1], "citing": row[2], "papers": papers}

    def authors(self, skipped: set[str] | None = None) -> list[dict[str, Any]]:
        """The top authors of the in-bibliographies pool, by summed connections
        then paper count (the old build_authors). Worked out from the stored
        counters when the pool has moved, and at most every few seconds."""
        now = time.monotonic()
        fresh = self._authors_rev == self.rev and self._authors_skips == len(skipped or ())
        if self._authors_rev != -1 and (fresh or now - self._authors_at < AUTHORS_STALE_SECONDS):
            return self._authors
        with self._lock:
            found = self._db.execute("SELECT wid, authors, lib_cites FROM works WHERE in_lib = 0 AND lib_cites > 0").fetchall()
            rev = self.rev
        skipped = skipped or set()
        papers: dict[str, int] = {}
        cites: dict[str, int] = {}
        info: dict[str, tuple[str, str]] = {}
        for wid, authors, lib_cites in found:
            if wid in skipped:
                continue
            for author in json.loads(authors or "[]"):
                if len(author) < 2 or not author[0]:
                    continue
                aid = author[0]
                papers[aid] = papers.get(aid, 0) + 1
                cites[aid] = cites.get(aid, 0) + lib_cites
                if aid not in info:
                    info[aid] = (author[1] or "", author[2] if len(author) > 2 else "")
        ranked = sorted(cites, key=lambda aid: (cites[aid], papers[aid]), reverse=True)[:AUTHORS_TOP]
        self._authors = [
            {"openalex": aid, "name": info[aid][0], "orcid": info[aid][1] or "", "papers": papers[aid], "lib_cites": cites[aid]} for aid in ranked
        ]
        self._authors_at = now
        self._authors_rev = rev
        self._authors_skips = len(skipped)
        return self._authors


def parse_sort(spec: str) -> list[tuple[str, bool]]:
    """"conn:desc,year:desc" -> [("conn", True), ("year", True)]. Unknown
    columns are dropped; a column named twice keeps its first place."""
    out: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for part in (spec or "").split(","):
        name, _, direction = part.strip().partition(":")
        if name in SORTS and name not in seen:
            seen.add(name)
            out.append((name, direction != "asc"))
    return out or [("conn", True)]


Identity = Callable[[], tuple[set[str], set[str], set[str]]]
