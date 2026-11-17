"""The lists' routes. A list changes only through POST .../ops, a batch of
named operations applied atomically (app/boards/ops.py has every op and its
parameters; GET /api/lists/schema lists them). The page, a script and an MCP
agent all speak the same ops, so there is one set of rules.

Creating, restoring and locking whole lists has no MCP tool: an agent edits
lists, it does not decide which exist or which may change.
"""
from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any, Callable, ClassVar, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from app.apidocs import PATH, QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.boards import cite, ops, refparse
from app.boards import store as boards
from app.boards.service import BoardService
from app.core import sse
from app.core.logs import KIND_ADMIN
from app.core.security import actor_from
from app.mcp.registry import Call
from app.routes.helpers import Page, Paged, Refused, cut_page, error, get_config, get_store
from app.routes.logs import audit

TAG = "Lists"


def get_service(request: Request) -> BoardService:
    return request.app.state.boards


def actor_name(request: Request) -> str:
    actor = actor_from(request)
    if actor is None:
        return ""
    return actor.user.display_name + (" (API key)" if actor.via_api_key else "")


def board_refused(refusal: boards.BoardError) -> Refused:
    return Refused(refusal.status, str(refusal), **refusal.extra)


Slug = Annotated[str, PATH, Meta(description='The list\'s slug, from GET /api/lists (the main list is "main").')]


class SlugPath(RequestType):
    slug: Slug


class ListsReply(Paged):
    lists: list[dict[str, Any]]


@route(
    "GET /api/lists", summary="List the lists",
    tag=TAG,
    description="Every curated list, the main one first: slug, name, rev (its version number), how many papers it holds, and whether it is view-only.",
    mcp="list_lists", read_only=True,
)
def list_lists(request: Request, body: Page) -> ListsReply:
    page = cut_page(boards.list_boards(get_store(request)), body)
    return ListsReply(lists=page.pop("rows"), **page)


class CreateList(RequestType):
    name: Annotated[str, Meta(description="The new list's name.", extra={"error": "name must be text"})]


class ListReply(Reply):
    list: dict[str, Any]


@route(
    "POST /api/lists", summary="Make a new list",
    tag=TAG,
    description="A new, empty list.",
    mcp_http="An agent edits lists; which lists exist is a person's decision.",
)
def create_list(request: Request, body: CreateList) -> ListReply:
    name = actor_name(request)
    try:
        record = boards.create_board(get_store(request), body.name, name)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    audit(request, KIND_ADMIN, "list created", {"slug": record["slug"], "name": record["name"]})
    get_service(request).changed(record["slug"], record["rev"], name)
    return ListReply(list=boards.summary(record))


@route(
    "GET /api/lists/{slug}", summary="Read a list",
    tag=TAG, errors=(404,),
    description=(
        "One list in full: its document (rows in order, each with key, title, year, tags and cells; columns; the "
        "tag vocabulary with colours), its rev, and what the library knows of each row."
    ),
    mcp="get_list", read_only=True,
)
def get_list(request: Request, body: SlugPath) -> ListReply:
    service = get_service(request)
    record = boards.get_board(service.store, body.slug)
    if record is None:
        raise Refused(404, "no such list")
    return ListReply(list=service.view(record))


def run_ops(service: BoardService, slug: str, batch: Any, user_name: str, if_rev: int | None, dry_run: bool) -> dict[str, Any]:
    """Raises BoardError."""
    applied = boards.apply_ops(service.store, slug, batch, service.ctx(), user_name, if_rev=if_rev, dry_run=dry_run)
    if applied.changed:
        service.changed(slug, applied.rev, user_name)
    body: dict[str, Any] = {"ok": True, "rev": applied.rev, "changed": applied.changed, "results": applied.results}
    record = boards.get_board(service.store, slug)
    if record is not None:
        view = service.view(record) if not dry_run else {**boards.summary(record), "doc": applied.doc, "papers": service.papers_for(applied.doc)}
        body["list"] = view
    return body


