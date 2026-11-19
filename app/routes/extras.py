"""Phase 7's extras: saved searches, the missing.xlsx workbook, the
research-log check and the citation-graph crawl. See app/extras/.
"""
from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from app.apidocs import PATH, QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.extras import crawl as cr
from app.extras import logcheck, xlsx
from app.extras.searches import SavedSearches, SearchError
from app.library.catalogue import public
from app.routes.boards import actor_name
from app.routes.helpers import Refused
from app.routes.content import missing_scope
from app.routes.library import get_catalogue

SEARCH_TAG = "Saved searches"
MISSING_TAG = "Missing pool"
LOG_TAG = "Research log"
CRAWL_TAG = "Crawl"
XLSX = xlsx.XLSX
ROW_LIMIT = 2000


def get_searches(request: Request) -> SavedSearches:
    return request.app.state.searches


def proxy_url(request: Request) -> str:
    return request.app.state.settings.get().library.proxy_url


def attachment(data: bytes, name: str) -> Response:
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{xlsx.filename(name)}.xlsx"'})


def refused(error: SearchError) -> Refused:
    return Refused(400, "invalid_search", problems=error.problems)


SearchId = Annotated[str, PATH, Meta(min_length=1, max_length=120, description="The search's id, or its name.", extra={"error": "no such search"})]
Groups = Annotated[list[dict[str, Any]], Meta(description=(
    "Named groups of terms: {name (letters, digits, _), mode: any | all | none | at_least, terms: [phrases] (any / all / none), "
    "n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of "
    "the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text."
))]


class Empty(RequestType):
    pass


class SearchPath(RequestType):
    search: SearchId


class SearchBody(RequestType):
    name: Annotated[str, Meta(min_length=1, max_length=120, description="Its name, unique.", extra={"error": "give the search a name"})]
    query: Annotated[str, Meta(max_length=2000, description='A boolean query in the search box\'s grammar (AND, OR, NOT, -term, "phrase"). May be empty.')] = ""
    groups: Groups = []
    description: Annotated[str, Meta(max_length=2000)] = ""


class SearchUpdate(SearchBody, kw_only=True):
    search: SearchId


class SearchesReply(Reply):
    api_name: ClassVar[str] = "SavedSearches"
    searches: Annotated[list[dict[str, Any]], Meta(description="Each search: id, name, description, query, groups, created / updated at and by.")]


@route(
    "GET /api/searches", summary="The saved searches",
    tag=SEARCH_TAG,
    description="Every saved search: a name, a boolean query and named groups of terms. The crawl and missing.xlsx use them.",
    mcp="list_saved_searches", read_only=True,
)
def list_searches(request: Request, body: Empty) -> SearchesReply:
    return SearchesReply(searches=get_searches(request).all())


class SearchReply(Reply):
    api_name: ClassVar[str] = "SavedSearch"
    search: dict[str, Any]


@route(
    "POST /api/searches", summary="Save a search",
    tag=SEARCH_TAG, status=201, errors=(400,),
    description="A new saved search. A search that does not hold together is a 400 listing each problem with where it is.",
    mcp="create_saved_search",
)
def create_search(request: Request, body: SearchBody) -> SearchReply:
    data = {"name": body.name, "query": body.query, "groups": body.groups, "description": body.description}
    try:
        return SearchReply(search=get_searches(request).save(data, actor_name(request)))
    except SearchError as error:
        raise refused(error) from None


def found(request: Request, spec: str) -> dict[str, Any]:
    search = get_searches(request).find(spec)
    if search is None:
        raise Refused(404, "no such search")
    return search


@route(
    "POST /api/searches/{search}", summary="Change a saved search",
    tag=SEARCH_TAG, errors=(400, 404),
    description="Replace a saved search's name, query, groups and description.",
    mcp="update_saved_search",
)
def update_search(request: Request, body: SearchUpdate) -> SearchReply:
    old = found(request, body.search)
    data = {"name": body.name, "query": body.query, "groups": body.groups, "description": body.description}
    try:
        return SearchReply(search=get_searches(request).save(data, actor_name(request), old["id"]))
    except SearchError as error:
        raise refused(error) from None


