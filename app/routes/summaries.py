"""LLM summaries of papers' sections, made on request, and their rollup; and
each list's Google Sheets mirror. See app/extras/summaries.py and
app/boards/sheetsync.py.
"""
from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from app.apidocs import PATH, QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.boards import store as boards
from app.extras import xlsx
from app.extras.summaries import DISPLAY, SECTION_KEYS, Summaries
from app.routes.boards import actor_name
from app.routes.helpers import Refused
from app.routes.library import find_paper

TAG = "Summaries"
SHEETS_TAG = "Google Sheets"
MAX_KEYS = 2000

Section = Literal["all", "abstract", "introduction", "background", "methods", "results", "conclusions", "future"]
SECTION_HELP = "all (the whole text), abstract, introduction, background, methods, results, conclusions or future."


def get_summaries(request: Request) -> Summaries:
    return request.app.state.summaries


class Empty(RequestType):
    pass


class StatusReply(Reply):
    api_name: ClassVar[str] = "SummariesStatus"
    provider: Annotated[str, Meta(description='The provider config.yaml picks: claude, openai or gemini; "" when no key is set.')]
    model: str
    queued: int
    running: Annotated[list[str] | None, Meta(description="[paper key, section] being summarised now.")]
    failed: int
    done: Annotated[int, Meta(description="Summaries made since the server started.")]
    counts: Annotated[dict[str, int], Meta(description="Summaries kept, by section.")]
    sections: Annotated[list[list[str]], Meta(description="[key, display name] of each section.")]


@route(
    "GET /api/summaries/status", summary="The summaries queue",
    tag=TAG,
    description="Which language model writes the summaries, what is queued, and how many are kept per section.",
    mcp="summaries_status", read_only=True,
)
def summaries_status(request: Request, body: Empty) -> StatusReply:
    service = get_summaries(request)
    return StatusReply(**service.status(), counts=service.counts(), sections=[[k, DISPLAY[k]] for k in SECTION_KEYS])


class PaperQuery(RequestType):
    key: Annotated[str, QUERY, Meta(description="The paper's key.")] = ""


class PaperReply(Reply):
    api_name: ClassVar[str] = "PaperSummaries"
    summaries: Annotated[dict[str, dict[str, Any]], Meta(description=(
        "By section: hashtags, summary (Markdown), provider, model, at, by, cut (the text was too long and was cut), and state "
        "(done, queued, running, failed) with error."
    ))]


@route(
    "GET /api/summaries/paper", summary="One paper's summaries",
    tag=TAG, errors=(404,),
    description="Every summary kept for a paper, and those queued or failed.",
    mcp="get_paper_summaries", read_only=True,
)
def paper_summaries(request: Request, body: PaperQuery) -> PaperReply:
    if not body.key or find_paper(request, body.key)[0] is None:
        raise Refused(404, "no such paper")
    return PaperReply(summaries=get_summaries(request).of_paper(body.key))


class RequestBody(RequestType):
    keys: Annotated[list[str], Meta(description=f"Paper keys, at most {MAX_KEYS}.", extra={"error": 'send {"keys": [...], "sections": [...]}'})]
    sections: Annotated[list[Section], Meta(description="Sections to summarise: " + SECTION_HELP, extra={"error": "sections are: " + ", ".join(SECTION_KEYS)})]
    force: Annotated[bool, Meta(description="Summarise again a section already summarised.")] = False


class RequestReply(Reply):
    api_name: ClassVar[str] = "SummariesQueued"
    queued: int
    kept: Annotated[int, Meta(description="Already summarised, left alone (send force to redo).")]
    unknown: Annotated[int, Meta(description="Keys that are not library papers.")]


