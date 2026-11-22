"""Adding papers: the routes the Zotero plugin (zotero-plugin/) calls.

A new paper in desktop Zotero is sent as Zotero's JSON (POST
/api/ingest/items), then each attachment's file in pieces (POST
/api/ingest/file). Both pass straight on to the caller's ZoteroWebDAV
library -- their own, else the server's for admins -- see
app/library/ingest.py. Nothing names the library's address or key.
"""
from __future__ import annotations

from typing import Annotated, Any, ClassVar

from msgspec import Meta
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.apidocs import QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.core.security import actor_from
from app.library import ingest
from app.routes.helpers import Refused, get_config

TAG = "Ingest"
WHY_NO_TOOL = "For the Zotero plugin, which sends a paper's Zotero JSON and files; an agent has neither."


def _target(request: Request) -> ingest.Target:
    cfg, actor = get_config(request), actor_from(request)
    libraries = getattr(request.app.state, "libraries", None)
    if libraries is None:
        raise Refused(409, "this server has no library registry")
    try:
        return ingest.target_for(libraries, actor.user, actor.is_admin, cfg.secret_key, cfg.library.source)
    except ingest.IngestError as refused:
        raise Refused(refused.status, str(refused)) from None


class IngestTarget(Reply, kw_only=True):
    """Where papers you send go."""

    api_name: ClassVar[str] = "IngestTarget"
    writable: Annotated[bool, Meta(description="Whether papers you send can be stored. false: reason says why.")]
    kind: Annotated[str, Meta(description='"own": your own library (the Account screen). "server": the server\'s library. Empty when writable is false.')]
    reason: Annotated[str, Meta(description="Why papers cannot be stored. Empty when they can.")]
    chunk_bytes: Annotated[int, Meta(description="How long each piece of a file sent to POST /api/ingest/file must be, all but the last.")]


@route(
    "GET /api/ingest/target", summary="Where papers you send go",
    tag=TAG, mcp_http=WHY_NO_TOOL,
    description="Your own library if you connected one on the Account screen, else the server's library (admins "
    "only, and only when it is a ZoteroWebDAV server). Never names the library's address. The Zotero plugin's "
    "Test connection button asks this.",
)
def ingest_target(request: Request) -> IngestTarget:
    try:
        target = _target(request)
    except Refused as refused:
        if refused.status >= 500:
            raise
        return IngestTarget(writable=False, kind="", reason=refused.message, chunk_bytes=ingest.UPLOAD_PIECE)
    return IngestTarget(writable=True, kind=target.kind, reason="", chunk_bytes=ingest.UPLOAD_PIECE)


class IngestItems(RequestType):
    items: Annotated[list[dict[str, Any]], Meta(description=(
        "Each {key, data}: data is Zotero's JSON for the item (Zotero.Item.toJSON(), the web API's data object), "
        "key its 8-character Zotero key. The paper, then its attachments and notes (parentItem names the paper)."
    ))] = []
    collections: Annotated[list[dict[str, Any]], Meta(description=(
        "Each {key, data}: Zotero's JSON for a collection the items are filed in, and its parents. Optional."
    ))] = []


class IngestResult(Reply, kw_only=True):
    api_name: ClassVar[str] = "IngestResult"
    kind: Annotated[str, Meta(description='"item" or "collection".')]
    key: str
    ok: bool
    changed: Annotated[bool, Meta(description="false when the library already had exactly this.")]
    error: Annotated[str, Meta(description="Why it was not stored. Empty when ok.")]


class IngestItemsReply(Reply, kw_only=True):
    api_name: ClassVar[str] = "IngestItemsReply"
    results: Annotated[list[IngestResult], Meta(description="One per record: collections first, then items, each parent before its children.")]
    stored: int
    failed: int


@route(
    "POST /api/ingest/items", summary="Add papers to your library",
    tag=TAG, mcp_http=WHY_NO_TOOL, errors=(400, 403, 409, 424),
    description="Stores items and collections, as Zotero's JSON and with their Zotero keys, in the library GET "
    "/api/ingest/target names. Collections go first, then each item after its parent. Sending the same again "
    "changes nothing. At most 200 items and 200 collections. Then send each attachment's file to POST "
    "/api/ingest/file. The paper shows up in the library seconds later.",
)
def ingest_items(request: Request, body: IngestItems) -> IngestItemsReply:
    target = _target(request)
    try:
        stored = ingest.store(target, body.items, body.collections)
    except ingest.IngestError as refused:
        raise Refused(refused.status, str(refused)) from None
    return IngestItemsReply(
        results=[IngestResult(**r) for r in stored["results"]],
        stored=stored["stored"], failed=stored["failed"],
    )


class IngestFile(RequestType):
    key: Annotated[str, QUERY, Meta(description="The attachment item's Zotero key, stored first with POST /api/ingest/items.")] = ""
    filename: Annotated[str, QUERY, Meta(description="The file's name, without folders.", max_length=255)] = ""
    size: Annotated[int, QUERY, Meta(ge=1, description="The whole file's size in bytes.")] = 1
    offset: Annotated[int, QUERY, Meta(ge=0, description="Where this piece starts: a multiple of chunk_bytes (GET /api/ingest/target). 0 starts the file over.")] = 0
    mtime: Annotated[int, QUERY, Meta(ge=0, description="The file's modification time, in milliseconds since 1970. Default: now.")] = 0


class IngestFileReply(Reply, kw_only=True):
    api_name: ClassVar[str] = "IngestFileReply"
    received: Annotated[int, Meta(description="Bytes of the file the library holds so far.")]
    done: Annotated[bool, Meta(description="The whole file arrived and is stored.")]


@route(
    "POST /api/ingest/file", summary="Send a piece of an attachment's file",
    tag=TAG, mcp_http=WHY_NO_TOOL, body_type="application/octet-stream", errors=(400, 403, 404, 409, 413, 424),
    description="The body is one piece of the file, starting at offset: chunk_bytes long, but the last, which "
    "ends the file. Send the pieces in order. When the last arrives the library stores the file as Zotero's "
    "WebDAV sync does, and the attachment opens in PRMA.",
)
async def ingest_file(request: Request, body: IngestFile) -> IngestFileReply:
    length = request.headers.get("content-length") or ""
    if length.isdigit() and int(length) > ingest.UPLOAD_PIECE:
        raise Refused(413, f"a piece is at most {ingest.UPLOAD_PIECE} bytes")
    data = await request.body()
    if len(data) > ingest.UPLOAD_PIECE:
        raise Refused(413, f"a piece is at most {ingest.UPLOAD_PIECE} bytes")
    target = await run_in_threadpool(_target, request)
    try:
        reply = await run_in_threadpool(ingest.store_piece, target, body.key, body.filename, body.size, body.offset, body.mtime, data)
    except ingest.IngestError as refused:
        raise Refused(refused.status, str(refused)) from None
    return IngestFileReply(received=reply["received"], done=reply["done"])
