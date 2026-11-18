"""OpenAlex, one paper at a time: its own record, the works it cites, and
every work citing it. Ported from the old prma src/openalex/api.py and
openalex.py, with what they learned kept:

  - a 404 is an answer, not a failure: OpenAlex merges duplicate works and
    deletes the loser's id, and an unindexed DOI is common. It is cached as
    "not found" and never asked again until someone presses Retry.
  - 429 means wait: Retry-After is honoured, with backoff when it is missing.
  - a paper with no DOI is looked up by its title, but only a close match is
    taken (the old code took the first result, marked "Todo").

What changed: cited_by is every page (cursor paging), not the top 200, and
references come in batches of 50 with only the fields the missing pool shows,
so a paper costs a few requests instead of one per reference.

No third-party HTTP library: urllib is enough for GETs of JSON.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.content import links
from app.library.zotero import normalize_doi
from app.search import query as q

BASE = "https://api.openalex.org/works"
USER_AGENT = "paper-reference-manager/1.0"
TIMEOUT_SECONDS = 30
MAX_TRIES = 5
# The longest a 429 is waited out inside one task; past it the task fails and
# the queue's own backoff takes over, so one paper never holds the lane all day.
MAX_WAIT_SECONDS = 120
BATCH = 50
PAGE = 200
# A cited_by list past this many pages is cut: a textbook cited 40,000 times
# would otherwise be 200 requests and 40,000 pool rows for one paper.
MAX_CITED_PAGES = 50
TITLE_MATCH = 92

# What the missing pool keeps of a work. abstract_inverted_index is large but
# it is the abstract, and the pool searches it.
COMPACT_FIELDS = (
    "id,doi,title,display_name,publication_year,publication_date,cited_by_count,"
    "authorships,best_oa_location,open_access,primary_location,abstract_inverted_index,type"
)


class NotFound(Exception):
    """OpenAlex has no such work."""


class Unavailable(Exception):
    """OpenAlex could not be asked: network, rate limit, a 5xx. Retried later."""


@dataclass
class Fetched:
    work: dict[str, Any]
    references: list[dict[str, Any]]
    cited_by: list[dict[str, Any]]
    cited_by_cut: bool = False
    via_title: bool = False


def wid_of(value: Any) -> str:
    """"https://openalex.org/W123" -> "W123"."""
    return str(value or "").rstrip("/").rsplit("/", 1)[-1]


def compact(work: dict[str, Any]) -> dict[str, Any]:
    """The few fields the missing pool and the Paper screen show of a work.
    The same as the old openalex_entry_scalars, plus abstract and journal."""
    best = work.get("best_oa_location") or {}
    oa = work.get("open_access") or {}
    source = ((work.get("primary_location") or {}).get("source") or {})
    authors, seen = [], set()
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        aid = wid_of(author.get("id"))
        if not aid or aid in seen:
            continue
        seen.add(aid)
        orcid = str(author.get("orcid") or "").rsplit("/", 1)[-1]
        authors.append([aid, author.get("display_name") or "", orcid])
    doi = normalize_doi(work.get("doi")) or ""
    return {
        "wid": wid_of(work.get("id")),
        "doi": doi,
        "title": work.get("title") or work.get("display_name") or "",
        "abstract": links.abstract_from_inverted(work.get("abstract_inverted_index")),
        "year": work.get("publication_year"),
        "pubdate": work.get("publication_date") or "",
        "journal": source.get("display_name") or "",
        "cited_by": work.get("cited_by_count") or 0,
        "oa_pdf": best.get("pdf_url") or oa.get("oa_url") or "",
        "authors": authors[:60],
        "type": work.get("type") or "",
    }


class Client:
    def __init__(self, api_key: str = "", opener: Callable[[str], tuple[int, dict[str, str], bytes]] | None = None) -> None:
        self.api_key = api_key
        # Replaced in tests: url -> (status, headers, body).
        self.opener = opener or _urlopen
        self.sleep: Callable[[float], None] = time.sleep

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(params or {})
        if self.api_key:
            merged["api_key"] = self.api_key
        if merged:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(merged)
        waited = 0.0
        last = ""
        for attempt in range(MAX_TRIES):
            try:
                status, headers, body = self.opener(url)
            except (OSError, socket.timeout) as error:
                last = f"network: {error}"
                wait = min(2**attempt, 30)
            else:
                if status == 200:
                    try:
                        return json.loads(body)
                    except ValueError:
                        raise Unavailable("OpenAlex sent something that is not JSON") from None
                if status == 404:
                    raise NotFound()
                if status == 429:
                    last = "rate limited (429)"
                    try:
                        wait = float(headers.get("retry-after") or 0) or min(5 * 2**attempt, 60)
                    except ValueError:
                        wait = min(5 * 2**attempt, 60)
                elif status >= 500:
                    last = f"OpenAlex answered {status}"
                    wait = min(2**attempt, 30)
                else:
                    raise Unavailable(f"OpenAlex answered {status}")
            if waited + wait > MAX_WAIT_SECONDS:
                break
            waited += wait
            self.sleep(wait)
        raise Unavailable(last or "OpenAlex did not answer")

    # -- one work --------------------------------------------------------------

    def by_doi(self, doi: str) -> dict[str, Any]:
        return self._get(f"{BASE}/https://doi.org/{urllib.parse.quote(doi, safe='/:;()._-')}")

    def by_title(self, title: str) -> dict[str, Any]:
        """The work whose title is this one, near enough. NotFound otherwise."""
        clean = " ".join(str(title or "").replace('"', " ").split())
        if len(clean) < 8:
            raise NotFound()
        data = self._get(BASE, {"search": f'"{clean}"', "per-page": 10, "select": "id,doi,title,display_name"})
        from rapidfuzz import fuzz

        wanted = q.fold(clean)
        for work in data.get("results") or []:
            got = q.fold(work.get("title") or work.get("display_name") or "")
            if got and fuzz.token_sort_ratio(wanted, got) >= TITLE_MATCH:
                return self._get(f"{BASE}/{wid_of(work.get('id'))}")
        raise NotFound()

    # -- its network -------------------------------------------------------------

    def works(self, wids: Iterable[str]) -> list[dict[str, Any]]:
        """Many works by id, BATCH a request, compact."""
        clean = [w for w in dict.fromkeys(wids) if w.startswith("W")]
        out = []
        for start in range(0, len(clean), BATCH):
            chunk = clean[start : start + BATCH]
            data = self._get(BASE, {"filter": "ids.openalex:" + "|".join(chunk), "per-page": BATCH, "select": COMPACT_FIELDS})
            out.extend(compact(work) for work in data.get("results") or [])
        return out

    def citing(self, wid: str) -> tuple[list[dict[str, Any]], bool]:
        """Every work citing wid, compact, most cited first. -> (works, cut)."""
        out: list[dict[str, Any]] = []
        cursor = "*"
        for _ in range(MAX_CITED_PAGES):
            data = self._get(BASE, {"filter": f"cites:{wid}", "per-page": PAGE, "cursor": cursor, "select": COMPACT_FIELDS})
            out.extend(compact(work) for work in data.get("results") or [])
            cursor = (data.get("meta") or {}).get("next_cursor") or ""
            if not cursor or not data.get("results"):
                return out, False
        return out, True

    def work_with_refs(self, wid: str) -> tuple[dict[str, Any], list[str]]:
        """One work, compact, and the ids of the works it cites (the crawl)."""
        work = self._get(f"{BASE}/{wid}", {"select": COMPACT_FIELDS + ",referenced_works"})
        return compact(work), [wid_of(w) for w in work.get("referenced_works") or []]

    def citing_top(self, wid: str, limit: int = PAGE) -> list[dict[str, Any]]:
        """The most-cited works citing wid, one page, compact (the crawl)."""
        data = self._get(BASE, {"filter": f"cites:{wid}", "per-page": min(limit, PAGE), "sort": "cited_by_count:desc", "select": COMPACT_FIELDS})
        return [compact(work) for work in data.get("results") or []]

    def fetch(self, doi: str, title: str) -> Fetched:
        """A library paper's whole OpenAlex stage. NotFound, Unavailable."""
        via_title = False
        if doi:
            work = self.by_doi(doi)
        else:
            work = self.by_title(title)
            via_title = True
        wid = wid_of(work.get("id"))
        references = self.works(wid_of(w) for w in work.get("referenced_works") or [])
        cited_by, cut = (self.citing(wid) if wid and (work.get("cited_by_count") or 0) > 0 else ([], False))
        return Fetched(work=work, references=references, cited_by=cited_by, cited_by_cut=cut, via_title=via_title)


def _urlopen(url: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, b""
