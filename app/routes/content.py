"""The routes of each paper's derived content and of the missing pool: what
is known about a paper (and asking for it sooner), the queue's state and its
failures, and the papers you do not have yet.

Everything reads app/content/ (the queue in papers/content.db, the pool in
search.db), so none of it waits on OpenAlex: a stage that is not done says
so, and the page hears when it is over /api/library/stream ("paper" events).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from msgspec import Meta
from starlette.requests import Request

from app.apidocs import QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.boards import store as boards
from app.content import store as st
from app.content.pool import POOLS, parse_sort
from app.content.service import ContentService
from app.routes.boards import actor_name
from app.routes.helpers import PAGE_LIMIT_MESSAGE, PAGE_MAX, PAGE_OFFSET_MESSAGE, Paged, Refused

TAG = "Content"
MISSING_TAG = "Missing papers"
PAGE_DEFAULT = 100
MAX_BADGE_KEYS = 5000

Limit = Annotated[int, QUERY, Meta(ge=1, le=PAGE_MAX, description="Rows to return. Default 100.", extra={"error": PAGE_LIMIT_MESSAGE})]
Offset = Annotated[int, QUERY, Meta(ge=0, description="Rows to skip: the next value of the previous page.", extra={"error": PAGE_OFFSET_MESSAGE})]
Stage = Literal["openalex", "methods", "code", "datasets", "modalities", "figures", "ocr"]
STAGE_ERROR = "stage must be one of: openalex, methods, code, datasets, modalities, figures, ocr"


def get_content(request: Request) -> ContentService:
    return request.app.state.content


def lists_holding(request: Request, key: str) -> list[dict[str, Any]]:
    """The lists a paper is on, and where: {slug, name, position}."""
    store = request.app.state.store
    out = []
    for row in boards.list_boards(store):
        record = boards.get_board(store, row["slug"])
        if record is None:
            continue
        for position, item in enumerate(record["doc"].get("items") or [], start=1):
            if item.get("key") == key:
                out.append({"slug": row["slug"], "name": row.get("name") or row["slug"], "position": position})
                break
    return out


# -- one paper ----------------------------------------------------------------


class PaperKey(RequestType):
    key: Annotated[str, QUERY, Meta(description="The paper's key, from search_library.")] = ""


class ContentReply(Reply):
    key: str
    content: Annotated[dict[str, Any], Meta(description=(
        "stages: each stage's state (pending, running, done, failed, not_found, none) with its error and summary; "
        "sections (the text split on its headings), code, data and names (links and datasets found), modalities, "
        "network (OpenAlex id, reference and citer counts, how many of each are in the library) and openalex_abstract."
    ))]
    lists: Annotated[list[dict[str, Any]], Meta(description="The lists the paper is on: slug, name, position.")]


@route(
    "GET /api/paper/content", summary="What is known about a paper",
    tag=TAG, errors=(404,),
    description=(
        "Everything derived about one paper so far: its sections (the methods split), code and dataset links, "
        "modality tags, its OpenAlex network, and the state of each stage. Asking moves its unfinished stages to the "
        "front of the queue, so what someone is looking at is done first."
    ),
    mcp="get_paper_content", read_only=True,
)
def paper_content(request: Request, body: PaperKey) -> ContentReply:
    paper = request.app.state.library.catalogue.find(body.key)
    if paper is None:
        raise Refused(404, "no such paper in the library")
    content = get_content(request)
    content.open(paper.key)
    return ContentReply(key=paper.key, content=content.paper(paper.key), lists=lists_holding(request, paper.key))


class RetryBody(RequestType):
    key: Annotated[str, Meta(description="A paper's key. Empty: every paper.")] = ""
    stage: Annotated[str, Meta(description="One stage. Empty: every stage.", extra={"error": STAGE_ERROR})] = ""


class RetryReply(Reply):
    queued: Annotated[int, Meta(description="How many stages were put back in the queue.")]


@route(
    "POST /api/papers/retry", summary="Try a failed stage again",
    tag=TAG, errors=(404,),
    description=(
        "Put failed (and not-found) stages back in the queue at once: one paper's, one stage's across the library, "
        "or one paper's one stage. A not-found OpenAlex lookup is only ever asked again this way."
    ),
    mcp="retry_content",
)
def retry(request: Request, body: RetryBody) -> RetryReply:
    if body.stage and body.stage not in st.STAGES:
        raise Refused(400, STAGE_ERROR)
    key = ""
    if body.key:
        paper = request.app.state.library.catalogue.find(body.key)
        if paper is None:
            raise Refused(404, "no such paper in the library")
        key = paper.key
    content = get_content(request)
    queued = content.files.retry(key, body.stage)
    content._queue_event(force=True)
    return RetryReply(queued=queued)


class BadgesBody(RequestType):
    keys: Annotated[list[str], Meta(description="Paper keys. At most 5000.", extra={"error": 'send {"keys": [...]}'})]


class BadgesReply(Reply):
    badges: Annotated[dict[str, dict[str, Any]], Meta(description=(
        "Per key: states (each stage's state), code and data (how many links), methods (a methods section was "
        "found), mods, refs and citers, errors."
    ))]


@route(
    "POST /api/papers/badges", summary="What is ready, for many papers",
    tag=TAG,
    description="A short summary of each paper's content, for the badges on every row that shows a paper.",
    mcp="content_badges", read_only=True,
)
def badges(request: Request, body: BadgesBody) -> BadgesReply:
    if len(body.keys) > MAX_BADGE_KEYS:
        raise Refused(400, f"at most {MAX_BADGE_KEYS} keys at once")
    return BadgesReply(badges=get_content(request).badges([str(k) for k in body.keys]))


# -- the queue ------------------------------------------------------------------


class StatusReply(Reply):
    stages: Annotated[dict[str, dict[str, int]], Meta(description="Per stage, how many papers are in each state.")]
    pool: Annotated[dict[str, int], Meta(description="The missing pool: all, refs, citing, and papers (library papers whose network is in).")]
    running: Annotated[dict[str, str], Meta(description="The paper each lane (net, local) is working on now.")]
    workers: Annotated[list[dict[str, Any]], Meta(description=(
        "The heavy-stage workers (`python -m app worker`) that checked in lately: id, host, pid, started, beat, "
        "doing (the task in hand), stages, alive (checked in within 90 s)."
    ))]
    openalex_enabled: bool
    openalex_key: Annotated[bool, Meta(description="Whether library.openalex_api_key is set.")]
    library: Annotated[dict[str, Any], Meta(description="papers, with_text, no_pdf, text_pending.")]


@route(
    "GET /api/content/status", summary="How far the content queue has got",
    tag=TAG,
    description="Per stage, how many papers are done, pending, running, failed or not found; the missing pool's size; what is running.",
    mcp="content_status", read_only=True,
)
def content_status(request: Request) -> StatusReply:
    catalogue = request.app.state.library.catalogue
    papers = catalogue.all()
    status = get_content(request).status()
    library = {
        "papers": len(papers),
        "with_text": sum(1 for p in papers if p.has_text),
        "no_pdf": sum(1 for p in papers if not p.record.get("pdfs")),
        "text_pending": catalogue.status.text_pending,
    }
    return StatusReply(library=library, **status)


class StageListing(RequestType):
    stage: Annotated[Stage, QUERY, Meta(description="The stage.", extra={"error": STAGE_ERROR})] = "openalex"
    state: Annotated[Literal["unfinished", "failed", "not_found", "errors", "pending", "done"], QUERY, Meta(
        description='"unfinished" (default): pending, running and failed. "errors": failed and not found.',
        extra={"error": "state must be one of: unfinished, failed, not_found, errors, pending, done"},
    )] = "unfinished"
    q: Annotated[str, QUERY, Meta(description="Only papers whose title, DOI or error contains this.")] = ""
    sort: Annotated[Literal["added", "title", "year", "journal", "state", "error", "attempts", "first_failed", "last_failed"], QUERY, Meta(
        description="Default added (newest first).",
        extra={"error": "sort must be one of: added, title, year, journal, state, error, attempts, first_failed, last_failed"},
    )] = "added"
    dir: Annotated[Literal["asc", "desc"], QUERY, Meta(description="Default desc.", extra={"error": "dir must be asc or desc"})] = "desc"
    limit: Limit = PAGE_DEFAULT
    offset: Offset = 0


class StageReply(Paged):
    papers: Annotated[list[dict[str, Any]], Meta(description="key, title, doi, year, state, attempts, error, first_failed, last_failed, next_at.")]


STATE_SETS = {
    "unfinished": (st.PENDING, st.RUNNING, st.FAILED),
    "failed": (st.FAILED,),
    "not_found": (st.NOT_FOUND,),
    "errors": (st.FAILED, st.NOT_FOUND),
    "pending": (st.PENDING, st.RUNNING),
    "done": (st.DONE,),
}


@route(
    "GET /api/content/papers", summary="The papers a stage has not finished",
    tag=TAG,
    description=(
        "A stage's papers in some states, a page at a time: the ones still to do, or the failures with why, when "
        "they first and last failed, and how many tries -- the Status and Errors screens."
    ),
    mcp="content_papers", read_only=True,
)
def stage_papers(request: Request, body: StageListing) -> StageReply:
    catalogue = request.app.state.library.catalogue
    rows = []
    needle = body.q.strip().lower()
    for task in get_content(request).files.listing(body.stage, STATE_SETS[body.state]):
        paper = catalogue.get(task["key"])
        if paper is None:
            continue
        record = paper.record
        row = {
            "key": task["key"], "title": record.get("title", ""), "doi": record.get("doi", ""), "year": record.get("year"),
            "journal": record.get("journal", ""), "added": record.get("date_added", ""), "state": task["state"],
            "attempts": task["attempts"], "error": task.get("error", ""), "first_failed": task.get("first_failed"),
            "last_failed": task.get("last_failed"), "next_at": task.get("next_at"),
        }
        if needle and needle not in f"{row['title']} {row['doi']} {row['error']}".lower():
            continue
        rows.append(row)
    descending = body.dir == "desc"
    keys = {
        "title": lambda r: (r["title"] or "").lower(),
        "year": lambda r: r["year"] or 0,
        "journal": lambda r: (r["journal"] or "").lower(),
        "state": lambda r: r["state"] or "",
        "error": lambda r: (r["error"] or "").lower(),
        "attempts": lambda r: r["attempts"],
        "first_failed": lambda r: r["first_failed"] or 0,
        "last_failed": lambda r: r["last_failed"] or 0,
    }
    rows.sort(key=keys.get(body.sort, lambda r: r["added"] or ""), reverse=descending)
    page = rows[body.offset : body.offset + body.limit]
    end = body.offset + len(page)
    return StageReply(papers=page, next=end if end < len(rows) else None, total=len(rows))


# -- the missing pool -------------------------------------------------------------


class MissingSearch(RequestType):
    q: Annotated[str, QUERY, Meta(description="The search, the library's boolean grammar. Read up to 500 characters.")] = ""
    pool: Annotated[Literal["all", "refs", "citing"], QUERY, Meta(
        description='"all" (default), "refs" (works your library cites), "citing" (works citing your library).',
        extra={"error": "pool must be all, refs or citing"},
    )] = "all"
    sort: Annotated[str, QUERY, Meta(description=(
        'Columns, most important first: "conn:desc,year:desc". Columns: relevance (only while searching), conn, '
        "cited_by, title, year. Default conn:desc."
    ))] = ""
    skipped: Annotated[Literal["hide", "show"], QUERY, Meta(description="Default hide.", extra={"error": "skipped must be hide or show"})] = "hide"
    paper: Annotated[str, QUERY, Meta(description="Only this library paper's network: its references and citers that you lack.")] = ""
    limit: Limit = PAGE_DEFAULT
    offset: Offset = 0


class MissingReply(Paged):
    works: Annotated[list[dict[str, Any]], Meta(description=(
        "wid, doi, title, journal, year, cited_by (OpenAlex), oa_pdf, authors, lib_cites (library papers citing it), "
        "cites_lib (library papers it cites), conn (their sum), score, skipped."
    ))]
    counts: Annotated[dict[str, int], Meta(description="all, refs, citing: the same search on each tab.")]
    skipped: Annotated[int, Meta(description="How many matching works are skipped.")]
    paper: Annotated[dict[str, Any] | None, Meta(description="The library paper a network filter names.")] = None


@route(
    "GET /api/missing", summary="Search the papers you do not have",
    tag=MISSING_TAG, errors=(404,),
    description=(
        "The missing pool: works your library cites, and works citing it, that are not in the library, with "
        "how many of your papers connect to each. Searched with the library's grammar, sorted on several columns, a "
        "page at a time. It fills in as each paper's OpenAlex stage lands."
    ),
    mcp="search_missing", read_only=True,
)
def search_missing(request: Request, body: MissingSearch) -> MissingReply:
    content = get_content(request)
    paper_info = None
    paper_key = ""
    if body.paper:
        paper = request.app.state.library.catalogue.find(body.paper)
        if paper is None:
            raise Refused(404, "no such paper in the library")
        paper_key = paper.key
        paper_info = {"key": paper.key, "title": paper.record.get("title", "")}
    found = content.pool.search(
        body.q[:500], body.pool, parse_sort(body.sort), content.skipped(), body.skipped == "show", paper_key, body.limit, body.offset,
    )
    end = body.offset + len(found["rows"])
    return MissingReply(
        works=found["rows"], counts=found["counts"], skipped=found["skipped"], paper=paper_info,
        next=end if end < found["total"] else None, total=found["total"],
    )


class AuthorsReply(Reply):
    authors: Annotated[list[dict[str, Any]], Meta(description="openalex, name, orcid, papers (in the pool), lib_cites (summed connections).")]


@route(
    "GET /api/missing/authors", summary="Who you cite most and lack",
    tag=MISSING_TAG,
    description="The top 100 authors of the works your library cites and does not have, by summed connections then paper count.",
    mcp="missing_authors", read_only=True,
)
def missing_authors(request: Request) -> AuthorsReply:
    content = get_content(request)
    return AuthorsReply(authors=content.pool.authors(content.skipped()))


class SkipBody(RequestType):
    wids: Annotated[list[str], Meta(description='OpenAlex ids ("W123"). At most 1000.', extra={"error": 'send {"wids": [...]}'})]
    skip: Annotated[bool, Meta(description="true hides them (default); false shows them again.")] = True


class SkipReply(Reply):
    changed: int


@route(
    "POST /api/missing/skip", summary="Skip or unskip missing papers",
    tag=MISSING_TAG,
    description="Hide works from the Missing screen (a soft hide, undone by skip false), or bring them back.",
    mcp="skip_missing",
)
def skip_missing(request: Request, body: SkipBody) -> SkipReply:
    wids = [str(w).strip() for w in body.wids if str(w).strip().startswith("W")][:1000]
    if not wids:
        raise Refused(400, 'send {"wids": ["W..."]}')
    return SkipReply(changed=get_content(request).skip(wids, body.skip, actor_name(request)))


__all__ = ["POOLS"]
