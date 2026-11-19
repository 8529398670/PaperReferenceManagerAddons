"""The citation-graph crawl: a best-first spider over OpenAlex from your
library, looking for papers you do not have. Ported from the old prma
src/crawler/crawler.py.

A paper matching your keywords points two ways into the region you care
about: back through what it cites (older, foundational) and forward through
what cites it (newer, downstream). A work reached from several places is
likelier to be on topic than any single hit, so how often it is reached
counts toward its score:

    score = alpha * keyword hits + beta * log10(cites + 1) + gamma * incoming links

Keyword hits are how many of a saved search's terms (its query's words and
its any / all groups' terms) a work's title, abstract and journal hold.

Seeds are library papers with at least min_seed_hits; their neighbours come
from the missing pool, which already holds every library paper's references
and citers, so the first step costs nothing. Further out each visited work
costs one request for its record and references, one per 50 references, and
one for its 200 most-cited citers, out of api_budget. Every work fetched is
kept per WID (<content dir>/_crawl/works/), so a second run is cheap.

The result -- the novel works (not in the library, with at least
min_novel_hits) and every work visited, each with its score, depth and the
work it was reached from -- is kept per saved search and shown on the
Missing screen.
"""
from __future__ import annotations

import heapq
import json
import math
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from app.content import openalex
from app.extras import searches as ss
from app.search import query as q

MAX_RESULTS = 2000


@dataclass
class Settings:
    max_visits: int = 500
    max_depth: int = 2
    min_seed_hits: int = 1
    min_novel_hits: int = 2
    api_budget: int = 1000
    keyword_weight: float = 1.0
    cite_weight: float = 0.4
    link_weight: float = 0.5
    cited_by: bool = True

    def check(self) -> list[str]:
        problems = []
        if not 1 <= self.max_visits <= 5000:
            problems.append("max_visits must be 1-5000")
        if not 0 <= self.max_depth <= 4:
            problems.append("max_depth must be 0-4")
        if not 0 <= self.min_seed_hits <= 50 or not 0 <= self.min_novel_hits <= 50:
            problems.append("min_seed_hits and min_novel_hits must be 0-50")
        if not 0 <= self.api_budget <= 20000:
            problems.append("api_budget must be 0-20000")
        if any(not 0 <= w <= 10 for w in (self.keyword_weight, self.cite_weight, self.link_weight)):
            problems.append("weights must be 0-10")
        return problems


def hits_in(hay: str, terms: list[str]) -> int:
    """How many terms the folded haystack holds, each a phrase whose last
    word may be a prefix (as the search box matches)."""
    padded = " " + hay
    return sum(1 for term in terms if (" " + term) in padded)


def haystack(work: dict[str, Any]) -> str:
    return q.fold(" ".join(str(work.get(k) or "") for k in ("title", "abstract", "journal")))


