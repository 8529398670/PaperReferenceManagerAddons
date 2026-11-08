"""The lists' routes. A list changes only through POST .../ops, a batch of
named operations applied atomically (app/boards/ops.py has every op and its
parameters; GET /api/lists/schema lists them). The page, a script and an MCP
agent all speak the same ops, so there is one set of rules.
"""
from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.boards import ops, store as boards
from app.boards.service import BoardService
from app.core import sse
from app.core.security import actor_from, check_csrf
from app.routes.helpers import error, forbidden, get_store, not_found, read_json, run, send_page
from app.core.logs import KIND_ADMIN
from app.routes.logs import audit


def get_service(request: Request) -> BoardService:
    return request.app.state.boards


def actor_name(request: Request) -> str:
    actor = actor_from(request)
    if actor is None:
        return ""
    return actor.user.display_name + (" (API key)" if actor.via_api_key else "")


def board_refused(refusal: boards.BoardError) -> JSONResponse:
    return JSONResponse({"error": str(refusal), **refusal.extra}, status_code=refusal.status)


async def list_lists(request: Request) -> Response:
    return send_page(request, "lists", await run(boards.list_boards, get_store(request)))


async def create_list(request: Request) -> Response:
    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    name = body.get("name")
    if not isinstance(name, str):
        return error(400, "name must be text")
    try:
        record = await run(boards.create_board, get_store(request), name, actor_name(request))
    except boards.BoardError as refusal:
        return board_refused(refusal)
    audit(request, KIND_ADMIN, "list created", {"slug": record["slug"], "name": record["name"]})
    get_service(request).changed(record["slug"], record["rev"], actor_name(request))
    return JSONResponse({"list": boards.summary(record)})


def view_or_none(service: BoardService, slug: str) -> dict[str, Any] | None:
    record = boards.get_board(service.store, slug)
    return None if record is None else service.view(record)


async def get_list(request: Request) -> Response:
    view = await run(view_or_none, get_service(request), request.path_params["slug"])
    if view is None:
        return not_found("no such list")
    return JSONResponse({"list": view})


def run_ops(service: BoardService, slug: str, batch: Any, user_name: str, if_rev: int | None, dry_run: bool) -> dict[str, Any]:
    """Shared with the MCP list_ops tool. Raises BoardError."""
    applied = boards.apply_ops(service.store, slug, batch, service.ctx(), user_name, if_rev=if_rev, dry_run=dry_run)
    if applied.changed:
        service.changed(slug, applied.rev, user_name)
    body: dict[str, Any] = {"ok": True, "rev": applied.rev, "changed": applied.changed, "results": applied.results}
    record = boards.get_board(service.store, slug)
    if record is not None:
        view = service.view(record) if not dry_run else {**boards.summary(record), "doc": applied.doc, "papers": service.papers_for(applied.doc)}
        body["list"] = view
    return body


async def post_ops(request: Request) -> Response:
    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    if_rev = body.get("if_rev")
    if if_rev is not None and (not isinstance(if_rev, int) or isinstance(if_rev, bool)):
        return error(400, "if_rev must be a whole number")
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        return error(400, "dry_run must be true or false")
    try:
        answer = await run(run_ops, get_service(request), request.path_params["slug"], body.get("ops"), actor_name(request), if_rev, dry_run)
    except boards.BoardError as refusal:
        return board_refused(refusal)
    return JSONResponse(answer)


def schema_body() -> dict[str, Any]:
    """The ported ops schema, with this app's routes in place of the old
    app's. Shared with the MCP list_schema tool."""
    body = ops.schema()
    body["about"] = (
        "Edit a list one named operation at a time. POST /api/lists/<slug>/ops runs a batch atomically: "
        "every op succeeds and the list is saved once, as one new rev, or nothing is saved."
    )
    body["auth"] = "A signed-in browser session (with csrf_token in the body), or Authorization: Bearer <API key>."
    body["endpoints"] = {
        "GET /api/lists": "every list: {slug, name, rev, count, shelf, locked}, the main list first",
        "POST /api/lists": "{name} -- a new, empty list",
        "GET /api/lists/<slug>": "the list: its document (doc), rev, and what the library knows of each row (papers)",
        "POST /api/lists/<slug>/ops": "{ops: [{op, ...}], if_rev?: rev, dry_run?: bool}",
        "GET /api/lists/schema": "this document",
        "GET /api/lists/stream": "server-sent events: list {slug, rev, by} on every change",
    }
    body.pop("examples", None)
    return body


async def get_schema(request: Request) -> Response:
    """Every op, its parameters and what it does."""
    return JSONResponse(schema_body())


async def stream_lists(request: Request) -> Response:
    """"list" {slug, rev, by} whenever any list changes."""
    if request.method == "HEAD":
        return Response(headers=sse.HEADERS)
    from app.routes.streams import still_signed_in

    hub = get_service(request).hub
    client = hub.join()
    if client is None:
        return error(503, "too many live streams")
    return sse.EventStream(hub, client, still_signed_in(request), opening=(sse.retry(sse.RETRY_MS),))
