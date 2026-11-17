"""The library's routes: the papers in Zotero, searched and paged; one paper;
its PDF; the userscripts' "do I have this" check; and the live stream that
says when the library moved.

Everything reads the in-memory catalogue (app/library/catalogue.py), so none
of it waits on Zotero. The handlers are plain functions, so they run in a
worker thread: a full-text query reads the index file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from app.apidocs import QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.core import sse
from app.library.catalogue import Catalogue, public, sort_papers
from app.routes.helpers import PAGE_LIMIT_MESSAGE, PAGE_MAX, PAGE_OFFSET_MESSAGE, Paged, Refused, error, get_config

MAX_EXISTS_QUERIES = 5000
PAGE_DEFAULT = 50
TAG = "Library"


def get_catalogue(request: Request) -> Catalogue:
    return request.app.state.library.catalogue


Limit = Annotated[int, QUERY, Meta(ge=1, le=PAGE_MAX, description="Papers to return. Default 50.", extra={"error": PAGE_LIMIT_MESSAGE})]
Offset = Annotated[int, QUERY, Meta(ge=0, description="Papers to skip: the next value of the previous page.", extra={"error": PAGE_OFFSET_MESSAGE})]


class LibraryStatus(Reply):
    """How far the catalogue has got reading Zotero."""

    ready: bool
    papers: int
    with_text: int
    text_pending: int
    error: str
    rev: int


def status_body(catalogue: Catalogue) -> LibraryStatus:
    status = catalogue.status
    return LibraryStatus(
        ready=status.ready,
        papers=status.papers,
        with_text=status.with_text,
        text_pending=status.text_pending,
        error=status.error,
        rev=catalogue.rev,
    )


class SearchPapers(RequestType):
    q: Annotated[str, QUERY, Meta(description="The search. Empty lists every paper. Read up to 500 characters.")] = ""
    mode: Annotated[Literal["text", "title"], QUERY, Meta(
        description='"text" (default): boolean full-text search. "title": a half-remembered title, typos and all, or a DOI.',
        extra={"error": "mode must be text or title"},
    )] = "text"
    sort: Annotated[Literal["relevance", "added", "year", "title", "journal", "authors"], QUERY, Meta(
        description="Default relevance. authors orders by the first author.",
        extra={"error": "sort must be one of: relevance, added, year, title, journal, authors"},
    )] = "relevance"
    dir: Annotated[Literal["asc", "desc"], QUERY, Meta(description="Default desc.", extra={"error": "dir must be asc or desc"})] = "desc"
    has: Annotated[str, QUERY, Meta(description=(
        'Only papers with: "code" (code links found), "data" (dataset links or names), "no_text" (no PDF text), '
        '"no_openalex" (OpenAlex has no record, or the lookup failed). Several, comma-separated, must all hold.'
    ))] = ""
    limit: Limit = PAGE_DEFAULT
    offset: Offset = 0


HAS = ("code", "data", "no_text", "no_openalex")


class SearchReply(Paged):
    papers: Annotated[list[dict[str, Any]], Meta(description=(
        "Each paper as the library has it, with score (its relevance, or null) and content (what is ready of it, as "
        "content_badges gives it; null before its first stage is queued)."
    ))]
    fuzzy: Annotated[bool, Meta(description="Whether the matches are near ones, not exact.")]
    status: LibraryStatus


@route(
    "GET /api/papers", summary="Search the library",
    tag=TAG,
    description=(
        "Search the papers in the Zotero library, a page at a time. mode \"text\" (default) is boolean full-text "
        "search over title, authors, abstract and the PDF's text: words are ANDed, OR between alternatives, -word or "
        "NOT word excludes, \"a phrase\" is literal. mode \"title\" finds a half-remembered title, typos and all, or a "
        "pasted DOI."
    ),
    mcp_note="Each paper's key is what list_ops' add takes.",
    mcp="search_library", read_only=True,
)
def list_papers(request: Request, body: SearchPapers) -> SearchReply:
    catalogue = get_catalogue(request)
    result = catalogue.search(body.q[:500], mode=body.mode)
    rows = result.rows
    content = request.app.state.content
    for want in [w.strip() for w in body.has.split(",") if w.strip()]:
        if want not in HAS:
            raise Refused(400, "has must name: " + ", ".join(HAS))
        if want == "no_text":
            rows = [p for p in rows if not p.has_text]
        else:
            keys = content.keys_with(want)
            rows = [p for p in rows if p.key in keys]
    rows = sort_papers(rows, body.sort, body.dir == "desc", result.scores)
    total = len(rows)
    page = rows[body.offset : body.offset + body.limit]
    end = body.offset + len(page)
    found = content.badges([paper.key for paper in page])
    return SearchReply(
        papers=[{**public(paper), "score": result.scores.get(paper.key), "content": found.get(paper.key)} for paper in page],
        next=end if end < total else None,
        total=total,
        fuzzy=result.fuzzy,
        status=status_body(catalogue),
    )


class RecentPapers(RequestType):
    days: Annotated[int, QUERY, Meta(ge=1, le=3650, description="How far back. Default 7.", extra={"error": "days must be 1-3650"})] = 7
    not_on: Annotated[str, QUERY, Meta(description="A list's slug: leave out the papers already on it.")] = ""
    limit: Limit = PAGE_DEFAULT
    offset: Offset = 0


class PapersReply(Paged):
    papers: list[dict[str, Any]]


@route(
    "GET /api/papers/recent", summary="Papers added lately",
    tag=TAG, errors=(404,),
    description=(
        "Papers added in Zotero in the last days, newest first, leaving out those already on the list not_on names: "
        "\"what did I save this week that isn't on this list yet?\". Read from the live catalogue, so a paper saved "
        "seconds ago is there."
    ),
    mcp="recent_papers", read_only=True,
)
def recent_papers(request: Request, body: RecentPapers) -> PapersReply:
    from app.boards import store as boards

    have: set[str] = set()
    if body.not_on:
        record = boards.get_board(request.app.state.store, body.not_on)
        if record is None:
            raise Refused(404, "no such list")
        have = {row["key"] for row in (record["doc"].get("items") or [])}
    since = (datetime.now(timezone.utc) - timedelta(days=body.days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [p for p in get_catalogue(request).all() if (p.record.get("date_added") or "") >= since and p.key not in have]
    rows.sort(key=lambda p: p.record.get("date_added") or "", reverse=True)
    page = rows[body.offset : body.offset + body.limit]
    end = body.offset + len(page)
    return PapersReply(papers=[public(p) for p in page], next=end if end < len(rows) else None, total=len(rows))


@route(
    "GET /api/library/status", summary="How the library is doing",
    tag=TAG,
    description="Whether the catalogue has read Zotero yet, how many papers it holds, how many have their text indexed, and any error.",
    mcp="library_status", read_only=True,
)
def library_status(request: Request) -> LibraryStatus:
    return status_body(get_catalogue(request))


class PaperKey(RequestType):
    key: Annotated[str, QUERY, Meta(description="The paper's Zotero key, from search_library.")] = ""


class PaperReply(Reply):
    paper: dict[str, Any]


@route(
    "GET /api/paper", summary="One paper",
    tag=TAG, errors=(404,),
    description="One paper in full: everything the library knows of it.",
    mcp="get_paper", read_only=True,
)
def get_paper(request: Request, body: PaperKey) -> PaperReply:
    paper = get_catalogue(request).find(body.key)
    if paper is None:
        raise Refused(404, "no such paper in the library")
    return PaperReply(paper=public(paper, full=True))


@route(
    "GET /api/paper/pdf", summary="A paper's PDF",
    tag=TAG, errors=(404,), reply_type="application/pdf",
    description="The paper's first PDF that is on disk, to open in the browser.",
    mcp_http="The file itself, for a browser to show.",
)
def get_pdf(request: Request, body: PaperKey) -> Response:
    """Only a path Zotero recorded for that paper is ever served, never one
    the request names."""
    paper = get_catalogue(request).find(body.key)
    if paper is None:
        raise Refused(404, "no such paper in the library")
    for name in paper.record.get("pdfs") or []:
        path = Path(name)
        if path.is_file():
            # inline, so the browser's own viewer opens it.
            return FileResponse(path, media_type="application/pdf", content_disposition_type="inline", filename=path.name)
    raise Refused(404, "this paper has no PDF on disk")


class ExistsRequest(RequestType):
    queries: Annotated[list[dict[str, Any]], Meta(
        description='The papers to look for: {"id", "title", "doi"} each. At most 5000.',
        extra={"error": 'send {"queries": [{"id": ..., "title": ..., "doi": ...}]}'},
    )]


class ExistsReply(Reply):
    results: Annotated[list[dict[str, Any]], Meta(description='{"id", "exists", "title", "doi"} for each query, in order.')]


@route(
    "POST /api/exists", summary="Which of these papers are in the library",
    tag=TAG,
    description=(
        "The userscripts' question: which of these papers is in the library. A DOI settles it; a title is matched "
        "only without one. Called with an API key (Authorization: Bearer), so it needs no csrf_token; a browser "
        "session sends one like any other POST."
    ),
    mcp="papers_exist", read_only=True,
)
def post_exists(request: Request, body: ExistsRequest) -> ExistsReply:
    if len(body.queries) > MAX_EXISTS_QUERIES:
        raise Refused(400, f"at most {MAX_EXISTS_QUERIES} queries at once")
    catalogue = get_catalogue(request)
    rows = []
    for query in body.queries:
        doi = str(query.get("doi") or "")[:400]
        title = str(query.get("title") or "")[:1000]
        rows.append({"id": query.get("id"), "exists": catalogue.exists(doi, title), "title": query.get("title"), "doi": query.get("doi")})
    return ExistsReply(results=rows)


class VersionReply(Reply):
    version: Annotated[str, Meta(description="Changes whenever the library does.")]
    papers: int


@route(
    "GET /api/version", summary="The library's version token",
    tag=TAG,
    description="A token that changes whenever the library does, so a userscript can poll cheaply and re-ask only then.",
    mcp="library_version", read_only=True,
)
def get_version(request: Request) -> VersionReply:
    catalogue = get_catalogue(request)
    return VersionReply(version=catalogue.version(), papers=catalogue.status.papers)


class LinksReply(Reply):
    proxy_url: Annotated[str, Meta(description="library.proxy_url: the prefix a paper's publisher link goes through. Empty for none.")]


@route(
    "GET /api/library/links", summary="What a paper's links need",
    tag=TAG,
    description="What the page needs to build a paper's links.",
    mcp_http="Settings for drawing the page's links, not something an agent acts on.",
)
def get_config_links(request: Request) -> LinksReply:
    return LinksReply(proxy_url=get_config(request).library.proxy_url)


@route(
    "GET /api/library/stream", summary="When the library moves",
    tag=TAG, reply_type="text/event-stream",
    description=(
        "Server-sent events: \"changed\" when papers were added, changed or removed, \"progress\" while full text "
        "is being indexed. The page fetches what it shows again."
    ),
    mcp_http="A live event stream for the page; library_version is the polling equivalent.",
)
async def stream_library(request: Request) -> Response:
    if request.method == "HEAD":
        return Response(headers=sse.HEADERS)
    from app.routes.streams import still_signed_in

    hub: sse.Hub = request.app.state.library.hub
    client = hub.join()
    if client is None:
        return error(503, "too many live streams")
    allowed = still_signed_in(request)
    return sse.EventStream(hub, client, allowed, opening=(sse.retry(sse.RETRY_MS),))