class RunOps(RequestType):
    slug: Slug
    ops: Annotated[list[dict[str, Any]], Meta(description="The ops, in order: {op, ...} each. GET /api/lists/schema names them all.")]
    if_rev: Annotated[int | None, Meta(description="Refuse the batch when the list has moved past this rev since you read it.", extra={"error": "if_rev must be a whole number"})] = None
    dry_run: Annotated[bool, Meta(description="Preview: run the ops and answer, but save nothing.", extra={"error": "dry_run must be true or false"})] = False


Results = list[Any]


class OpsReply(Reply):
    ok: bool
    rev: int
    changed: bool
    results: Results
    list: Annotated[dict[str, Any] | None, Meta(description="The list afterwards. Left out of the MCP tool's answer: get_list has it.")] = None


def without_list(call: Call, body: Any, serve: Callable[[Any, Any], Any]) -> dict[str, Any]:
    """The MCP list_ops tool's answer stays small: the whole document is in
    get_list."""
    reply = serve(call.request, body)
    return {"ok": reply.ok, "rev": reply.rev, "changed": reply.changed, "results": reply.results}


@route(
    "POST /api/lists/{slug}/ops", summary="Change a list",
    tag=TAG, errors=(403, 404, 409),
    description=(
        "Run a batch of ops against a list, atomically: every op succeeds and the list is saved once, or nothing is "
        "saved and the answer names the op that failed. Rows are named by key, DOI or \"#N\" (position). "
        "Examples: {\"op\":\"add\",\"paper\":\"<key or DOI or title>\",\"at\":\"top\"}, {\"op\":\"move\",\"row\":\"#12\",\"to\":1}, "
        "{\"op\":\"tag\",\"rows\":[\"#1\",\"#2\"],\"add\":[\"premier\"]}, {\"op\":\"set_cell\",\"row\":\"#1\",\"col\":\"Notes\",\"value\":\"key paper\",\"mode\":\"append\"}. "
        "dry_run previews; if_rev refuses the batch when the list moved since you read it. Every change keeps the "
        "previous version, so a removal can be put back."
    ),
    mcp="list_ops", destructive=True, call=without_list,
)
def post_ops(request: Request, body: RunOps) -> OpsReply:
    try:
        answer = run_ops(get_service(request), body.slug, body.ops, actor_name(request), body.if_rev, body.dry_run)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    return OpsReply(**answer)


def schema_body() -> dict[str, Any]:
    """The ported ops schema, with this app's routes in place of the old
    app's."""
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


class SchemaReply(Reply):
    about: str
    auth: str
    endpoints: dict[str, str]
    responses: Any = None
    row_selector: Any = None
    position: Any = None
    ops: Any = None
    examples: Any = None


@route(
    "GET /api/lists/schema", summary="List ops reference",
    tag=TAG,
    description="Every op POST /api/lists/{slug}/ops takes, with its parameters, plus how rows and positions are named.",
    mcp_note="Read it before a first list_ops call.",
    mcp="list_schema", read_only=True,
)
def get_schema(request: Request) -> SchemaReply:
    body = schema_body()
    known = set(SchemaReply.__struct_fields__)
    return SchemaReply(**{key: value for key, value in body.items() if key in known})


@route(
    "GET /api/lists/stream", summary="When a list changes",
    tag=TAG, reply_type="text/event-stream",
    description="Server-sent events: \"list\" {slug, rev, by} whenever any list changes.",
    mcp_http="A live event stream for the page; get_list's rev says the same when asked.",
)
async def stream_lists(request: Request) -> Response:
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