class Cache:
    """Each work the crawl met, by WID: {work (compact), refs, citers}. refs
    and citers are None until fetched."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, wid: str) -> Path:
        return self.folder / wid[-2:] / f"{wid}.json"

    def get(self, wid: str) -> dict[str, Any] | None:
        try:
            return json.loads(self.path(wid).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, wid: str, entry: dict[str, Any]) -> None:
        path = self.path(wid)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)


class Crawl:
    """One run: everything it needs passed in, so it is testable without a
    server. Progress goes to report(visited, novel, api_used)."""

    def __init__(self, settings: Settings, terms: list[str], seeds: list[tuple[str, str, dict[str, Any]]],
                 neighbours: Callable[[str], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
                 client: openalex.Client | None, cache: Cache, in_library: Callable[[dict[str, Any]], bool],
                 report: Callable[[int, int, int], None] = lambda *_: None, stop: Callable[[], bool] = lambda: False) -> None:
        self.s = settings
        self.terms = terms
        # (library key, its wid, its compact work)
        self.seeds = seeds
        # library key -> (its references, its citers), from the pool
        self.neighbours = neighbours
        self.client = client
        self.cache = cache
        self.in_library = in_library
        self.report = report
        self.stop = stop
        self.budget = settings.api_budget
        self.errors: list[str] = []

    def score(self, work: dict[str, Any], links: int) -> tuple[float, int]:
        hits = hits_in(haystack(work), self.terms)
        return (self.s.keyword_weight * hits + self.s.cite_weight * math.log10((work.get("cited_by") or 0) + 1)
                + self.s.link_weight * links), hits

    def _spend(self) -> bool:
        if self.client is None or self.budget <= 0:
            return False
        self.budget -= 1
        return True

    def _expand(self, wid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """A visited external work's references and citers, cache first."""
        entry = self.cache.get(wid) or {}
        refs: list[dict[str, Any]] = []
        citers: list[dict[str, Any]] = []
        try:
            ref_ids = entry.get("refs")
            if ref_ids is None and self._spend():
                work, ref_ids = self.client.work_with_refs(wid)
                entry["work"] = work
                entry["refs"] = ref_ids
                self.cache.put(wid, entry)
            missing = []
            for rid in ref_ids or []:
                cached = self.cache.get(rid)
                if cached and cached.get("work"):
                    refs.append(cached["work"])
                else:
                    missing.append(rid)
            for start in range(0, len(missing), openalex.BATCH):
                if not self._spend():
                    break
                for work in self.client.works(missing[start:start + openalex.BATCH]):
                    refs.append(work)
                    old = self.cache.get(work["wid"]) or {}
                    self.cache.put(work["wid"], {**old, "work": work})
            if self.s.cited_by:
                citer_ids = entry.get("citers")
                if citer_ids is None and self._spend():
                    found = self.client.citing_top(wid)
                    for work in found:
                        old = self.cache.get(work["wid"]) or {}
                        self.cache.put(work["wid"], {**old, "work": work})
                    entry["citers"] = [w["wid"] for w in found]
                    self.cache.put(wid, entry)
                    citers = found
                else:
                    for cid in citer_ids or []:
                        cached = self.cache.get(cid)
                        if cached and cached.get("work"):
                            citers.append(cached["work"])
        except openalex.NotFound:
            entry.setdefault("refs", [])
            entry.setdefault("citers", [])
            self.cache.put(wid, entry)
        except openalex.Unavailable as error:
            self.errors.append(f"{wid}: {error}")
        return refs, citers

    def run(self) -> dict[str, Any]:
        started = time.time()
        frontier: list[tuple[float, int, str, int]] = []
        best: dict[str, float] = {}
        links: dict[str, int] = {}
        depth_of: dict[str, int] = {}
        works: dict[str, dict[str, Any]] = {}
        via: dict[str, dict[str, str]] = {}
        library_key: dict[str, str] = {}
        visited: list[str] = []
        seen: set[str] = set()
        novel: dict[str, float] = {}
        counter = 0

        def push(work: dict[str, Any], depth: int, parent: str = "", how: str = "") -> None:
            nonlocal counter
            wid = work.get("wid") or ""
            if not wid.startswith("W"):
                return
            works.setdefault(wid, work)
            value, hits = self.score(works[wid], links.get(wid, 0))
            if wid not in best or value > best[wid]:
                best[wid] = value
                depth_of[wid] = min(depth, depth_of.get(wid, depth))
                if parent:
                    via[wid] = {"from": parent, "how": how}
                heapq.heappush(frontier, (-value, counter, wid, depth))
                counter += 1
            if hits >= self.s.min_novel_hits and wid not in library_key and not self.in_library(works[wid]):
                novel[wid] = max(value, novel.get(wid, value))

        seeded = 0
        for key, wid, work in self.seeds:
            if hits_in(haystack(work), self.terms) < self.s.min_seed_hits:
                continue
            seeded += 1
            library_key[wid] = key
            push(work, 0)

        while frontier and len(visited) < self.s.max_visits and not self.stop():
            _, _, wid, depth = heapq.heappop(frontier)
            if wid in seen:
                continue
            seen.add(wid)
            visited.append(wid)
            self.report(len(visited), len(novel), self.s.api_budget - self.budget)
            if depth >= self.s.max_depth:
                continue
            if wid in library_key:
                refs, citers = self.neighbours(library_key[wid])
            else:
                refs, citers = self._expand(wid)
            for kind, found in (("cites", refs), ("cited by", citers)):
                for work in found:
                    other = work.get("wid") or ""
                    if not other or other in seen:
                        continue
                    links[other] = links.get(other, 0) + 1
                    push(work, depth + 1, wid, kind)

        def row(wid: str) -> dict[str, Any]:
            work = works.get(wid, {})
            value, hits = self.score(work, links.get(wid, 0))
            parent = via.get(wid, {})
            from_work = works.get(parent.get("from", ""), {})
            return {
                "wid": wid, "doi": work.get("doi") or "", "title": work.get("title") or "", "journal": work.get("journal") or "",
                "year": work.get("year"), "cited_by": work.get("cited_by") or 0, "oa_pdf": work.get("oa_pdf") or "",
                "authors": [a[1] for a in work.get("authors") or [] if len(a) > 1][:12],
                "score": round(best.get(wid, value), 3), "hits": hits, "links": links.get(wid, 0), "depth": depth_of.get(wid, 0),
                "from": parent.get("from", ""), "from_title": from_work.get("title") or "", "how": parent.get("how", ""),
                "from_key": library_key.get(parent.get("from", ""), ""), "seed_key": library_key.get(wid, ""),
            }

        novel_rows = sorted((row(w) for w in novel), key=lambda r: -r["score"])[:MAX_RESULTS]
        visited_rows = sorted((row(w) for w in visited), key=lambda r: -r["score"])[:MAX_RESULTS]
        return {
            "settings": asdict(self.s), "terms": self.terms, "seeds": seeded, "visited": len(visited), "novel": len(novel),
            "api_used": self.s.api_budget - self.budget, "errors": self.errors[:50], "stopped": self.stop(),
            "started_at": started, "finished_at": time.time(), "novel_rows": novel_rows, "visited_rows": visited_rows,
        }


