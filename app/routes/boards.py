"""The lists' routes. A list changes only through POST .../ops, a batch of
named operations applied atomically (app/boards/ops.py has every op and its
parameters; GET /api/lists/schema lists them). The page, a script and an MCP
agent all speak the same ops, so there is one set of rules.
"""
from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.boards import cite, refparse

from app.boards import ops, store as boards
from app.boards.service import BoardService
from app.core import sse
from app.core.security import actor_from, check_csrf
from app.routes.helpers import PAGE_MAX, bad_request, error, forbidden, get_config, get_store, not_found, read_json, run, send_page, whole_number
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
        "GET /api/lists/<slug>/rows": "the list as flat rows: ?q= text filter, ?tags=a,b&match=any|all|none, ?shelf=1 for the staging shelf, ?limit= (max 500) &offset=",
        "GET /api/lists/<slug>/export.csv": "the list as CSV in its order: #, DOI_or_Key, Cite, Title, Year, Tags, <columns>, MD_File. ?keys=k1,k2 (or POST {keys}) exports only those rows",
        "GET /api/lists/<slug>/history": "kept versions, newest first: {rev, at, by, rows, shelf} (the last 40)",
        "GET /api/lists/<slug>/history/<rev>": "one kept version, with its doc",
        "POST /api/lists/<slug>/restore": "{rev} -- put a kept version back as a new version (so it can be undone too)",
        "POST /api/lists/<slug>/lock": "{locked: bool} -- view-only for everyone; ops then answer 403 (dry runs still work)",
        "POST /api/cite": "{keys: [...], style?} -> {style, cites: {key: {intext, full}}}",
        "GET /api/cite/styles": "the CSL styles on this server, usable or not (with why)",
        "POST /api/refs/parse": "{text} or {file: base64 of a .docx/.txt} -> the references read and matched to the library (what the stage op would put on the shelf)",
        "GET /api/lists/schema": "this document",
        "GET /api/lists/stream": "server-sent events: list {slug, rev, by, locked?} on every change",
    }
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


# -- reading a list as rows, or as CSV -----------------------------------------

ROWS_MAX = 500


async def get_rows(request: Request) -> Response:
    """The list as flat rows, filtered like the page's filter and tag bar."""
    params = request.query_params
    match = params.get("match", "any")
    if match not in ops.MATCHES:
        return bad_request("match must be any, all or none")
    limit = whole_number(params.get("limit"), ROWS_MAX)
    offset = whole_number(params.get("offset"), 0)
    if limit is None or not 1 <= limit <= ROWS_MAX:
        return bad_request(f"limit must be 1-{ROWS_MAX}")
    if offset is None or offset < 0:
        return bad_request("offset must be 0 or more")
    tags = [t.strip() for t in params.get("tags", "").split(",") if t.strip()]
    service = get_service(request)
    record = await run(boards.get_board, service.store, request.path_params["slug"])
    if record is None:
        return not_found("no such list")
    doc = record["doc"]
    meta = service.meta([row["key"] for row in (doc.get("items") or []) + (doc.get("staging") or [])])
    body = ops.rows_view(doc, meta=meta, q=params.get("q", "")[:500], tags=tags, match=match, shelf=params.get("shelf") in ("1", "true"), limit=limit, offset=offset)
    return JSONResponse({**body, "slug": record["slug"], "rev": record.get("rev", 0)})


def export_csv(service: BoardService, record: dict[str, Any], default_style: str, keep: set[str] | None) -> str:
    doc = record["doc"]
    items = doc.get("items") or []
    style = service.cite_style(doc, default_style)
    cites = service.cites(style, [row for row in items if keep is None or row["key"] in keep])
    return ops.to_csv(doc, meta=service.meta([row["key"] for row in items]), cites=cites, keep=keep)


async def get_export_csv(request: Request) -> Response:
    service = get_service(request)
    record = await run(boards.get_board, service.store, request.path_params["slug"])
    if record is None:
        return not_found("no such list")
    if request.method == "POST":
        # The page's filter can be thousands of keys: too long for a URL.
        body = await read_json(request)
        if body is None:
            return error(400, "malformed request body")
        if not check_csrf(request, body.get("csrf_token")):
            return forbidden("missing or invalid csrf_token")
        keys = body.get("keys")
        if keys is not None and (not isinstance(keys, list) or not all(isinstance(k, str) for k in keys)):
            return bad_request("keys must be a list of row keys")
        keep = None if keys is None else set(keys)
    else:
        raw = request.query_params.get("keys")
        keep = None if raw is None else {k for k in raw.split(",") if k}
    text = await run(export_csv, service, record, get_config(request).library.cite_style, keep)
    filename = f"{record['slug']}.csv"
    return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# -- versions and the view-only switch ------------------------------------------