class GetRows(RequestType):
    slug: Slug
    q: Annotated[str, QUERY, Meta(description="A text filter. Read up to 500 characters.")] = ""
    tags: Annotated[str, QUERY, Meta(description="Tags to filter by, comma-separated.")] = ""
    match: Annotated[Literal["any", "all", "none"], QUERY, Meta(description="How the tags combine. Default any.", extra={"error": "match must be any, all or none"})] = "any"
    shelf: Annotated[str, QUERY, Meta(description="1 or true: the staging shelf instead of the list.")] = ""
    limit: Annotated[int, QUERY, Meta(ge=1, le=ROWS_MAX, description="Rows to return. Default 500.", extra={"error": f"limit must be 1-{ROWS_MAX}"})] = ROWS_MAX
    offset: Annotated[int, QUERY, Meta(ge=0, description="Rows to skip.", extra={"error": "offset must be 0 or more"})] = 0


Rows = list[dict[str, Any]]


class RowsReply(Reply):
    slug: str
    rev: int
    total: int
    offset: int
    rows: Rows
    columns: Rows
    tags: Rows
    options: dict[str, Any]
    list: Annotated[int, Meta(description="How many rows the list holds.")]
    shelf: Annotated[int, Meta(description="How many rows are on its staging shelf.")]


@route(
    "GET /api/lists/{slug}/rows", summary="A list as flat rows",
    tag=TAG, errors=(404,),
    description="The list as flat rows, each with its position and its cells under their column labels, filtered like the page's filter and tag bar.",
    mcp="list_rows", read_only=True,
)
def get_rows(request: Request, body: GetRows) -> RowsReply:
    tags = [t.strip() for t in body.tags.split(",") if t.strip()]
    service = get_service(request)
    record = boards.get_board(service.store, body.slug)
    if record is None:
        raise Refused(404, "no such list")
    doc = record["doc"]
    meta = service.meta([row["key"] for row in (doc.get("items") or []) + (doc.get("staging") or [])])
    view = ops.rows_view(doc, meta=meta, q=body.q[:500], tags=tags, match=body.match, shelf=body.shelf in ("1", "true"), limit=body.limit, offset=body.offset)
    known = set(RowsReply.__struct_fields__)
    return RowsReply(**{key: value for key, value in view.items() if key in known}, slug=record["slug"], rev=record.get("rev", 0))


def export_csv(service: BoardService, record: dict[str, Any], default_style: str, keep: set[str] | None) -> str:
    doc = record["doc"]
    items = doc.get("items") or []
    style = service.cite_style(doc, default_style)
    cites = service.cites(style, [row for row in items if keep is None or row["key"] in keep])
    return ops.to_csv(doc, meta=service.meta([row["key"] for row in items]), cites=cites, keep=keep)


def csv_response(request: Request, slug: str, keep: set[str] | None) -> Response:
    service = get_service(request)
    record = boards.get_board(service.store, slug)
    if record is None:
        raise Refused(404, "no such list")
    text = export_csv(service, record, get_config(request).library.cite_style, keep)
    filename = f"{record['slug']}.csv"
    return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


EXPORT_DESCRIPTION = "The list as CSV in its order: #, DOI_or_Key, Cite, Title, Year, Tags, <columns>, MD_File."


class ExportQuery(RequestType):
    slug: Slug
    keys: Annotated[str, QUERY, Meta(description="Only these rows: their keys, comma-separated. Leave out for every row.")] = ""


@route(
    "GET /api/lists/{slug}/export.csv", summary="A list as CSV",
    tag=TAG, errors=(404,), reply_type="text/csv",
    description=EXPORT_DESCRIPTION,
    mcp_http="A file to download; list_rows gives the same rows as data.",
)
def get_export_csv(request: Request, body: ExportQuery) -> Response:
    keep = {k for k in body.keys.split(",") if k} if "keys" in request.query_params else None
    return csv_response(request, body.slug, keep)


class ExportBody(RequestType):
    slug: Slug
    keys: Annotated[list[str] | None, Meta(description="Only these rows, by key: the page's filter can be thousands, too long for a URL.", extra={"error": "keys must be a list of row keys"})] = None


