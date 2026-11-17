"""The review screener's rules, as named setups: the word lists, thresholds,
extraction fields and datasets, edited on the Screener rules page
(static/js/review_rules.js) or by an agent through the API and MCP.

A setup is a whole rules document with a name. "default" is
config/review.yaml with the edits kept in the database; others are copies,
or documents written from scratch (screener_rules_guide says how). One setup
is in use. Using another, or saving the one in use, moves the rules'
signature, so the content queue re-screens every candidate paper in turn --
or takes the result it kept for that setup, so swapping back is instant.
Saving a setup not in use re-screens nothing. Test runs a paper, or pasted
text, through any setup or unsaved rules.

All of it is the admins', from a browser session or an admin API key.
"""
from __future__ import annotations

import time
from typing import Annotated, Any, ClassVar, Literal

from msgspec import Meta
from starlette.requests import Request
from starlette.responses import Response

from app.apidocs import ADMIN, PATH, Reply, route
from app.apidocs import Request as RequestType
from app.content import sections
from app.content import store as st
from app.core.logs import KIND_ADMIN
from app.review import rules as R
from app.review import screen
from app.review.service import DEFAULT, ReviewService, SetupError
from app.routes.boards import actor_name
from app.routes.helpers import Refused
from app.routes.logs import audit

TAG = "Screener"
MAX_TEST_CHARS = 400_000

SetupId = Annotated[str, PATH, Meta(
    min_length=1, max_length=64, description='The setup\'s id, from list_screener_setups ("default" is config/review.yaml).',
    extra={"error": "no such setup"},
)]
Changes = Annotated[list[dict[str, Any]] | None, Meta(description=(
    "Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. "
    + R.CHANGE_PATHS
))]


def get_review(request: Request) -> ReviewService:
    return request.app.state.review


def refused(error: SetupError | R.RulesError) -> Refused:
    if isinstance(error, R.RulesError):
        return Refused(400, "invalid_review_rules", problems=error.problems)
    return Refused(error.status, error.message, **error.extra)


def rules_moved(request: Request, before: str, what: str) -> None:
    """The rules in use changed: the queue looks again, and the log says so."""
    review = get_review(request)
    if review.signature != before:
        request.app.state.content.dirty = True
        audit(request, KIND_ADMIN, what, {"setup": review.active, "signature": review.signature})


class Empty(RequestType):
    pass


class SetupPath(RequestType):
    setup: SetupId


# -- the setups ----------------------------------------------------------------------

class SetupsReply(Reply):
    api_name: ClassVar[str] = "ScreenerSetups"
    setups: Annotated[list[dict[str, Any]], Meta(description=(
        "Each setup, the default first: id, name, description, active (in use), builtin (the default), edited, signature, "
        "changed_count (places differing from config/review.yaml), based_on, updated_at, updated_by, problem (why it does not load)."
    ))]
    in_use: Annotated[str, Meta(description="The id of the setup in use.")]


@route(
    "GET /api/review/setups", summary="The screener's rule setups",
    tag=TAG, role=ADMIN,
    description="Every named set of screener rules, and which one is in use.",
    mcp="list_screener_setups", read_only=True,
)
def list_setups(request: Request, body: Empty) -> SetupsReply:
    review = get_review(request)
    return SetupsReply(setups=review.setups(), in_use=review.active)


class SetupReply(Reply):
    """One setup with its whole rules, the defaults beside them, and how far the
    queue has got with the setup in use."""

    api_name: ClassVar[str] = "ScreenerSetup"
    setup: Annotated[dict[str, Any], Meta(description="The setup's id, name, description and state, as in list_screener_setups.")]
    rules: Annotated[dict[str, Any], Meta(description="The setup's rules (config/review.yaml's shape).")]
    defaults: Annotated[dict[str, Any], Meta(description="config/review.yaml as shipped.")]
    changed: Annotated[list[str], Meta(description="Paths where the setup differs from the defaults, in the change-path syntax.")]
    signature: Annotated[str, Meta(description="The setup's signature: send it back as base_signature when saving.")]
    in_use: Annotated[str, Meta(description="The id of the setup in use.")]
    in_use_signature: str
    edited: bool
    updated_at: float | None
    updated_by: str
    problem: str
    post_kinds: list[str]
    groups: list[str]
    params: list[str]
    vocab_names: list[str]
    progress: Annotated[dict[str, Any], Meta(description=(
        "Of the setup in use: candidates (papers on a list or with a picked figure), and of their review tasks: done, "
        "current (screened under the rules in use), waiting, failed, included, borderline."
    ))]


