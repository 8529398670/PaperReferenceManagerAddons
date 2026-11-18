"""The library as the app sees it: every paper in Zotero, in memory, kept in
step with Zotero by sync(), and searchable.

There is no import step and no reindex. sync() is cheap when nothing changed
(a stat of three files); when Zotero committed, it reads the library (a third
of a second for a few thousand papers), compares each paper's signature with
what it last saw, and touches only what was added, changed or removed. That
happens in two passes, so a new paper is listed and findable by its title at
once, and its full text -- Zotero's own extraction of the PDF, which it may
write a little later -- lands in the index when it is there.

Everything here is synchronous: the watcher runs sync() in a worker thread,
and requests read through snapshots of the current state, never a dict that
is being changed under them.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.library.zotero import Item, Library, normalize_doi
from app.search import query as q
from app.search.index import Index, fts_phrase

# A full look at every extracted-text file, even when zotero.sqlite has not
# changed: Zotero writes those without a commit of its own.
TEXT_RECHECK_SECONDS = 60
# How often to tell the page how far the text pass has got.
PROGRESS_EVERY = 50

# The fields a list shows, and what the page may sort by.
SORTS = ("relevance", "added", "year", "title")
TITLE_THRESHOLD = 96


@dataclass
class Paper:
    """One paper: the record shown and the folded text matched against."""

    doc_id: int
    record: dict[str, Any]
    meta_sig: str
    text_sig: str
    title_f: str = ""
    head_f: str = ""
    ident_f: str = ""
    has_text: bool = False

    @property
    def key(self) -> str:
        return self.record["key"]


def _fold_fields(paper: Paper) -> None:
    record = paper.record
    paper.title_f = q.fold(record.get("title"))
    paper.ident_f = q.fold(" ".join([record.get("doi") or "", record.get("key") or "", record.get("zkey") or ""]))
    paper.head_f = " ".join(
        part
        for part in (
            paper.title_f,
            q.fold(" ".join(record.get("authors") or [])),
            q.fold(record.get("journal")),
            q.fold(" ".join(record.get("tags") or [])),
            paper.ident_f,
            q.fold(record.get("abstract")),
        )
        if part
    )


def public(paper: Paper, full: bool = False) -> dict[str, Any]:
    """What the API hands out for a paper. The list carries what a row
    shows; full adds the abstract and the rest."""
    record = paper.record
    row = {
        "key": record["key"],
        "zkey": record.get("zkey", ""),
        "title": record.get("title", ""),
        "doi": record.get("doi", ""),
        "year": record.get("year"),
        "journal": record.get("journal", ""),
        "authors": record.get("authors", []),
        "added": record.get("date_added", ""),
        "tags": record.get("tags", []),
        "has_pdf": bool(record.get("pdfs")),
        "has_text": paper.has_text,
    }
    if full:
        row.update(
            {
                "abstract": record.get("abstract", ""),
                "url": record.get("url", ""),
                "type": record.get("type", ""),
                "collections": record.get("collections", []),
                "modified": record.get("date_modified", ""),
            }
        )
    return row


@dataclass
class SyncResult:
    added: int = 0
    changed: int = 0
    removed: int = 0
    texts: int = 0

    def any(self) -> bool:
        return bool(self.added or self.changed or self.removed or self.texts)

    def note(self) -> str:
        return f"{self.added} added, {self.changed} changed, {self.removed} removed, {self.texts} texts indexed"


@dataclass
class Status:
    """What the page shows about the library's state."""

    ready: bool = False
    papers: int = 0
    with_text: int = 0
    text_pending: int = 0
    error: str = ""
    last_sync: float = 0.0


@dataclass
class SearchResult:
    rows: list[Paper]
    fuzzy: bool = False
    scores: dict[str, int] = field(default_factory=dict)