@route(
    "POST /api/lists/{slug}/export.csv", summary="Some of a list as CSV",
    tag=TAG, errors=(404,), reply_type="text/csv",
    description=EXPORT_DESCRIPTION + " The rows to export are in the body.",
    mcp_http="A file to download; list_rows gives the same rows as data.",
)
def post_export_csv(request: Request, body: ExportBody) -> Response:
    return csv_response(request, body.slug, None if body.keys is None else set(body.keys))


# -- versions and the view-only switch ------------------------------------------

class HistoryReply(Paged):
    versions: list[dict[str, Any]]


class GetHistory(RequestType):
    slug: Slug
    limit: Annotated[int, QUERY, Meta(ge=1, le=1000, description="Versions to return. Default 200.", extra={"error": "limit must be 1-1000"})] = 200
    offset: Annotated[int, QUERY, Meta(ge=0, description="Versions to skip.", extra={"error": "offset must be 0 or more"})] = 0


@route(
    "GET /api/lists/{slug}/history", summary="A list's past versions",
    tag=TAG, errors=(404,),
    description=(
        "The kept versions of a list (the last 40), newest first: rev, when, by whom, row and shelf counts. "
        "Version N is the list as it stood before the change that made rev N+1."
    ),
    mcp_note="list_version reads one in full. Restoring is done from the page.",
    mcp="list_history", read_only=True,
)
def get_history(request: Request, body: GetHistory) -> HistoryReply:
    try:
        rows = boards.history(get_store(request), body.slug)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    page = cut_page(rows, Page(limit=body.limit, offset=body.offset))
    return HistoryReply(versions=page.pop("rows"), **page)


class VersionPath(RequestType):
    slug: Slug
    rev: Annotated[int, PATH, Meta(ge=1, description="The version's rev, from list_history.", extra={"error": "no such version"})]


class VersionReply(Reply):
    version: dict[str, Any]


@route(
    "GET /api/lists/{slug}/history/{rev}", summary="One past version of a list",
    tag=TAG, errors=(404,),
    description="One kept version of a list, with its whole document.",
    mcp="list_version", read_only=True,
)
def get_version(request: Request, body: VersionPath) -> VersionReply:
    try:
        found = boards.version(get_store(request), body.slug, body.rev)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    return VersionReply(version=found)


class RestoreBody(RequestType):
    slug: Slug
    rev: Annotated[int, Meta(description="The kept version to put back.", extra={"error": "rev must be a whole number"})]


class RestoreReply(Reply):
    ok: bool
    rev: int
    list: dict[str, Any] | None


@route(
    "POST /api/lists/{slug}/restore", summary="Put a past version back",
    tag=TAG, errors=(403, 404),
    description="Put a kept version back as a new version, so it can be undone too. Refused while the list is view-only.",
    mcp_http="Restoring is done from the page, by a person.",
)
def post_restore(request: Request, body: RestoreBody) -> RestoreReply:
    service = get_service(request)
    name = actor_name(request)
    try:
        new_rev = boards.restore(service.store, body.slug, body.rev, name)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    audit(request, KIND_ADMIN, "list version restored", {"slug": body.slug, "rev": body.rev, "new_rev": new_rev})
    service.changed(body.slug, new_rev, name)
    record = boards.get_board(service.store, body.slug)
    return RestoreReply(ok=True, rev=new_rev, list=service.view(record) if record else None)


class LockBody(RequestType):
    slug: Slug
    locked: Annotated[bool, Meta(description="true: view-only for everyone; ops then answer 403.", extra={"error": "locked must be true or false"})]


class LockReply(Reply):
    ok: bool
    list: dict[str, Any]