def progress(request: Request) -> dict[str, Any]:
    review = get_review(request)
    content = request.app.state.content
    wanted = review.candidates()
    out = {"candidates": len(wanted), "done": 0, "current": 0, "waiting": 0, "failed": 0, "included": 0, "borderline": 0}
    sig = "rules:" + review.signature + "#"
    rows = content.files.rows()
    for key, stages in content.files.summaries(list(wanted)).items():
        state, summary, _ = stages.get(st.REVIEW, ("", {}, ""))
        if state == st.DONE:
            out["done"] += 1
            if rows.get((key, st.REVIEW), ("", ""))[1].startswith(sig):
                out["current"] += 1
            out["included"] += 1 if summary.get("include") else 0
            out["borderline"] += 1 if summary.get("borderline") else 0
        elif state == st.FAILED:
            out["failed"] += 1
        elif state in (st.PENDING, st.RUNNING):
            out["waiting"] += 1
    return out


def setup_reply(request: Request, setup: str) -> SetupReply:
    try:
        view = get_review(request).view(setup)
    except SetupError as error:
        raise refused(error) from None
    return SetupReply(**view, progress=progress(request))


@route(
    "GET /api/review/setups/{setup}", summary="One rule setup",
    tag=TAG, role=ADMIN, errors=(404,),
    description=(
        "A setup's whole rules -- every word list, threshold, extraction field and dataset -- with config/review.yaml's "
        "defaults beside them and the paths where they differ."
    ),
    mcp="get_screener_setup", read_only=True,
)
def get_setup(request: Request, body: SetupPath) -> SetupReply:
    return setup_reply(request, body.setup)


class CreateBody(RequestType):
    name: Annotated[str, Meta(min_length=1, max_length=80, description="Its name, unique.", extra={"error": "give the setup a name"})]
    description: Annotated[str, Meta(max_length=2000, description="What it is for.")] = ""
    source: Annotated[str, Meta(description='The setup to copy (default "default"). Ignored when rules are sent.')] = DEFAULT
    rules: Annotated[dict[str, Any] | None, Meta(description="A whole rules document to start from instead of a copy.")] = None
    changes: Changes = None
    activate: Annotated[bool, Meta(description="Use it at once (re-screens the candidate papers).")] = False


@route(
    "POST /api/review/setups", summary="Make a rule setup",
    tag=TAG, role=ADMIN, status=201, errors=(400, 404, 409),
    description=(
        "A new named setup: a copy of another (source), or a whole rules document (rules), with changes made to it. "
        "Rules that do not load are a 400 listing each problem with where it is; nothing is made. It is not used until "
        "activated."
    ),
    mcp="create_screener_setup",
)
def create_setup(request: Request, body: CreateBody) -> SetupReply:
    review = get_review(request)
    before = review.signature
    by = actor_name(request)
    try:
        base = body.rules if body.rules is not None else review.data_of(body.source)
        data = R.apply_changes(base, body.changes) if body.changes else base
        source = "" if body.rules is not None else body.source
        setup = review.create(body.name, by, body.description, source, data if body.rules is not None or body.changes else None)
        if body.activate:
            review.activate(setup)
    except (SetupError, R.RulesError) as error:
        raise refused(error) from None
    audit(request, KIND_ADMIN, "screener setup made", {"setup": setup, "source": source})
    rules_moved(request, before, "screener setup in use")
    return setup_reply(request, setup)


class SaveBody(RequestType):
    setup: SetupId
    rules: Annotated[dict[str, Any] | None, Meta(description="The whole rules document.")] = None
    changes: Changes = None
    name: Annotated[Annotated[str, Meta(max_length=80)] | None, Meta(description="A new name (not for the default).")] = None
    description: Annotated[Annotated[str, Meta(max_length=2000)] | None, Meta(description="A new description (not for the default).")] = None
    base_signature: Annotated[str, Meta(description=(
        "The signature the setup had when read: if it has changed since, nothing is saved and the answer is a 409 with the "
        "current signature."
    ))] = ""


