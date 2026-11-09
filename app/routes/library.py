"""The library's routes: the papers in Zotero, searched and paged; one paper;
its PDF; the userscripts' "do I have this" check; and the live stream that
says when the library moved.

Everything reads the in-memory catalogue (app/library/catalogue.py), so none
of it waits on Zotero. The search runs in a worker thread anyway: a full-text
query reads the index file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from app.core import sse
from app.core.security import actor_from
from app.library.catalogue import SORTS, Catalogue, public, sort_papers
from app.routes.helpers import PAGE_MAX, bad_request, error, get_config, not_found, read_json, run, whole_number

MAX_EXISTS_QUERIES = 5000
PAGE_DEFAULT = 50


def get_catalogue(request: Request) -> Catalogue:
    return request.app.state.library.catalogue


def status_body(catalogue: Catalogue) -> dict[str, Any]:
    status = catalogue.status
    return {
        "ready": status.ready,
        "papers": status.papers,
        "with_text": status.with_text,
        "text_pending": status.text_pending,
        "error": status.error,
        "rev": catalogue.rev,
    }


def search_page(catalogue: Catalogue, text: str, mode: str, sort: str, descending: bool, limit: int, offset: int) -> dict[str, Any]:
    """Shared with the MCP search_library tool."""
    result = catalogue.search(text, mode=mode)
    rows = sort_papers(result.rows, sort, descending, result.scores)
    total = len(rows)
    page = rows[offset : offset + limit]
    end = offset + len(page)
    return {
        "papers": [{**public(paper), "score": result.scores.get(paper.key)} for paper in page],
        "next": end if end < total else None,
        "total": total,
        "fuzzy": result.fuzzy,
        "status": status_body(catalogue),
    }


async def list_papers(request: Request) -> Response:
    params = request.query_params
    mode = params.get("mode", "text")
    if mode not in ("text", "title"):
        return bad_request("mode must be text or title")
    sort = params.get("sort", "relevance")
    if sort not in SORTS:
        return bad_request("sort must be one of: " + ", ".join(SORTS))
    direction = params.get("dir", "desc")
    if direction not in ("asc", "desc"):
        return bad_request("dir must be asc or desc")
    limit = whole_number(params.get("limit"), PAGE_DEFAULT)
    offset = whole_number(params.get("offset"), 0)
    if limit is None or not 1 <= limit <= PAGE_MAX:
        return bad_request("limit must be 1-1000")
    if offset is None or offset < 0:
        return bad_request("offset must be 0 or more")
    query = params.get("q", "")[:500]
    body = await run(search_page, get_catalogue(request), query, mode, sort, direction == "desc", limit, offset)
    return JSONResponse(body)


def recent_page(catalogue: Catalogue, store: Any, days: int, not_on: str, limit: int, offset: int) -> dict[str, Any] | None:
    """Papers added in Zotero in the last `days`, newest first, leaving out
    those already on list `not_on`. None when that list does not exist."""
    from datetime import datetime, timedelta, timezone

    from app.boards import store as boards

    have: set[str] = set()
    if not_on:
        record = boards.get_board(store, not_on)
        if record is None:
            return None
        doc = record["doc"]
        have = {row["key"] for row in (doc.get("items") or [])}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [p for p in catalogue.all() if (p.record.get("date_added") or "") >= since and p.key not in have]
    rows.sort(key=lambda p: p.record.get("date_added") or "", reverse=True)
    page = rows[offset : offset + limit]
    end = offset + len(page)
    return {"papers": [public(p) for p in page], "next": end if end < len(rows) else None, "total": len(rows)}


async def recent_papers(request: Request) -> Response:
    """"What did I save this week that isn't on this list yet?" Read from the
    live catalogue, so a paper saved seconds ago is there."""
    params = request.query_params
    days = whole_number(params.get("days"), 7)
    limit = whole_number(params.get("limit"), PAGE_DEFAULT)
    offset = whole_number(params.get("offset"), 0)
    if days is None or not 1 <= days <= 3650:
        return bad_request("days must be 1-3650")
    if limit is None or not 1 <= limit <= PAGE_MAX:
        return bad_request("limit must be 1-1000")
    if offset is None or offset < 0:
        return bad_request("offset must be 0 or more")
    body = await run(recent_page, get_catalogue(request), request.app.state.store, days, params.get("not_on", ""), limit, offset)
    if body is None:
        return not_found("no such list")
    return JSONResponse(body)


async def library_status(request: Request) -> Response:
    return JSONResponse(status_body(get_catalogue(request)))


async def get_paper(request: Request) -> Response:
    paper = get_catalogue(request).find(request.query_params.get("key", ""))
    if paper is None:
        return not_found("no such paper in the library")
    return JSONResponse({"paper": public(paper, full=True)})


async def get_pdf(request: Request) -> Response:
    """The paper's first PDF that is on disk. Only a path Zotero recorded for
    that paper is ever served, never one the request names."""
    paper = get_catalogue(request).find(request.query_params.get("key", ""))
    if paper is None:
        return not_found("no such paper in the library")
    for name in paper.record.get("pdfs") or []:
        path = Path(name)
        if path.is_file():
            # inline, so the browser's own viewer opens it.
            return FileResponse(path, media_type="application/pdf", content_disposition_type="inline", filename=path.name)
    return not_found("this paper has no PDF on disk")


def exists_rows(catalogue: Catalogue, queries: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for query in queries:
        if not isinstance(query, dict):
            continue
        doi = str(query.get("doi") or "")[:400]
        title = str(query.get("title") or "")[:1000]
        rows.append({"id": query.get("id"), "exists": catalogue.exists(doi, title), "title": query.get("title"), "doi": query.get("doi")})
    return rows


async def post_exists(request: Request) -> Response:
    """The userscripts' question: which of these papers is in the library.
    {"queries": [{"id", "title", "doi"}]} -> {"results": [{"id", "exists",
    "title", "doi"}]}. A DOI settles it; a title is matched only without one.
    Called with an API key (Authorization: Bearer), so it needs no CSRF token;
    a browser session sends one like any other POST."""
    body = await read_json(request)
    if body is None or not isinstance(body.get("queries"), list):
        return bad_request('send {"queries": [{"id": ..., "title": ..., "doi": ...}]}')
    actor = actor_from(request)
    if actor is not None and not actor.via_api_key:
        from app.core.security import check_csrf

        if not check_csrf(request, body.get("csrf_token")):
            return error(403, "missing or invalid csrf_token")
    queries = body["queries"]
    if len(queries) > MAX_EXISTS_QUERIES:
        return error(413, f"at most {MAX_EXISTS_QUERIES} queries at once")
    return JSONResponse({"results": await run(exists_rows, get_catalogue(request), queries)})


async def get_version(request: Request) -> Response:
    """A token that changes whenever the library does, so a userscript can
    poll cheaply and re-ask only then."""
    catalogue = get_catalogue(request)
    return JSONResponse({"version": catalogue.version(), "papers": catalogue.status.papers})


async def get_config_links(request: Request) -> Response:
    """What the page needs to build a paper's links."""
    return JSONResponse({"proxy_url": get_config(request).library.proxy_url})


async def stream_library(request: Request) -> Response:
    """"changed" when papers were added, changed or removed, "progress" while
    full text is being indexed. The page fetches what it shows again."""
    if request.method == "HEAD":
        return Response(headers=sse.HEADERS)
    from app.routes.streams import still_signed_in

    hub: sse.Hub = request.app.state.library.hub
    client = hub.join()
    if client is None:
        return error(503, "too many live streams")
    allowed = still_signed_in(request)
    return sse.EventStream(hub, client, allowed, opening=(sse.retry(sse.RETRY_MS),))