@route(
    "POST /api/lists/{slug}/lock", summary="Make a list view-only, or editable",
    tag=TAG, errors=(404,),
    description="View-only for everyone: ops then answer 403 (dry runs still work). Not a change to its document, so its rev stays put.",
    mcp_http="Which lists may change is a person's decision.",
)
def post_lock(request: Request, body: LockBody) -> LockReply:
    service = get_service(request)
    name = actor_name(request)
    try:
        record = boards.set_locked(service.store, body.slug, body.locked, name)
    except boards.BoardError as refusal:
        raise board_refused(refusal) from None
    audit(request, KIND_ADMIN, "list locked" if body.locked else "list unlocked", {"slug": body.slug})
    service.changed(body.slug, record.get("rev", 0), name, locked=body.locked)
    return LockReply(ok=True, list=boards.summary(record))


# -- citations and reference lists -------------------------------------------

MAX_CITE_KEYS = 5000
Keys = list[str]


class CiteBody(RequestType):
    keys: Annotated[Keys, Meta(description="The papers' keys. At most 5000.", extra={"error": "keys must be a list of paper keys"})]
    list: Annotated[str, Meta(description="A list's slug: papers not in the library are cited from their row on it.")] = ""
    style: Annotated[str, Meta(description="A CSL style from GET /api/cite/styles. Default: the list's, else library.cite_style.")] = ""


class CiteReply(Reply):
    style: str
    cites: Annotated[dict[str, Any], Meta(description="{key: {intext, full}}.")]


@route(
    "POST /api/cite", summary="Cite papers",
    tag=TAG,
    description="Each paper's in-text and full citation in a CSL style.",
    mcp="cite_papers", read_only=True,
)
def post_cite(request: Request, body: CiteBody) -> CiteReply:
    if len(body.keys) > MAX_CITE_KEYS:
        raise Refused(400, f"at most {MAX_CITE_KEYS} keys at once")
    service = get_service(request)
    doc = None
    if body.list:
        record = boards.get_board(service.store, body.list)
        doc = record["doc"] if record else None
    resolved = cite.resolve_style(body.style, ((doc or {}).get("options") or {}).get("cite_style") or "", get_config(request).library.cite_style)
    rows_by_key = {row["key"]: row for row in ((doc or {}).get("items") or []) + ((doc or {}).get("staging") or [])}
    rows = [rows_by_key.get(k) or {"key": k} for k in body.keys]
    return CiteReply(style=resolved, cites=service.cites(resolved, rows))


class StylesReply(Reply):
    styles: list[Any]
    default: str


@route(
    "GET /api/cite/styles", summary="The citation styles",
    tag=TAG,
    description="The CSL styles on this server, usable or not (with why), and the default.",
    mcp="cite_styles", read_only=True,
)
def get_cite_styles(request: Request) -> StylesReply:
    return StylesReply(styles=cite.list_styles(), default=cite.resolve_style(get_config(request).library.cite_style))


MAX_UPLOAD = 10 * 1024 * 1024


class ParseRefs(RequestType):
    text: Annotated[str, Meta(description="A pasted reference list.")] = ""
    file: Annotated[str, Meta(description="Or a .docx or .txt file, base64. At most 10 MB.")] = ""


class ParseRefsReply(Reply):
    refs: list[Any]
    max: int
    text: Annotated[str, Meta(description="What was read, so a dropped file can go on to the stage op.")]


@route(
    "POST /api/refs/parse", summary="Read a reference list",
    tag=TAG,
    description="A pasted or dropped reference list, read and matched to the library: a preview of what the stage op puts on the shelf.",
    mcp="parse_refs", read_only=True,
)
def post_refs_parse(request: Request, body: ParseRefs) -> ParseRefsReply:
    text = body.text
    if body.file:
        try:
            data = base64.b64decode(body.file, validate=True)
        except (binascii.Error, ValueError):
            raise Refused(400, "file must be base64") from None
        if len(data) > MAX_UPLOAD:
            raise Refused(400, "that file is over 10 MB")
        try:
            text = refparse.text_from_upload(data)
        except ValueError as wrong:
            raise Refused(400, str(wrong)) from None
    if not text.strip():
        raise Refused(400, "send {text} or {file}")
    return ParseRefsReply(refs=get_service(request).parse_refs(text), max=refparse.MAX_REFS, text=text)