@route(
    "POST /api/review/setups/{setup}", summary="Save a rule setup",
    tag=TAG, role=ADMIN, errors=(400, 404, 409),
    description=(
        "Changes a setup's rules (whole, or by changes), name or description. A pattern that does not compile, or a "
        "missing or wrong-typed value, is a 400 listing each problem with where it is; nothing is saved. Saving the setup "
        "in use re-screens the candidate papers one at a time; saving another re-screens nothing."
    ),
    mcp="save_screener_setup",
)
def save_setup(request: Request, body: SaveBody) -> SetupReply:
    review = get_review(request)
    before = review.signature
    try:
        review.save_setup(body.setup, actor_name(request), rules=body.rules, changes=body.changes, name=body.name,
                          description=body.description, base_signature=body.base_signature)
    except (SetupError, R.RulesError) as error:
        raise refused(error) from None
    audit(request, KIND_ADMIN, "screener setup saved", {"setup": body.setup, "signature": R.signature_of(review.data_of(body.setup))})
    rules_moved(request, before, "screener rules in use changed")
    return setup_reply(request, body.setup)


@route(
    "POST /api/review/setups/{setup}/activate", summary="Use a rule setup",
    tag=TAG, role=ADMIN, errors=(400, 404),
    description=(
        "Screens with this setup from now on. Each candidate paper takes the result it already has for this setup's rules "
        "when its text has not changed, and is re-screened in the background otherwise."
    ),
    mcp="use_screener_setup",
)
def activate_setup(request: Request, body: SetupPath) -> SetupReply:
    review = get_review(request)
    before = review.signature
    try:
        review.activate(body.setup)
    except (SetupError, R.RulesError) as error:
        raise refused(error) from None
    audit(request, KIND_ADMIN, "screener setup in use", {"setup": body.setup})
    rules_moved(request, before, "screener rules in use changed")
    return setup_reply(request, body.setup)


@route(
    "POST /api/review/setups/{setup}/delete", summary="Delete a rule setup",
    tag=TAG, role=ADMIN, errors=(404, 409),
    description="Deletes a setup for good. The default, and the setup in use, cannot be deleted.",
    mcp="delete_screener_setup", destructive=True,
)
def delete_setup(request: Request, body: SetupPath) -> SetupsReply:
    review = get_review(request)
    try:
        review.delete(body.setup)
    except SetupError as error:
        raise refused(error) from None
    audit(request, KIND_ADMIN, "screener setup deleted", {"setup": body.setup})
    return SetupsReply(setups=review.setups(), in_use=review.active)


@route(
    "POST /api/review/setups/{setup}/reset", summary="Reset the default rule setup",
    tag=TAG, role=ADMIN, errors=(404, 409),
    description="Drops the default setup's edits: config/review.yaml as it is. Only the default can be reset.",
    mcp="reset_screener_setup", destructive=True,
)
def reset_setup(request: Request, body: SetupPath) -> SetupReply:
    review = get_review(request)
    before = review.signature
    try:
        review.reset(body.setup)
    except SetupError as error:
        raise refused(error) from None
    audit(request, KIND_ADMIN, "screener default setup reset", {})
    rules_moved(request, before, "screener rules in use changed")
    return setup_reply(request, body.setup)