class Crawler:
    """Runs one crawl at a time on its own thread, keeps each saved search's
    last result, and says how far it has got."""

    def __init__(self, folder: Path, content: Any, catalogue: Any, saved: ss.SavedSearches,
                 api_key: Callable[[], str], publish: Callable[[str, dict[str, Any]], None] = lambda n, d: None) -> None:
        self.folder = folder
        self.cache = Cache(folder / "works")
        self.content = content
        self.catalogue = catalogue
        self.saved = saved
        self.api_key = api_key
        self.publish = publish
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = False
        self.state: dict[str, Any] = {"running": False}

    def results_path(self, search_id: str) -> Path:
        return self.folder / "runs" / f"{search_id}.json"

    def result(self, search_id: str) -> dict[str, Any] | None:
        try:
            return json.loads(self.results_path(search_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def runs(self) -> list[dict[str, Any]]:
        """Each kept result's summary, newest first."""
        out = []
        for path in (self.folder / "runs").glob("*.json"):
            found = self.result(path.stem)
            if found:
                out.append({k: v for k, v in found.items() if not k.endswith("_rows")})
        return sorted(out, key=lambda r: -(r.get("finished_at") or 0))

    def status(self) -> dict[str, Any]:
        return dict(self.state)

    def start(self, search: dict[str, Any], settings: Settings, by: str, catalogue: Any = None,
              identity: tuple[set[str], set[str], set[str]] | None = None) -> bool:
        """False when a crawl is already running. catalogue is the library it
        starts from and identity (wids, dois, folded titles) what counts as
        in it: the starter's own (default the server's)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop = False
            self.state = {"running": True, "search_id": search["id"], "search": search["name"], "visited": 0, "novel": 0,
                          "api_used": 0, "max_visits": settings.max_visits, "started_at": time.time(), "by": by}
            self._thread = threading.Thread(target=self._run, args=(search, settings, by, catalogue, identity), name="crawl", daemon=True)
            self._thread.start()
        self.publish("crawl", self.status())
        return True

    def stop(self) -> None:
        self._stop = True

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _seeds(self, catalogue: Any = None) -> list[tuple[str, str, dict[str, Any]]]:
        """Every library paper with an OpenAlex id, as a compact work."""
        out = []
        for paper in (catalogue if catalogue is not None else self.catalogue).all():
            wid = self.content.wid_of(paper.key)
            if not wid:
                continue
            record = paper.record
            out.append((paper.key, wid, {
                "wid": wid, "doi": record.get("doi") or "", "title": record.get("title") or "", "journal": record.get("journal") or "",
                "abstract": record.get("abstract") or "", "year": record.get("year"), "cited_by": 0, "authors": [],
            }))
        return out

    def _neighbours(self, key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        pool = self.content.pool
        edges = pool.edges_of(key)
        found = pool.compact_of(edges.get("ref", []) + edges.get("cite", []))
        return [found[w] for w in edges.get("ref", []) if w in found], [found[w] for w in edges.get("cite", []) if w in found]

    def _run(self, search: dict[str, Any], settings: Settings, by: str, catalogue: Any = None,
             identity: tuple[set[str], set[str], set[str]] | None = None) -> None:
        last = [0.0]

        def report(visited: int, novel: int, api: int) -> None:
            self.state.update(visited=visited, novel=novel, api_used=api)
            now = time.monotonic()
            if now - last[0] > 1.0:
                last[0] = now
                self.publish("crawl", self.status())

        wids, dois, titles = identity if identity is not None else self.content.pool.library

        def in_library(work: dict[str, Any]) -> bool:
            return work.get("wid") in wids or (work.get("doi") or "").lower() in dois or q.fold(work.get("title")) in titles

        try:
            key = self.api_key()
            crawl = Crawl(settings, ss.keywords(search), self._seeds(catalogue), self._neighbours,
                          openalex.Client(key) if settings.api_budget > 0 else None, self.cache, in_library, report, lambda: self._stop)
            found = crawl.run()
            found.update(search_id=search["id"], search=search["name"], by=by)
            path = self.results_path(search["id"])
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(found, separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)
            self.state = {"running": False, "search_id": search["id"], "search": search["name"], "visited": found["visited"],
                          "novel": found["novel"], "api_used": found["api_used"], "finished_at": found["finished_at"], "error": ""}
        except Exception as error:  # noqa: BLE001 -- a failed crawl is reported, never takes the server down
            self.state = {"running": False, "search_id": search["id"], "search": search["name"], "error": str(error) or repr(error),
                          "finished_at": time.time()}
        self.publish("crawl", self.status())