@route(
    "POST /api/searches/{search}/delete", summary="Delete a saved search",
    tag=SEARCH_TAG, errors=(404,),
    description="Delete a saved search. The answer is the search as it was, which POST /api/searches/restore puts back.",
    mcp="delete_saved_search", destructive=True,
)
def delete_search(request: Request, body: SearchPath) -> SearchReply:
    old = found(request, body.search)
    get_searches(request).delete(old["id"])
    return SearchReply(search=old)


class RestoreBody(RequestType):
    search: Annotated[dict[str, Any], Meta(description="The search as delete_saved_search answered it.")]


@route(
    "POST /api/searches/restore", summary="Put a deleted search back",
    tag=SEARCH_TAG, errors=(400,),
    description="Undo a delete: the search as it was, with its id.",
    mcp_http="The page's undo; an agent makes the search again with create_saved_search.",
)
def restore_search(request: Request, body: RestoreBody) -> SearchReply:
    record = body.search
    if not isinstance(record.get("id"), str) or not record["id"]:
        raise Refused(400, "send the search delete answered")
    try:
        from app.extras.searches import clean

        tidy = clean(record)
    except SearchError as error:
        raise refused(error) from None
    saved = {**record, **tidy}
    get_searches(request).restore(saved)
    return SearchReply(search=saved)


class RunQuery(RequestType):
    search: SearchId
    pool: Annotated[Literal["library", "missing", "both"], QUERY, Meta(
        description='"both" (default), "library" or "missing".', extra={"error": "pool must be library, missing or both"},
    )] = "both"
    limit: Annotated[int, QUERY, Meta(ge=1, le=ROW_LIMIT, description=f"Rows of each pool to return. Default 500, at most {ROW_LIMIT}.")] = 500


class RunReply(Reply):
    api_name: ClassVar[str] = "SavedSearchRun"
    search: dict[str, Any]
    library: Annotated[list[dict[str, Any]], Meta(description="Library papers matched, newest first: key, title, doi, year, journal, authors, added, tags.")]
    library_total: int
    library_groups: Annotated[dict[str, int], Meta(description="How many library papers each group matches on its own.")]
    missing: Annotated[list[dict[str, Any]], Meta(description="Missing works matched, by connections: wid, doi, title, journal, year, cited_by, oa_pdf, authors, conn.")]
    missing_total: int
    missing_groups: dict[str, int]


def run_search(request: Request, search: dict[str, Any], pool: str, limit: int) -> RunReply:
    saved = get_searches(request)
    catalogue = get_catalogue(request)
    lib: list[dict[str, Any]] = []
    lib_total = 0
    lib_groups: dict[str, int] = {}
    if pool in ("library", "both"):
        keys, lib_groups = saved.run_library(search, catalogue)
        lib_total = len(keys)
        lib = [public(catalogue.get(k)) for k in keys[:limit] if catalogue.get(k) is not None]
    miss: list[dict[str, Any]] = []
    miss_total = 0
    miss_groups: dict[str, int] = {}
    if pool in ("missing", "both"):
        miss, miss_total, miss_groups = saved.run_missing(search, limit, scope=missing_scope(request))
    return RunReply(search=search, library=lib, library_total=lib_total, library_groups=lib_groups, missing=miss,
                    missing_total=miss_total, missing_groups=miss_groups)


@route(
    "GET /api/searches/{search}/run", summary="Run a saved search",
    tag=SEARCH_TAG, errors=(404,),
    description="The library papers and missing works a saved search matches, and how many each of its groups matches alone.",
    mcp="run_saved_search", read_only=True,
)
def run(request: Request, body: RunQuery) -> RunReply:
    return run_search(request, found(request, body.search), body.pool, body.limit)


class TryBody(SearchBody):
    pool: Annotated[Literal["library", "missing", "both"], Meta(description='"both" (default), "library" or "missing".')] = "both"
    limit: Annotated[int, Meta(ge=1, le=ROW_LIMIT)] = 200
    name: Annotated[str, Meta(max_length=120)] = "Unsaved"


