"""MCP tools for the library and the lists. Each one calls the helper its HTTP
route calls (search_page, run_ops, ...), so an agent and the page are held to
the same rules. Creating, renaming or deleting whole lists is not here: an
agent edits lists, it does not decide which exist.
"""
from __future__ import annotations

from typing import Any

from app.boards import store as boards
from app.mcp.registry import Call, Refusal, Registry, Tool
from app.routes.boards import run_ops, schema_body
from app.routes.library import search_page

SLUG = {"type": "string", "description": "The list's slug, from list_lists (the main list is \"main\")."}


def search_library(call: Call) -> dict[str, Any]:
    args = call.bind({"query": str}, optional={"mode": str, "limit": int, "offset": int})
    mode = args.get("mode", "text")
    if mode not in ("text", "title"):
        raise Refusal("mode must be text or title")
    limit, offset = args.get("limit", 25), args.get("offset", 0)
    if not 1 <= limit <= 200 or offset < 0:
        raise Refusal("limit must be 1-200 and offset 0 or more")
    catalogue = call.request.app.state.library.catalogue
    return search_page(catalogue, args["query"], mode, "relevance", True, limit, offset)


def list_lists(call: Call) -> dict[str, Any]:
    call.bind({})
    return {"lists": boards.list_boards(call.store)}


def get_list(call: Call) -> dict[str, Any]:
    args = call.bind({"slug": str})
    service = call.request.app.state.boards
    record = boards.get_board(call.store, args["slug"])
    if record is None:
        raise Refusal(f"no list {args['slug']!r}")
    return {"list": service.view(record)}


def list_schema(call: Call) -> dict[str, Any]:
    call.bind({})
    return schema_body()


def list_ops(call: Call) -> dict[str, Any]:
    args = call.bind({"slug": str, "ops": list}, optional={"if_rev": int, "dry_run": bool})
    service = call.request.app.state.boards
    name = call.actor.user.display_name + " (API key)"
    try:
        answer = run_ops(service, args["slug"], args["ops"], name, args.get("if_rev"), args.get("dry_run", False))
    except boards.BoardError as refusal:
        detail = "".join(f"; {k}: {v}" for k, v in refusal.extra.items())
        raise Refusal(str(refusal) + detail) from None
    # The whole document is in get_list; the answer here stays small.
    answer.pop("list", None)
    return answer


def register(registry: Registry) -> None:
    registry.register(Tool(
        name="search_library",
        title="Search the library",
        description=(
            "Search the papers in the Zotero library. mode \"text\" (default) is boolean full-text search over title, "
            "authors, abstract and the PDF's text: words are ANDed, OR between alternatives, -word or NOT word excludes, "
            "\"a phrase\" is literal. mode \"title\" finds a half-remembered title, typos and all, or a pasted DOI. "
            "Each paper's key is what list_ops' add takes."
        ),
        call=search_library,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["text", "title"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        read_only=True,
    ))
    registry.register(Tool(
        name="list_lists",
        title="List the lists",
        description="Every curated list: slug, name, rev (its version number), how many papers it holds, and whether it is view-only.",
        call=list_lists,
        read_only=True,
    ))
    registry.register(Tool(
        name="get_list",
        title="Read a list",
        description="One list in full: its document (rows in order, each with key, title, year, tags and cells; columns; the tag vocabulary with colours), its rev, and what the library knows of each row.",
        call=get_list,
        input_schema={"type": "object", "properties": {"slug": SLUG}, "required": ["slug"], "additionalProperties": False},
        read_only=True,
    ))
    registry.register(Tool(
        name="list_schema",
        title="List ops reference",
        description="Every op list_ops takes, with its parameters, plus how rows and positions are named. Read it before a first list_ops call.",
        call=list_schema,
        read_only=True,
    ))
    registry.register(Tool(
        name="list_ops",
        title="Change a list",
        description=(
            "Run a batch of ops against a list, atomically: every op succeeds and the list is saved once, or nothing is "
            "saved and the answer names the op that failed. Rows are named by key, DOI or \"#N\" (position). "
            "Examples: {\"op\":\"add\",\"paper\":\"<key or DOI or title>\",\"at\":\"top\"}, {\"op\":\"move\",\"row\":\"#12\",\"to\":1}, "
            "{\"op\":\"tag\",\"rows\":[\"#1\",\"#2\"],\"add\":[\"premier\"]}, {\"op\":\"set_cell\",\"row\":\"#1\",\"col\":\"Notes\",\"value\":\"key paper\",\"mode\":\"append\"}. "
            "dry_run previews; if_rev refuses the batch when the list moved since you read it. Every change keeps the "
            "previous version, so a removal can be put back."
        ),
        call=list_ops,
        input_schema={
            "type": "object",
            "properties": {
                "slug": SLUG,
                "ops": {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 500},
                "if_rev": {"type": "integer"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["slug", "ops"],
            "additionalProperties": False,
        },
        destructive=True,
    ))
