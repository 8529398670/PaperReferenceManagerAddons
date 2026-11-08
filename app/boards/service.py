"""The running lists: how ops reach the library, and the live stream that
tells every open page "list X is at rev N now" so it fetches the list again.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.boards import ops, store as boards
from app.core import db, sse
from app.library.catalogue import Catalogue
from app.search import query as q

RESOLVE_THRESHOLD = 96


class BoardService:
    def __init__(self, store: db.Store, catalogue: Catalogue) -> None:
        self.store = store
        self.catalogue = catalogue
        self.hub = sse.Hub(max_clients=32)
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    def stop(self) -> None:
        self.hub.close()

    def changed(self, slug: str, rev: int, by: str) -> None:
        """Tell open pages. Safe from any thread."""
        message = sse.event("list", json.dumps({"slug": slug, "rev": rev, "by": by}))
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
        """What ops ask about papers: whether each is in the library. Modality
        tags and code/dataset links arrive with the content stages (phase 4)."""
        out = {}
        for key in keys:
            paper = self.catalogue.get(key)
            if paper is not None:
                out[key] = {"in_library": True}
        return out

    def ctx(self) -> ops.Ctx:
        return ops.Ctx(resolve=self.resolve, meta=self.meta)

    # -- the rows as the page draws them ---------------------------------------

    def papers_for(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Per row key, what the library knows now: whether it is there, has a
        PDF, has searchable text. The row itself keeps what it was added with,
        so a paper deleted from Zotero still reads right on the list."""
        out = {}
        for row in (doc.get("items") or []) + (doc.get("staging") or []):
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
                }
        return out

    def view(self, record: dict[str, Any]) -> dict[str, Any]:
        doc = record["doc"]
        return {**boards.summary(record), "doc": doc, "papers": self.papers_for(doc)}