async def get_history(request: Request) -> Response:
    try:
        rows = await run(boards.history, get_store(request), request.path_params["slug"])
    except boards.BoardError as refusal:
        return board_refused(refusal)
    return send_page(request, "versions", rows)


async def get_version(request: Request) -> Response:
    rev = whole_number(request.path_params["rev"], -1)
    if rev is None or rev < 1:
        return not_found("no such version")
    try:
        found = await run(boards.version, get_store(request), request.path_params["slug"], rev)
    except boards.BoardError as refusal:
        return board_refused(refusal)
    return JSONResponse({"version": found})


async def post_restore(request: Request) -> Response:
    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    rev = body.get("rev")
    if not isinstance(rev, int) or isinstance(rev, bool):
        return bad_request("rev must be a whole number")
    service = get_service(request)
    slug = request.path_params["slug"]
    name = actor_name(request)
    try:
        new_rev = await run(boards.restore, service.store, slug, rev, name)
    except boards.BoardError as refusal:
        return board_refused(refusal)
    audit(request, KIND_ADMIN, "list version restored", {"slug": slug, "rev": rev, "new_rev": new_rev})
    service.changed(slug, new_rev, name)
    record = await run(boards.get_board, service.store, slug)
    return JSONResponse({"ok": True, "rev": new_rev, "list": service.view(record) if record else None})


async def post_lock(request: Request) -> Response:
    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    locked = body.get("locked")
    if not isinstance(locked, bool):
        return bad_request("locked must be true or false")
    service = get_service(request)
    slug = request.path_params["slug"]
    name = actor_name(request)
    try:
        record = await run(boards.set_locked, service.store, slug, locked, name)
    except boards.BoardError as refusal:
        return board_refused(refusal)
    audit(request, KIND_ADMIN, "list locked" if locked else "list unlocked", {"slug": slug})
    service.changed(slug, record.get("rev", 0), name, locked=locked)
    return JSONResponse({"ok": True, "list": boards.summary(record)})


# -- citations and reference lists -------------------------------------------

MAX_CITE_KEYS = 5000


async def post_cite(request: Request) -> Response:
    """{keys, style?} -> {style, cites: {key: {intext, full}}}. Papers not in
    the library are cited from their row on `list` when one is named."""
    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    keys = body.get("keys")
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        return bad_request("keys must be a list of paper keys")
    if len(keys) > MAX_CITE_KEYS:
        return error(413, f"at most {MAX_CITE_KEYS} keys at once")
    service = get_service(request)
    doc = None
    slug = body.get("list")
    if isinstance(slug, str) and slug:
        record = await run(boards.get_board, service.store, slug)
        doc = record["doc"] if record else None
    style = body.get("style") if isinstance(body.get("style"), str) else ""
    resolved = cite.resolve_style(style, ((doc or {}).get("options") or {}).get("cite_style") or "", get_config(request).library.cite_style)
    rows_by_key = {row["key"]: row for row in ((doc or {}).get("items") or []) + ((doc or {}).get("staging") or [])}
    rows = [rows_by_key.get(k) or {"key": k} for k in keys]
    cites = await run(service.cites, resolved, rows)
    return JSONResponse({"style": resolved, "cites": cites})


async def get_cite_styles(request: Request) -> Response:
    styles = await run(cite.list_styles)
    return JSONResponse({"styles": styles, "default": cite.resolve_style(get_config(request).library.cite_style)})


MAX_UPLOAD = 10 * 1024 * 1024


async def post_refs_parse(request: Request) -> Response:
    """A pasted or dropped reference list, read and matched: a preview of what
    the stage op puts on the shelf. {text} or {file: base64}."""
    import base64
    import binascii

    body = await read_json(request)
    if body is None:
        return error(400, "malformed request body")
    if not check_csrf(request, body.get("csrf_token")):
        return forbidden("missing or invalid csrf_token")
    text = body.get("text")
    if isinstance(body.get("file"), str):
        try:
            data = base64.b64decode(body["file"], validate=True)
        except (binascii.Error, ValueError):
            return bad_request("file must be base64")
        if len(data) > MAX_UPLOAD:
            return error(413, "that file is over 10 MB")
        try:
            text = refparse.text_from_upload(data)
        except ValueError as wrong:
            return bad_request(str(wrong))
    if not isinstance(text, str) or not text.strip():
        return bad_request("send {text} or {file}")
    found = await run(get_service(request).parse_refs, text)
    # text: what was read, so a dropped file can go on to the stage op.
    return JSONResponse({"refs": found, "max": refparse.MAX_REFS, "text": text})