@route(
    "POST /api/searches/try", summary="Try a search before saving it",
    tag=SEARCH_TAG, errors=(400,),
    description="Run a search as sent, without saving it: what the editor shows as you type.",
    mcp="try_saved_search", read_only=True,
)
def try_search(request: Request, body: TryBody) -> RunReply:
    from app.extras.searches import clean

    try:
        search = clean({"name": body.name or "Unsaved", "query": body.query, "groups": body.groups, "description": body.description})
    except SearchError as error:
        raise refused(error) from None
    return run_search(request, {**search, "id": ""}, body.pool, body.limit)


class ExportQuery(RequestType):
    search: SearchId
    format: Annotated[Literal["xlsx", "md"], QUERY, Meta(description='"xlsx" (default) or "md".', extra={"error": "format must be xlsx or md"})] = "xlsx"


@route(
    "GET /api/searches/{search}/export", summary="A saved search's matches as a file",
    tag=SEARCH_TAG, errors=(404,), reply_type=XLSX,
    description="Every match, library and missing, as an .xlsx (a sheet each) or a Markdown list.",
    mcp_http="A file to download.",
)
def export_search(request: Request, body: ExportQuery) -> Response:
    search = found(request, body.search)
    result = run_search(request, search, "both", 100_000)
    proxy = proxy_url(request)
    if body.format == "md":
        lines = [f"# {search['name']}", ""]
        if search.get("query"):
            lines += [f"Query: `{search['query']}`", ""]
        lines += [f"## In the library ({result.library_total})", ""]
        for paper in result.library:
            doi = f" [{paper['doi']}](https://doi.org/{paper['doi']})" if paper.get("doi") else ""
            lines.append(f"- {paper['title']} ({paper.get('year') or 'n.d.'}){doi}")
        lines += ["", f"## Missing ({result.missing_total})", ""]
        for work in result.missing:
            doi = f" [{work['doi']}](https://doi.org/{work['doi']})" if work.get("doi") else ""
            lines.append(f"- {work['title']} ({work.get('year') or 'n.d.'}), {work['conn']} connections{doi}")
        name = xlsx.filename(search["name"], "search")
        return Response("\n".join(lines) + "\n", media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    library_rows = [[p["title"], p.get("year"), p.get("journal") or "", xlsx.Link("https://doi.org/" + p["doi"], p["doi"]) if p.get("doi") else "",
                     "; ".join(p.get("authors") or []), p.get("added") or ""] for p in result.library]
    sheets = [
        ("Library", ["Title", "Year", "Journal", "DOI", "Authors", "Added"], library_rows),
        ("Missing", xlsx.WORK_HEADER, [xlsx.work_row(w, proxy) for w in result.missing]),
    ]
    return attachment(xlsx.workbook(sheets), search["name"])


# -- missing.xlsx --------------------------------------------------------------------------

class MissingExportQuery(RequestType):
    top: Annotated[int, QUERY, Meta(ge=10, le=5000, description="Rows per sheet. Default 1000.")] = 1000
    searches: Annotated[bool, QUERY, Meta(description="Also a sheet per saved search (default true).")] = True


@route(
    "GET /api/missing/export.xlsx", summary="The missing pool as a workbook",
    tag=MISSING_TAG, reply_type=XLSX,
    description=(
        "The old missing.xlsx, from the live pool: the top works by connections, the newest, the most cited, the top authors, "
        "and one sheet per saved search. Each row has its DOI, proxy and open-access links, year, journal and connections. "
        "Skipped works are left out."
    ),
    mcp_http="A file to download.",
)
def missing_export(request: Request, body: MissingExportQuery) -> Response:
    content = request.app.state.content
    data = xlsx.missing_workbook(content.pool, get_searches(request) if body.searches else None, content.skipped(), proxy_url(request), body.top,
                                 scope=missing_scope(request))
    return attachment(data, "missing")


# -- the research-log check ------------------------------------------------------------------

class LogBody(RequestType):
    text: Annotated[str, Meta(max_length=logcheck.MAX_LOG_BYTES, description="The log's Markdown.", extra={"error": "send the log's text"})]
    name: Annotated[str, Meta(max_length=200, description="The file's name, for the report.")] = "research log"
    list_only: Annotated[bool, Meta(description="Only what the parser extracted, unchecked: for a log whose layout drifted.")] = False


class LogReply(Reply):
    api_name: ClassVar[str] = "ResearchLogCheck"
    source: str
    lines: int
    extracted: Annotated[int, Meta(description="Paper blocks found.")]
    unique: Annotated[int, Meta(description="After merging repeats by title.")]
    papers: Annotated[list[dict[str, Any]], Meta(description=(
        "Each paper: title, line, date (the heading above it), url, doi, occurrences (lines), mentions, and when checked: found "
        '("doi", "title" or "" for missing), recovered (its DOI is not in the library but its title is), key.'
    ))]
    missing: int = 0
    recovered: int = 0
    report: Annotated[str, Meta(description="The Markdown report, as the old command wrote it.")] = ""


@route(
    "POST /api/research-log/check", summary="Which papers in a research log you lack",
    tag=LOG_TAG, errors=(400,),
    description=(
        "Reads a Markdown research log (# 03SEP2026 date headings, &nbsp;-separated blocks of a title line and its links), "
        "lifts each paper's DOI out of its links, and checks each the way /api/exists does: a DOI settles it, else the title. "
        "A DOI miss is retried by title and marked recovered."
    ),
    mcp="check_research_log", read_only=True,
)
def check_log(request: Request, body: LogBody) -> LogReply:
    if not body.text.strip():
        raise Refused(400, "send the log's text")
    catalogue = get_catalogue(request)
    result = logcheck.run(body.text, body.name, None if body.list_only else catalogue.match)
    return LogReply(**result)


# -- the crawl -----------------------------------------------------------------------------

class CrawlStatusReply(Reply):
    api_name: ClassVar[str] = "CrawlStatus"
    status: Annotated[dict[str, Any], Meta(description="running, search_id, search, visited, novel, api_used, max_visits, started_at / finished_at, error.")]
    runs: Annotated[list[dict[str, Any]], Meta(description="Each saved search's last crawl: settings, terms, seeds, visited, novel, api_used, errors, when.")]
    defaults: Annotated[dict[str, Any], Meta(description="The crawl's default settings.")]


@route(
    "GET /api/crawl", summary="The crawl's progress and past runs",
    tag=CRAWL_TAG,
    description="Whether a crawl is running and how far it has got, and the last crawl of each saved search.",
    mcp="crawl_status", read_only=True,
)
def crawl_status(request: Request, body: Empty) -> CrawlStatusReply:
    return status_reply(request)


def status_reply(request: Request) -> CrawlStatusReply:
    from dataclasses import asdict

    crawler = request.app.state.crawler
    return CrawlStatusReply(status=crawler.status(), runs=crawler.runs(), defaults=asdict(cr.Settings()))


class CrawlBody(RequestType):
    search: Annotated[str, Meta(min_length=1, description="The saved search whose terms score the works (id or name).", extra={"error": "name a saved search"})]
    max_visits: Annotated[int, Meta(ge=1, le=5000)] = 500
    max_depth: Annotated[int, Meta(ge=0, le=4)] = 2
    min_seed_hits: Annotated[int, Meta(ge=0, le=50, description="Terms a library paper needs to be a seed.")] = 1
    min_novel_hits: Annotated[int, Meta(ge=0, le=50, description="Terms a work needs to be reported.")] = 2
    api_budget: Annotated[int, Meta(ge=0, le=20000, description="OpenAlex requests at most; 0 uses only what is cached.")] = 1000
    keyword_weight: Annotated[float, Meta(ge=0, le=10)] = 1.0
    cite_weight: Annotated[float, Meta(ge=0, le=10)] = 0.4
    link_weight: Annotated[float, Meta(ge=0, le=10)] = 0.5
    cited_by: Annotated[bool, Meta(description="Also walk forward, to the works citing each one.")] = True


@route(
    "POST /api/crawl", summary="Start a crawl",
    tag=CRAWL_TAG, status=202, errors=(400, 404, 409),
    description=(
        "A best-first walk over OpenAlex from the library papers matching a saved search: score = keyword_weight x terms matched "
        "+ cite_weight x log10(citations + 1) + link_weight x times reached. Runs in the background; GET /api/crawl says how far "
        "it has got, and the result replaces that search's last one."
    ),
    mcp="start_crawl",
)
def start_crawl(request: Request, body: CrawlBody) -> CrawlStatusReply:
    search = found(request, body.search)
    settings = cr.Settings(body.max_visits, body.max_depth, body.min_seed_hits, body.min_novel_hits, body.api_budget,
                           body.keyword_weight, body.cite_weight, body.link_weight, body.cited_by)
    problems = settings.check()
    if problems:
        raise Refused(400, "; ".join(problems))
    from app.extras.searches import keywords

    if not keywords(search):
        raise Refused(400, "that search has no positive terms to score with")
    crawler = request.app.state.crawler
    scope = missing_scope(request)
    identity = None if scope is None else scope[1:]
    if not crawler.start(search, settings, actor_name(request), get_catalogue(request), identity):
        raise Refused(409, "a crawl is already running")
    return status_reply(request)


@route(
    "POST /api/crawl/stop", summary="Stop the crawl",
    tag=CRAWL_TAG,
    description="Stop the crawl under way; what it found so far is kept as its result.",
    mcp="stop_crawl",
)
def stop_crawl(request: Request, body: Empty) -> CrawlStatusReply:
    request.app.state.crawler.stop()
    return status_reply(request)


class CrawlResultQuery(RequestType):
    search: SearchId
    view: Annotated[Literal["novel", "visited"], QUERY, Meta(description='"novel" (default): works you lack. "visited": every work walked.')] = "novel"
    limit: Annotated[int, QUERY, Meta(ge=1, le=cr.MAX_RESULTS)] = 500


class CrawlResultReply(Reply):
    api_name: ClassVar[str] = "CrawlResult"
    run: Annotated[dict[str, Any] | None, Meta(description="The run's settings and counts, null when it never ran.")]
    works: Annotated[list[dict[str, Any]], Meta(description=(
        "wid, doi, title, journal, year, cited_by, oa_pdf, authors, score, hits (terms matched), links (times reached), depth, "
        "from / from_title / from_key (the work it was reached from, and its library key when a seed), how (cites / cited by), "
        "in_library (it has been added since)."
    ))]
    total: int


@route(
    "GET /api/crawl/{search}", summary="A saved search's last crawl",
    tag=CRAWL_TAG, errors=(404,),
    description="The works the last crawl for a saved search found, best score first.",
    mcp="get_crawl", read_only=True,
)
def crawl_result(request: Request, body: CrawlResultQuery) -> CrawlResultReply:
    search = found(request, body.search)
    result = request.app.state.crawler.result(search["id"])
    if result is None:
        return CrawlResultReply(run=None, works=[], total=0)
    rows = result.get(f"{body.view}_rows") or []
    scope = missing_scope(request)
    wids, dois, titles = request.app.state.content.pool.library if scope is None else scope[1:]
    from app.search import query as q

    for row in rows:
        row["in_library"] = row["wid"] in wids or (row.get("doi") or "").lower() in dois or q.fold(row.get("title")) in titles
    return CrawlResultReply(run={k: v for k, v in result.items() if not k.endswith("_rows")}, works=rows[:body.limit], total=len(rows))


class CrawlExportQuery(RequestType):
    search: SearchId


@route(
    "GET /api/crawl/{search}/export.xlsx", summary="A crawl as a workbook",
    tag=CRAWL_TAG, errors=(404,), reply_type=XLSX,
    description="The last crawl for a saved search: Novel and Visited sheets, with score, terms matched, links, depth and where each was reached from.",
    mcp_http="A file to download.",
)
def crawl_export(request: Request, body: CrawlExportQuery) -> Response:
    search = found(request, body.search)
    result = request.app.state.crawler.result(search["id"])
    if result is None:
        raise Refused(404, "that search has not been crawled")
    proxy = proxy_url(request)
    header = ["Score", "Terms", "Links", "Depth", "Reached from", "How"] + xlsx.WORK_HEADER
    rows = {}
    for view in ("novel", "visited"):
        rows[view] = [[r["score"], r["hits"], r["links"], r["depth"], r.get("from_title") or r.get("from") or "", r.get("how") or ""]
                      + xlsx.work_row({**r, "conn": r["links"], "lib_cites": "", "cites_lib": ""}, proxy) for r in result.get(f"{view}_rows") or []]
    return attachment(xlsx.workbook([("Novel", header, rows["novel"]), ("Visited", header, rows["visited"])]), f"crawl-{search['name']}")