@route(
    "POST /api/summaries", summary="Summarise papers",
    tag=TAG, status=202, errors=(400, 409),
    description=(
        "Queue LLM summaries of these papers' sections. One call each, in the background, with config.yaml's llm: provider; "
        "each one costs money, so a section already summarised is skipped unless force. Progress arrives on the library stream "
        "as \"summary\" events."
    ),
    mcp="summarize_papers",
)
def request_summaries(request: Request, body: RequestBody) -> RequestReply:
    service = get_summaries(request)
    if service.choice() is None:
        raise Refused(409, "no language model is set up: add a key to the llm: section of config.yaml")
    keys = [k for k in dict.fromkeys(str(k).strip() for k in body.keys) if k][:MAX_KEYS]
    if not keys or not body.sections:
        raise Refused(400, 'send {"keys": [...], "sections": [...]}')
    out = service.request(keys, list(dict.fromkeys(body.sections)), body.force, actor_name(request), first=len(keys) == 1)
    return RequestReply(**out)


@route(
    "POST /api/summaries/cancel", summary="Empty the summaries queue",
    tag=TAG,
    description="Drop every queued summary; the one being written finishes.",
    mcp="cancel_summaries",
)
def cancel_summaries(request: Request, body: Empty) -> RequestReply:
    return RequestReply(queued=-get_summaries(request).cancel(), kept=0, unknown=0)


class DeleteBody(RequestType):
    key: Annotated[str, Meta(min_length=1)]
    section: Section


class DeleteReply(Reply):
    api_name: ClassVar[str] = "SummaryDeleted"
    summary: Annotated[dict[str, Any] | None, Meta(description="The summary as it was, for undo (POST /api/summaries/put).")]


@route(
    "POST /api/summaries/delete", summary="Delete a summary",
    tag=TAG,
    description="Forget one paper's summary of one section.",
    mcp="delete_summary", destructive=True,
)
def delete_summary(request: Request, body: DeleteBody) -> DeleteReply:
    return DeleteReply(summary=get_summaries(request).delete(body.key, body.section))


class PutBody(RequestType):
    key: Annotated[str, Meta(min_length=1)]
    section: Section
    summary: Annotated[dict[str, Any], Meta(description="{hashtags, summary, provider, model, at, by}: what delete answered.")]


@route(
    "POST /api/summaries/put", summary="Put a summary back",
    tag=TAG, errors=(400, 404),
    description="Undo a delete: the summary as it was.",
    mcp_http="The page's undo; an agent asks for the summary again with summarize_papers.",
)
def put_summary(request: Request, body: PutBody) -> DeleteReply:
    if find_paper(request, body.key)[0] is None:
        raise Refused(404, "no such paper")
    record = {k: body.summary.get(k) for k in ("hashtags", "summary", "provider", "model", "at", "by", "cut", "legacy") if k in body.summary}
    if not isinstance(record.get("summary"), str) or not record["summary"]:
        raise Refused(400, "send the summary delete answered")
    get_summaries(request).put(body.key, body.section, record)
    return DeleteReply(summary=record)


class RollupQuery(RequestType):
    section: Annotated[Section, QUERY, Meta(description="The section to roll up: " + SECTION_HELP)] = "methods"


class RollupReply(Reply):
    api_name: ClassVar[str] = "SummariesRollup"
    section: str
    columns: Annotated[list[str], Meta(description='The "**Subsection.**" headers the summaries carry, in first-seen order.')]
    extra: Annotated[list[str], Meta(description="The extra columns from config/rollup-extra-columns.yaml.")]
    rows: Annotated[list[dict[str, Any]], Meta(description="One per paper: key, title, doi, year, journal, hashtags, parts {header: text} (the whole summary, in its parts), extra {name: snippets}, model, at.")]
    hashtags: Annotated[list[list[Any]], Meta(description="[hashtag, papers] most used first.")]


@route(
    "GET /api/summaries/rollup", summary="One section's summaries as a table",
    tag=TAG,
    description=(
        "Every summary of a section: their subsection headers as columns, the hashtags and a histogram of them, and the extra "
        "keyword / regex columns config/rollup-extra-columns.yaml declares."
    ),
    mcp="summaries_rollup", read_only=True,
)
def rollup(request: Request, body: RollupQuery) -> RollupReply:
    found = get_summaries(request).rollup(body.section)
    # The whole summary is its parts already: sent once, not twice.
    for row in found["rows"]:
        row.pop("summary", None)
    return RollupReply(**found)