@route(
    "GET /api/review/setups/{setup}/export", summary="A rule setup as YAML",
    tag=TAG, role=ADMIN, reply_type="application/yaml", errors=(404,),
    description="A setup's rules in config/review.yaml's shape: to keep, or to paste in as the new defaults.",
    mcp_http="A file to download; get_screener_setup gives the same rules as JSON.",
)
def export_setup(request: Request, body: SetupPath) -> Response:
    review = get_review(request)
    try:
        data = review.data_of(body.setup)
    except SetupError as error:
        raise refused(error) from None
    name = next((s["name"] for s in review.setups() if s["id"] == body.setup), body.setup)
    text = f"# The review screener's rules: {name}, exported " + time.strftime("%Y-%m-%d %H:%M") + ".\n" + R.dump_yaml(data)
    filename = "review.yaml" if body.setup == DEFAULT else f"review-{body.setup}.yaml"
    return Response(text, media_type="application/yaml", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# -- checking and trying rules ------------------------------------------------------------

class GuideReply(Reply):
    api_name: ClassVar[str] = "ScreenerGuide"
    about: Annotated[str, Meta(description="How the rules work: patterns, macros, templates.")]
    change_paths: Annotated[str, Meta(description="The path syntax changes use.")]
    schema: Annotated[dict[str, Any], Meta(description="The rules document's JSON schema.")]
    post_kinds: list[str]
    groups: list[str]
    params: list[str]
    vocab_names: list[str]


GUIDE = (
    "A setup is one rules document (config/review.yaml's shape; get_screener_setup on \"default\" shows a full one). "
    "Patterns are Python regular expressions, matched case-insensitively. In extraction patterns <<NUM>> stands for a "
    "number, <<WORDS>> for the word-numbers (extraction.word_numbers) and <<NAME>> for any macro in extraction.macros. "
    "A post template uses ${v} (the group named v), ${0} (the whole match), ${1} (group 1), ${n} (a counted number); "
    "seconds_or_ms needs a (?P<v>...) group. Thresholds are {value, why}. Datasets' aliases are matched case-sensitively "
    "unless consensus.aliases_ignore_case. Build a setup by copying one (create_screener_setup with source) and sending "
    "changes, check rules with check_screener_rules, try them on a paper with test_screener, then use_screener_setup."
)


@route(
    "GET /api/review/guide", summary="How screener rules are written",
    tag=TAG, role=ADMIN,
    description="What an agent needs to write a setup: how patterns, macros and templates work, the change-path syntax, and the document's schema.",
    mcp="screener_rules_guide", read_only=True,
)
def guide(request: Request, body: Empty) -> GuideReply:
    return GuideReply(about=GUIDE, change_paths=R.CHANGE_PATHS, schema=R.schema(), post_kinds=list(R.POST_KINDS),
                      groups=list(R.GROUPS), params=list(R.PARAMS), vocab_names=list(R.VOCAB_NAMES))


class CheckBody(RequestType):
    rules: Annotated[dict[str, Any] | None, Meta(description="A whole rules document to check.")] = None
    setup: Annotated[str, Meta(description="A setup to check, or to make changes to first.")] = ""
    changes: Changes = None


class CheckReply(Reply):
    api_name: ClassVar[str] = "ReviewCheck"
    problems: Annotated[list[dict[str, str]], Meta(description="Each problem: path (where it is) and message. Empty: the rules load.")]
    signature: Annotated[str, Meta(description="The rules' signature; the same as the one in use means using them changes nothing.")]
    rescreen: Annotated[int, Meta(description="Papers using these rules would re-screen (or take a kept result for).")]


@route(
    "POST /api/review/check", summary="Check screener rules without saving",
    tag=TAG, role=ADMIN, errors=(404,),
    description=(
        "Whether rules load (every pattern compiles, every value has the right type): a whole document, a setup, or a "
        "setup with changes made. And how many papers using them would re-screen."
    ),
    mcp="check_screener_rules", read_only=True,
)
def check_rules(request: Request, body: CheckBody) -> CheckReply:
    review = get_review(request)
    try:
        base = body.rules if body.rules is not None else review.data_of(body.setup or review.active)
        compiled = R.load(R.apply_changes(base, body.changes) if body.changes else base)
    except SetupError as error:
        raise refused(error) from None
    except R.RulesError as error:
        return CheckReply(problems=error.problems, signature="", rescreen=0)
    return CheckReply(problems=[], signature=compiled.signature, rescreen=review.stale_count(compiled))


class ProgressReply(Reply):
    api_name: ClassVar[str] = "ReviewProgress"
    progress: dict[str, Any]
    signature: str
    in_use: str


@route(
    "GET /api/review/progress", summary="How far the screener has got",
    tag=TAG, role=ADMIN,
    description="Candidates, and how many are screened under the setup in use, waiting, or failed.",
    mcp="screener_progress", read_only=True,
)
def get_progress(request: Request, body: Empty) -> ProgressReply:
    review = get_review(request)
    return ProgressReply(progress=progress(request), signature=review.signature, in_use=review.active)


class TestBody(RequestType):
    rules: Annotated[dict[str, Any] | None, Meta(description="Rules to test with, not saved.")] = None
    setup: Annotated[str, Meta(description="A setup to test with (when no rules are sent); none means the one in use.")] = ""
    changes: Changes = None
    key: Annotated[str, Meta(description="A paper to screen, by its key.")] = ""
    title: str = ""
    abstract: str = ""
    text: Annotated[str, Meta(description="Pasted text to screen as the paper's body (and methods).")] = ""
    mode: Literal["full", "abstract"] = "full"


class TestReply(Reply):
    api_name: ClassVar[str] = "ReviewTest"
    result: Annotated[dict[str, Any], Meta(description="The review as the screens would show it: verdict with its why, fields with quotes.")]
    saved: Annotated[dict[str, Any] | None, Meta(description="The same paper under the setup in use, when testing other rules on a paper.")]
    paper: dict[str, Any]
    elapsed_ms: int


def paper_texts(request: Request, key: str) -> tuple[dict[str, Any], str, str, str, str]:
    """(record, title, abstract, methods, body) of one paper, from its methods
    stage's split (sections.json)."""
    content = request.app.state.content
    paper = content.catalogue.get(key)
    if paper is None:
        raise Refused(404, "paper_not_found")
    parts = (content.files.read(key, "sections.json") or {}).get("sections") or []
    methods = sections.methods_text(parts)
    if not methods:
        try:
            methods = (content.files.dir(key) / "methods_legacy.txt").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            methods = ""
    kept = []
    for part in parts:
        if part.get("key") == "references":
            break
        kept.append(part)
    record = paper.record
    abstract = record.get("abstract") or content._oa_abstract(key) or next((p["text"] for p in parts if p.get("key") == "abstract"), "")
    return record, record.get("title") or "", abstract, methods, sections.render(kept)


@route(
    "POST /api/review/test", summary="Try the screener on one paper",
    tag=TAG, role=ADMIN, errors=(400, 404),
    description=(
        "Screens one library paper (key) or pasted text with the rules sent (unsaved), a setup, or the setup in use -- with "
        "changes made first, if sent -- and returns the verdict, why, and every extracted field with its quote. Nothing is stored."
    ),
    mcp="test_screener", read_only=True,
)
def test_rules(request: Request, body: TestBody) -> TestReply:
    review = get_review(request)
    try:
        if body.rules is None and not body.changes and not body.setup:
            rules = review.rules
        else:
            base = body.rules if body.rules is not None else review.data_of(body.setup or review.active)
            rules = R.load(R.apply_changes(base, body.changes) if body.changes else base)
    except (SetupError, R.RulesError) as error:
        raise refused(error) from None
    paper: dict[str, Any] = {}
    doi = ""
    if body.key:
        record, title, abstract, methods, text = paper_texts(request, body.key)
        doi = (record.get("doi") or "").lower()
        paper = {"key": body.key, "title": title, "year": record.get("year"), "doi": doi,
                 "methods_chars": len(methods), "body_chars": len(text), "abstract_chars": len(abstract)}
    else:
        title, abstract, text = body.title, body.abstract, body.text[:MAX_TEST_CHARS]
        methods = ""
        if not (text.strip() or abstract.strip() or title.strip()):
            raise Refused(400, "review_test_empty")
        paper = {"title": title, "body_chars": len(text), "abstract_chars": len(abstract)}
    started = time.perf_counter()
    consensus = review.consensus()
    override = review.override_for(body.key, doi) if body.key else {}

    def run(with_rules: R.Rules) -> dict[str, Any]:
        if body.mode == "abstract":
            stored = screen.screen_abstract(with_rules, title, abstract)
        else:
            stored = screen.screen_paper(with_rules, title, abstract, methods, text)
        return review.present(stored, override, consensus, with_rules)

    result = run(rules)
    saved = run(review.rules) if body.key and rules.signature != review.signature else None
    return TestReply(result=result, saved=saved, paper=paper, elapsed_ms=int((time.perf_counter() - started) * 1000))


# -- hand-checked values ------------------------------------------------------------------

class OverrideBody(RequestType):
    key: Annotated[str, Meta(min_length=1, description="The paper's key (or its DOI).")]
    fields: Annotated[dict[str, str], Meta(description="Field -> value. Empty values are dropped; none at all deletes the override.")]


class OverridesReply(Reply):
    api_name: ClassVar[str] = "ReviewOverrides"
    overrides: Annotated[dict[str, dict[str, str]], Meta(description="Paper key (or DOI) -> {field: value}.")]


@route(
    "GET /api/review/overrides", summary="Hand-checked review values",
    tag=TAG, role=ADMIN,
    description="Values typed in by hand, by paper: each wins over what the screener extracted, whatever the setup, and flags the paper.",
    mcp="list_review_overrides", read_only=True,
)
def list_overrides(request: Request, body: Empty) -> OverridesReply:
    return OverridesReply(overrides=get_review(request).overrides())


@route(
    "POST /api/review/overrides", summary="Set a paper's hand-checked values",
    tag=TAG, role=ADMIN,
    description="Replaces one paper's overrides; sending no fields removes them. Nothing is re-screened: overrides apply when read.",
    mcp="set_review_override",
)
def set_override(request: Request, body: OverrideBody) -> OverridesReply:
    review = get_review(request)
    review.set_override(body.key.strip(), body.fields, actor_name(request))
    audit(request, KIND_ADMIN, "review override changed", {"key": body.key, "fields": sorted(body.fields)})
    return OverridesReply(overrides=review.overrides())