class Catalogue:
    def __init__(self, library: Library, index: Index) -> None:
        self.library = library
        self.index = index
        self._papers: dict[str, Paper] = {}
        self._by_doc: dict[int, str] = {}
        self._dois: dict[str, str] = {}
        self._titles: dict[str, str] = {}
        self._title_list: list[str] = []
        self._sync_lock = threading.Lock()
        self._stamp: Any = None
        self._text_checked = 0.0
        self.rev = 0
        self.status = Status()
        # Hears "changed" (the list of papers moved on) and "progress" (the
        # text pass), from the sync thread. main points it at the SSE hub.
        self.on_event: Callable[[str, dict[str, Any]], None] | None = None
        # A paper's text when Zotero extracted none (a scanned PDF): the
        # worker's OCR, from app/content. key -> text, "" for none.
        self.text_fallback: Callable[[str], str] | None = None

    # -- reading ---------------------------------------------------------------

    def load(self) -> None:
        """What the index already holds, so the first page after a restart
        needs nothing from Zotero."""
        papers: dict[str, Paper] = {}
        for doc_id, key, meta_sig, text_sig, record in self.index.load():
            paper = Paper(doc_id=doc_id, record=record, meta_sig=meta_sig, text_sig=text_sig)
            paper.has_text = bool(record.get("_has_text"))
            _fold_fields(paper)
            papers[key] = paper
        self._replace(papers)
        self.status.ready = bool(papers)

    def get(self, key: str) -> Paper | None:
        return self._papers.get(key)

    def all(self) -> list[Paper]:
        return list(self._papers.values())

    def version(self) -> str:
        """The userscripts' cheap "has anything changed" token."""
        return f"{self.rev}:{len(self._titles)}:{len(self._dois)}"

    def _replace(self, papers: dict[str, Paper]) -> None:
        dois: dict[str, str] = {}
        titles: dict[str, str] = {}
        for key, paper in papers.items():
            doi = (paper.record.get("doi") or "").lower()
            if doi:
                dois.setdefault(doi, key)
            if paper.title_f:
                titles.setdefault(paper.title_f, key)
        # Swapped in whole, so a request mid-search keeps the old view intact.
        self._papers = papers
        self._by_doc = {paper.doc_id: key for key, paper in papers.items()}
        self._dois = dois
        self._titles = titles
        self._title_list = list(titles)
        self.status.papers = len(papers)
        self.status.with_text = sum(1 for paper in papers.values() if paper.has_text)

    # -- keeping up with Zotero ------------------------------------------------

    def sync(self, force: bool = False) -> SyncResult | None:
        """Bring the catalogue up to date with Zotero. None when there was
        nothing to look at. Safe to call often; one runs at a time."""
        if not self._sync_lock.acquire(blocking=False):
            return None
        try:
            return self._sync(force)
        finally:
            self._sync_lock.release()

    def _sync(self, force: bool) -> SyncResult | None:
        stamp = self.library.stamp()
        if stamp is None:
            self.status.error = f"no Zotero library at {self.library.sqlite_path}"
            return None
        recheck_text = time.monotonic() - self._text_checked >= TEXT_RECHECK_SECONDS
        if not force and stamp == self._stamp and not recheck_text:
            return None
        items = self.library.read()
        self._stamp = stamp
        self._text_checked = time.monotonic()
        self.status.error = ""
        result = SyncResult()

        papers = dict(self._papers)
        for key, item in items.items():
            meta_sig = item.meta_signature()
            existing = papers.get(key)
            if existing is not None and existing.meta_sig == meta_sig:
                continue
            record = item.to_dict()
            record["_has_text"] = existing.has_text if existing else False
            doc_id = self.index.put_meta(key, meta_sig, record)
            paper = Paper(doc_id=doc_id, record=record, meta_sig=meta_sig, text_sig=existing.text_sig if existing else "")
            paper.has_text = record["_has_text"]
            _fold_fields(paper)
            papers[key] = paper
            if existing is None:
                result.added += 1
            else:
                result.changed += 1

        # A read that had to leave the -wal out is behind, not a sign that
        # papers were deleted.
        if not self.library.read_fell_back:
            gone = [key for key in papers if key not in items]
            if gone:
                self.index.delete(gone)
                for key in gone:
                    del papers[key]
                result.removed = len(gone)

        if result.added or result.changed or result.removed:
            self._replace(papers)
            self.status.ready = True
            self.rev += 1
            self._emit("changed", {"rev": self.rev})

        # The second pass: full text, newest papers first, so what was just
        # saved is searchable before the backlog.
        pending = [
            (items[key], paper)
            for key, paper in papers.items()
            if key in items and paper.text_sig != items[key].text_signature()
        ]
        pending.sort(key=lambda pair: pair[0].date_added, reverse=True)
        self.status.text_pending = len(pending)
        for done, (item, paper) in enumerate(pending, start=1):
            text_sig = item.text_signature()
            body = q.fold(item.read_fulltext())
            if not body and self.text_fallback is not None:
                body = q.fold(self.text_fallback(paper.key))
            self.index.put_text(paper.doc_id, text_sig, body)
            paper.text_sig = text_sig
            has_text = bool(body)
            if has_text != paper.has_text:
                paper.has_text = has_text
                paper.record["_has_text"] = has_text
                self.index.put_meta(paper.key, paper.meta_sig, paper.record)
            result.texts += 1
            self.status.text_pending = len(pending) - done
            if done % PROGRESS_EVERY == 0 or done == len(pending):
                self.status.with_text = sum(1 for p in self._papers.values() if p.has_text)
                self._emit("progress", {"done": done, "total": len(pending)})
        if result.texts:
            self.rev += 1
            self._emit("changed", {"rev": self.rev})
        self.status.last_sync = time.time()
        return result

    def put_text(self, key: str, text: str) -> None:
        """Search a paper by this text from now on (its OCR arrived), keeping
        its text signature, so the text pass does not redo it."""
        paper = self._papers.get(key)
        if paper is None or not text.strip():
            return
        self.index.put_text(paper.doc_id, paper.text_sig, q.fold(text))
        if not paper.has_text:
            paper.has_text = True
            paper.record["_has_text"] = True
            self.index.put_meta(paper.key, paper.meta_sig, paper.record)
            self.status.with_text = sum(1 for p in self._papers.values() if p.has_text)
        self.rev += 1
        self._emit("changed", {"rev": self.rev})

    def _emit(self, name: str, data: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(name, data)
            except Exception as error:  # noqa: BLE001 -- telling the page must never stop a sync
                print(f"[library] could not publish {name}: {error!r}", flush=True)

    # -- searching ---------------------------------------------------------------

    def search(self, text: str, mode: str = "text") -> SearchResult:
        """Every paper matching text, best first. mode "title" is the
        half-remembered-title lookup the boards use; "text" is the boolean
        full-text search."""
        papers = list(self._papers.values())
        folded = q.fold(text)
        if not folded:
            return SearchResult(rows=papers)
        if mode == "title":
            ranked, fuzzy = q.title_lookup(folded, [p.title_f for p in papers], [p.ident_f for p in papers])
            return SearchResult(rows=[papers[i] for i, _ in ranked], fuzzy=fuzzy, scores={papers[i].key: s for i, s in ranked})
        clauses = q.parse(text)
        if not clauses:
            return SearchResult(rows=papers)

        cache: dict[str, set[str]] = {}

        def matching(term: str) -> set[str]:
            if term not in cache:
                found = {p.key for p in papers if term in p.head_f}
                for doc_id in self.index.body_match(fts_phrase(term, prefix=True)):
                    key = self._by_doc.get(doc_id)
                    if key is not None:
                        found.add(key)
                cache[term] = found
            return cache[term]

        everything = {p.key for p in papers}
        hits: set[str] = set()
        for clause in clauses:
            chosen = set(everything)
            for term in clause.pos:
                chosen &= matching(term)
            for term in clause.neg:
                chosen -= matching(term)
            hits |= chosen

        if not hits:
            near = q.near_titles(folded, [p.title_f for p in papers])
            return SearchResult(rows=[papers[i] for i, _ in near], fuzzy=bool(near), scores={papers[i].key: s for i, s in near})

        terms = q.terms_of(clauses)
        in_body = set()
        if folded:
            for doc_id in self.index.body_match(fts_phrase(folded, prefix=False)):
                key = self._by_doc.get(doc_id)
                if key is not None:
                    in_body.add(key)
        scores = {}
        rows = []
        for paper in papers:
            if paper.key in hits:
                scores[paper.key] = q.relevance(paper.title_f, paper.head_f, paper.key in in_body, terms, folded)
                rows.append(paper)
        rows.sort(key=lambda p: scores[p.key], reverse=True)
        return SearchResult(rows=rows, scores=scores)

    def term_keys(self, term: str) -> set[str]:
        """The papers holding one folded term (a phrase, its last word a
        prefix), in their title, authors, journal, tags, abstract or full
        text: what one word of the search box matches. Saved searches build
        their groups from these."""
        folded = q.fold(term)
        if not folded:
            return set()
        found = {p.key for p in self._papers.values() if folded in p.head_f}
        for doc_id in self.index.body_match(fts_phrase(folded, prefix=True)):
            key = self._by_doc.get(doc_id)
            if key is not None:
                found.add(key)
        return found

    def query_keys(self, text: str) -> set[str]:
        """The papers a boolean query matches, with no near-title fallback."""
        if not q.parse(text):
            return {p.key for p in self._papers.values()}
        result = self.search(text)
        return set() if result.fuzzy else {p.key for p in result.rows}

    # -- does the library have it? ---------------------------------------------

    def exists(self, doi: str, title: str) -> bool:
        """The userscripts' question. A DOI settles it; a title is matched only
        when there is no DOI, exactly or at 96 (rapidfuzz token_sort_ratio)."""
        clean = normalize_doi(doi)
        if clean:
            return clean.lower() in self._dois
        folded = q.fold(title)
        if not folded:
            return False
        if folded in self._titles:
            return True
        from rapidfuzz import fuzz, process

        return process.extractOne(folded, self._title_list, scorer=fuzz.token_sort_ratio, processor=None, score_cutoff=TITLE_THRESHOLD) is not None

    def match(self, doi: str, title: str) -> tuple[Paper | None, str]:
        """The paper a reference names, and how it matched: "doi", "title" or
        "fuzzy". The /exists policy: a DOI settles it on its own (a reference
        whose DOI we lack is a paper we lack), and only without one is the
        title matched, exactly or at 96."""
        clean = normalize_doi(doi)
        if clean:
            key = self._dois.get(clean.lower())
            return (self._papers.get(key), "doi") if key else (None, "")
        folded = q.fold(title)
        if not folded:
            return None, ""
        if folded in self._titles:
            return self._papers.get(self._titles[folded]), "title"
        from rapidfuzz import fuzz, process

        best = process.extractOne(folded, self._title_list, scorer=fuzz.token_sort_ratio, processor=None, score_cutoff=TITLE_THRESHOLD)
        if best is None:
            return None, ""
        return self._papers.get(self._titles[best[0]]), "fuzzy"

    def find(self, spec: str) -> Paper | None:
        """A paper named by its key, its DOI, or its Zotero key."""
        spec = (spec or "").strip()
        if not spec:
            return None
        if spec in self._papers:
            return self._papers[spec]
        doi = normalize_doi(spec)
        if doi:
            key = self._dois.get(doi.lower())
            if key:
                return self._papers.get(key)
        for paper in self._papers.values():
            if paper.record.get("zkey") == spec:
                return paper
        return None


def sort_papers(rows: list[Paper], sort: str, descending: bool, scores: dict[str, int]) -> list[Paper]:
    """The list in the order the page asked for. Relevance only means
    something with a query; without one it falls back to newest added."""
    if sort in ("", "relevance") and scores:
        # Best first, always: "least relevant first" is not a useful list.
        return sorted(rows, key=lambda p: scores.get(p.key, 0), reverse=True)
    if sort in ("", "relevance"):
        return sorted(rows, key=lambda p: p.record.get("date_added") or "", reverse=True)
    if sort == "added":
        return sorted(rows, key=lambda p: p.record.get("date_added") or "", reverse=descending)
    if sort == "year":
        present = [p for p in rows if p.record.get("year")]
        absent = [p for p in rows if not p.record.get("year")]
        return sorted(present, key=lambda p: p.record["year"], reverse=descending) + absent
    if sort == "title":
        return sorted(rows, key=lambda p: p.title_f, reverse=descending)
    if sort in ("journal", "authors"):
        # Blank last either way, like year.
        def text(p: Paper) -> str:
            if sort == "journal":
                return (p.record.get("journal") or "").strip().lower()
            names = p.record.get("authors") or []
            return str(names[0]).strip().lower() if names else ""
        present = [p for p in rows if text(p)]
        absent = [p for p in rows if not text(p)]
        return sorted(present, key=text, reverse=descending) + absent
    return rows