@route(
    "GET /api/summaries/rollup.xlsx", summary="The rollup as a workbook",
    tag=TAG, reply_type=xlsx.XLSX,
    description="The rollup's Summaries sheet (a column per subsection and extra column) and its Hashtag counts.",
    mcp_http="A file to download.",
)
def rollup_xlsx(request: Request, body: RollupQuery) -> Response:
    found = get_summaries(request).rollup(body.section)
    header = ["DOI", "Title", "Year", "Journal", "Hashtags"] + found["columns"] + found["extra"] + ["Full summary"]
    rows = []
    for row in found["rows"]:
        doi = row["doi"]
        rows.append([xlsx.Link("https://doi.org/" + doi, doi) if doi else row["key"], row["title"], row["year"], row["journal"], row["hashtags"]]
                    + [row["parts"].get(c, "") for c in found["columns"]] + [row["extra"].get(c, "") for c in found["extra"]] + [row["summary"]])
    data = xlsx.workbook([("Summaries", header, rows), ("Hashtag counts", ["Hashtag", "Papers"], found["hashtags"])])
    name = xlsx.filename(f"summaries-{body.section}")
    return Response(data, media_type=xlsx.XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


# -- the Google Sheets mirror ----------------------------------------------------------------

Slug = Annotated[str, PATH, Meta(min_length=1, max_length=200, description="The list's slug.", extra={"error": "no such list"})]


class SheetPath(RequestType):
    slug: Slug


class SheetReply(Reply):
    api_name: ClassVar[str] = "SheetMirror"
    sheet: Annotated[dict[str, Any], Meta(description=(
        "available (google_sheets is on and has credentials), mode (off, one-way, two-way), spreadsheet_id, url, last_push, "
        "last_pull, error, refused (the last read-back was refused), note, pending, poll_seconds, default_mode."
    ))]


def the_list(request: Request, slug: str) -> str:
    try:
        return boards.find_board(request.app.state.boards.store, slug)["slug"]
    except boards.BoardError as error:
        raise Refused(error.status, str(error)) from None


@route(
    "GET /api/lists/{slug}/sheet", summary="A list's Google Sheet mirror",
    tag=SHEETS_TAG, errors=(404, 410),
    description="Whether the list is mirrored to a Google Sheet, how, and how the last push and read-back went.",
    mcp="get_list_sheet", read_only=True,
)
def get_sheet(request: Request, body: SheetPath) -> SheetReply:
    return SheetReply(sheet=request.app.state.sheets.status(the_list(request, body.slug)))


class SheetBody(RequestType):
    slug: Slug
    mode: Annotated[Literal["off", "one-way", "two-way"] | None, Meta(description=(
        "off; one-way (the list is pushed to its sheet after each change); two-way (also read back every poll_seconds). The "
        "first switch on makes the spreadsheet."
    ))] = None
    sync_now: Annotated[bool, Meta(description="Push (and read back, two-way) now.")] = False
    overwrite: Annotated[bool, Meta(description="Write the list over the sheet now, dropping anything typed there since the last read.")] = False


@route(
    "POST /api/lists/{slug}/sheet", summary="Mirror a list to a Google Sheet",
    tag=SHEETS_TAG, errors=(404, 409, 410),
    description="Switch a list's Google Sheet mirror off, one-way or two-way; sync now; or overwrite the sheet with the list.",
    mcp="set_list_sheet",
)
def set_sheet(request: Request, body: SheetBody) -> SheetReply:
    sheets = request.app.state.sheets
    slug = the_list(request, body.slug)
    if body.mode not in (None, "off") and not sheets.available():
        raise Refused(409, "Google Sheets is not set up: google_sheets.enabled and its credentials in config.yaml")
    return SheetReply(sheet=sheets.configure(slug, body.mode, body.sync_now, body.overwrite))
