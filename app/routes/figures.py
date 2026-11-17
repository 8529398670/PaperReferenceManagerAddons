"""The Figures screen's routes: the papers and their figure crops (all of them,
or only the method figures), the picks and skipped papers of each view, the
images, and the picks as JSON or CSV.

The crops come from the optional worker (`python -m app worker`) or the old
app's, linked in by `manage import-legacy --figures`; see app/content/figures.py.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Annotated, Any, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from app.apidocs import QUERY, Reply, route
from app.apidocs import Request as RequestType
from app.content.figures import CHIPS, SORTS, VIEWS, Figures, split_id
from app.routes.helpers import PAGE_LIMIT_MESSAGE, PAGE_OFFSET_MESSAGE, Paged, Refused

TAG = "Figures"
PAGE_MAX_PAPERS = 200
MAX_IDS = 1000

View = Annotated[Literal["all", "method"], QUERY, Meta(
    description='"all" (default): every figure. "method": the figures whose caption reads as a model design.',
    extra={"error": "view must be all or method"},
)]
ViewBody = Annotated[Literal["all", "method"], Meta(description='"all" or "method": each view has its own picks.', extra={"error": "view must be all or method"})]


def get_figures(request: Request) -> Figures:
    return request.app.state.figures


class FiguresQuery(RequestType):
    view: View = "all"
    sort: Annotated[Literal["added", "published", "match", "count", "title"], QUERY, Meta(
        description="added (default: when it reached Zotero), published, match (best caption match), count (most figures), title.",
        extra={"error": "sort must be one of: " + ", ".join(SORTS)},
    )] = "added"
    dir: Annotated[Literal["asc", "desc"], QUERY, Meta(description="Default desc.", extra={"error": "dir must be asc or desc"})] = "desc"
    chip: Annotated[Literal["all", "lead", "selected", "skipped", "other"], QUERY, Meta(
        description=(
            "all (default: every paper not skipped), lead (a structural term opens a caption), selected (a figure is picked), "
            "skipped, other (a figure is picked in the other view)."
        ),
        extra={"error": "chip must be one of: " + ", ".join(CHIPS)},
    )] = "all"
    mod: Annotated[str, QUERY, Meta(description="Only papers tagged with this modality.")] = ""
    term: Annotated[str, QUERY, Meta(description="Only papers with a caption matching this keyword (method view).")] = ""
    q: Annotated[str, QUERY, Meta(description="Only papers whose title, DOI or a caption contains this.")] = ""
    limit: Annotated[int, QUERY, Meta(ge=1, le=PAGE_MAX_PAPERS, description="Papers to return. Default 40.", extra={"error": PAGE_LIMIT_MESSAGE})] = 40
    offset: Annotated[int, QUERY, Meta(ge=0, description="Papers to skip: the next value of the previous page.", extra={"error": PAGE_OFFSET_MESSAGE})] = 0


class FiguresReply(Paged):
    papers: Annotated[list[dict[str, Any]], Meta(description=(
        "key, title, year, doi, added, date, skipped, mods, terms, lead, best, and figures: n, id (<key>#figure-N), page, caption, "
        "w, h, dup, picked, picked_other, match (score, terms, strong, lead, spans)."
    ))]
    figures: Annotated[int, Meta(description="How many figures the matching papers show.")]
    counts: Annotated[dict[str, int], Meta(description="Papers under each chip: all, lead, selected, skipped, other.")]
    mods: Annotated[list[dict[str, Any]], Meta(description="The modalities of the papers shown, with counts.")]
    terms: Annotated[list[dict[str, Any]], Meta(description="The caption keywords matched, with counts (method view).")]
    picks: Annotated[int, Meta(description="Figures picked in this view.")]
    skips: Annotated[int, Meta(description="Papers skipped in this view.")]
    workers: Annotated[bool, Meta(description="Whether a figures worker is running now.")]


@route(
    "GET /api/figures", summary="Papers and their figures",
    tag=TAG,
    description=(
        "The papers whose figures have been cropped, with their figures, a page of papers at a time: every figure, or the "
        "method figures (captions matching config/method-images.txt). Each figure says whether it is picked in this view and "
        "in the other; chips, modality and keyword filters narrow the papers."
    ),
    mcp="list_figures", read_only=True,
)
def list_figures(request: Request, body: FiguresQuery) -> FiguresReply:
    found = get_figures(request).listing(
        body.view, body.sort, body.dir == "desc", body.chip, body.mod, body.term, body.q[:200], body.offset, body.limit,
    )
    return FiguresReply(**found)


class StateQuery(RequestType):
    view: View = "all"


class StateReply(Reply):
    selected: Annotated[list[str], Meta(description="The picked figures' ids, in pick order.")]
    skipped: Annotated[list[str], Meta(description="The skipped papers' keys.")]


@route(
    "GET /api/figures/state", summary="A view's picks and skipped papers",
    tag=TAG, description="Every picked figure (in pick order) and every skipped paper of one view.",
    mcp="figure_picks", read_only=True,
)
def figures_state(request: Request, body: StateQuery) -> StateReply:
    return StateReply(**get_figures(request).state(body.view))


class PickBody(RequestType):
    view: ViewBody
    ids: Annotated[list[str], Meta(description='Figure ids, "<paper key>#figure-N". At most 1000.', extra={"error": 'send {"ids": ["<key>#figure-N"]}'})]
    pick: Annotated[bool, Meta(description="true picks them (default), false unpicks them.")] = True


@route(
    "POST /api/figures/pick", summary="Pick or unpick figures",
    tag=TAG, description="Pick figures in one view (a new pick goes last), or take picks back.",
    mcp="pick_figures",
)
def pick_figures(request: Request, body: PickBody) -> StateReply:
    ids = [i for i in (str(x).strip() for x in body.ids) if split_id(i)][:MAX_IDS]
    if not ids:
        raise Refused(400, 'send {"ids": ["<key>#figure-N"]}')
    return StateReply(**get_figures(request).pick(body.view, ids, body.pick))


class SkipBody(RequestType):
    view: ViewBody
    keys: Annotated[list[str], Meta(description="Paper keys. At most 1000.", extra={"error": 'send {"keys": [...]}'})]
    skip: Annotated[bool, Meta(description="true skips them (default), false brings them back.")] = True


@route(
    "POST /api/figures/skip", summary="Skip or unskip papers",
    tag=TAG, description="Hide papers you are done with from one view, or bring them back.",
    mcp="skip_figure_papers",
)
def skip_papers(request: Request, body: SkipBody) -> StateReply:
    keys = [k for k in (str(x).strip() for x in body.keys) if k][:MAX_IDS]
    if not keys:
        raise Refused(400, 'send {"keys": [...]}')
    return StateReply(**get_figures(request).skip(body.view, keys, body.skip))


class ReplaceBody(RequestType):
    view: ViewBody
    selected: Annotated[list[str], Meta(description="The picks to keep, in order.")] = []
    skipped: Annotated[list[str], Meta(description="The skipped papers to keep.")] = []


@route(
    "POST /api/figures/replace", summary="Replace a view's picks",
    tag=TAG,
    description="Set a view's picks and skipped papers outright: Clear sends both empty, and its undo sends the old ones back.",
    mcp="set_figure_picks", destructive=True,
)
def replace_state(request: Request, body: ReplaceBody) -> StateReply:
    selected = [i for i in body.selected if split_id(str(i))]
    return StateReply(**get_figures(request).replace(body.view, selected, [str(k) for k in body.skipped if k]))


class ExportQuery(RequestType):
    view: View = "all"
    format: Annotated[Literal["json", "csv"], QUERY, Meta(description="json (default) or csv.", extra={"error": "format must be json or csv"})] = "json"


@route(
    "GET /api/figures/export", summary="A view's picks as a file",
    tag=TAG, reply_type="application/octet-stream",
    description="Every picked figure of a view, in pick order, with its paper, DOI and caption: a JSON or CSV file to download.",
    mcp_http="A file to download; figure_picks gives the ids as data.",
)
def export_picks(request: Request, body: ExportQuery) -> Response:
    rows = get_figures(request).export_rows(body.view)
    name = f"figures-{body.view}"
    if body.format == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["order", "id", "key", "figure", "title", "year", "doi", "caption"])
        writer.writeheader()
        writer.writerows(rows)
        return Response(out.getvalue().encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    # A file to save, not an API answer (figure_picks is that), hence not
    # served as application/json.
    return Response(json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8"), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


class ImageQuery(RequestType):
    key: Annotated[str, QUERY, Meta(description="The paper's key.")] = ""
    n: Annotated[int, QUERY, Meta(ge=0, description="The figure's number; 0 is the paper's montage.", extra={"error": "n must be a figure number"})] = 0
    size: Annotated[Literal["thumb", "full"], QUERY, Meta(description="thumb (default, 640 px wide) or full (the 400 DPI crop).", extra={"error": "size must be thumb or full"})] = "thumb"


@route(
    "GET /api/figures/image", summary="One figure's image",
    tag=TAG, errors=(404,), reply_type="image/webp",
    description="A figure crop: a small copy for the grid (WebP), or the full crop (PNG). n=0 is the paper's montage.",
    mcp_http="An image, for a browser to show.",
)
def figure_image(request: Request, body: ImageQuery) -> Response:
    figures = get_figures(request)
    paper = request.app.state.library.catalogue.find(body.key)
    if paper is None:
        raise Refused(404, "no such paper in the library")
    if body.n == 0:
        path = figures.files.dir(paper.key) / "figures" / "montage.png"
        if not path.is_file():
            raise Refused(404, "this paper has no montage")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    if body.size == "full":
        path = figures.paths(paper.key, body.n)
        if not path.is_file():
            raise Refused(404, "no such figure")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    try:
        thumb = figures.thumb(paper.key, body.n)
    except OSError as error:
        raise Refused(404, f"the figure could not be read: {error}") from None
    if thumb is None:
        raise Refused(404, "no such figure")
    return FileResponse(thumb, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


__all__ = ["VIEWS"]
