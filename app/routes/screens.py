"""The Code and Datasets screens' routes, and the .xlsx export they share.

Each screen asks for all its rows at once (a few hundred papers) and sorts and
filters them in the browser, so what it exports is exactly what it shows, in
that order: the page sends the table it drew to /api/export/xlsx.
"""
from __future__ import annotations

from typing import Annotated, Any

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from app.apidocs import Reply, route
from app.apidocs import Request as RequestType
from app.content.screens import Screens
from app.extras import xlsx
from app.routes.helpers import Refused

TAG = "Code and datasets"
MAX_SHEETS = 8
MAX_ROWS = 50_000
MAX_COLUMNS = 60
XLSX = xlsx.XLSX


def get_screens(request: Request) -> Screens:
    return request.app.state.screens


class Empty(RequestType):
    pass


class CodeReply(Reply):
    papers: Annotated[list[dict[str, Any]], Meta(description=(
        "One per paper that links code: key, title, year, doi, journal, added, cites (OpenAlex), mods, lists (slug, name, "
        "position), tiers (slug, name, tier, color), figs (figures picked), and code: url, host, where, repo, info (GitHub or "
        "OSF: status, description, stars, language, methods), inferred (methods of the papers linking it), repaired (url, tier, "
        "confidence, original) for a link the PDF text mangled."
    ))]
    enrich: Annotated[dict[str, bool], Meta(description="github, osf: whether a token is set (without one that host is not asked).")]


@route(
    "GET /api/code", summary="Every paper that ships code",
    tag=TAG,
    description=(
        "One row per paper whose text links a code host, with each repository as GitHub or OSF describe it, the methods its "
        "README confirms or its citing papers suggest, and where the paper is curated."
    ),
    mcp="list_code", read_only=True,
)
def list_code(request: Request, body: Empty) -> CodeReply:
    enrich = request.app.state.settings.get().enrich
    return CodeReply(papers=get_screens(request).code_rows(), enrich={"github": bool(enrich.github_token), "osf": bool(enrich.osf_token)})


class DatasetsReply(Reply):
    papers: Annotated[list[dict[str, Any]], Meta(description=(
        "One per paper that links data or names a public collection: key, title, year, doi, added, cites, mods, lists, tiers, "
        "figs, code_n, data (url, host, where, accession when recovered from a bare ds number, target, info: status, title, "
        "description), names (name, url, description)."
    ))]


@route(
    "GET /api/datasets", summary="What public data the library stands on",
    tag=TAG,
    description=(
        "One row per paper that links a data archive record or names a public collection (HCP, NSD, ...), each record with "
        "what its archive says it is. The Datasets screen also groups these by dataset."
    ),
    mcp="list_datasets", read_only=True,
)
def list_datasets(request: Request, body: Empty) -> DatasetsReply:
    return DatasetsReply(papers=get_screens(request).dataset_rows())


class Sheet(RequestType):  # noqa: D101 -- one sheet of an export
    name: Annotated[str, Meta(description="The sheet's tab name (31 characters at most; cut to fit).")]
    columns: Annotated[list[str], Meta(description="The header row.")]
    rows: Annotated[list[list[Any]], Meta(description="The rows: text, numbers, or null. A cell that is an http(s) URL becomes a link.")]


class XlsxBody(RequestType):
    sheets: Annotated[list[Sheet], Meta(description=f"The sheets, in order. At most {MAX_SHEETS}.", extra={"error": 'send {"sheets": [{"name", "columns", "rows"}]}'})]
    filename: Annotated[str, Meta(description="The download's name, without .xlsx.")] = "export"


@route(
    "POST /api/export/xlsx", summary="A table as an Excel workbook",
    tag=TAG, reply_type=XLSX,
    description=(
        "Turns the tables a screen is showing into one .xlsx: a sheet each, the header frozen and bold, links clickable. "
        "The screens send exactly the rows they show, in their order."
    ),
    mcp_http="A file to download, made from the rows sent.",
)
def export_xlsx(request: Request, body: XlsxBody) -> Response:
    if not body.sheets or len(body.sheets) > MAX_SHEETS:
        raise Refused(400, f"send 1 to {MAX_SHEETS} sheets")
    if sum(len(s.rows) for s in body.sheets) > MAX_ROWS or any(len(s.columns) > MAX_COLUMNS for s in body.sheets):
        raise Refused(400, f"at most {MAX_ROWS} rows and {MAX_COLUMNS} columns")
    data = xlsx.workbook([(sheet.name, sheet.columns, sheet.rows) for sheet in body.sheets])
    name = xlsx.filename(body.filename)
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
