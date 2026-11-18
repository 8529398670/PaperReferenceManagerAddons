"""Saved searches: a name, a boolean query in the search box's grammar, and
named groups of terms. They replace the old searches/*.py predicate files,
which were executable Python -- not something to load from a web page.

A search matches a paper (or a missing work) when its query matches, if it
has one, and every required group does. A group is one of:

  any       at least one of its terms is there
  all       every term is there
  none      none of its terms is there
  at_least  at least n of the groups it names match (the old at_least(n, ...))

A group named only inside an at_least is usually not required on its own:
that is its `required: false`. A term is a phrase, matched the way one word of
the search box is: folded (accents and punctuation flattened) and its last
word a prefix, in the title, authors, journal, tags, abstract or full text
(the missing pool has no full text: its title, abstract, journal and
authors). The old files matched with rapidfuzz partial_ratio at 80, which let
"bold" match "old"; a phrase is predictable.

Each search runs over the library and over the missing pool, from the same
indexes the search box uses, so it costs a few hundred milliseconds and
nothing is built. The crawl takes its keywords from one, and missing.xlsx
writes a sheet for each.
"""
from __future__ import annotations

import ast
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.core import db
from app.search import query as q

MODES = ("any", "all", "none", "at_least")
MAX_SEARCHES = 200
MAX_GROUPS = 40
MAX_TERMS = 400
MAX_TERM = 200
MAX_QUERY = 2000
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")


class SearchError(Exception):
    """A saved search that does not hold together: problems is a list of
    {where, message}."""

    def __init__(self, problems: list[dict[str, str]]) -> None:
        super().__init__("; ".join(f"{p['where']}: {p['message']}" for p in problems))
        self.problems = problems


def clean(data: dict[str, Any]) -> dict[str, Any]:
    """A search as sent, checked and tidied: {name, description, query,
    groups: [{name, mode, terms, n, of, required}]}. Raises SearchError."""
    problems: list[dict[str, str]] = []

    def bad(where: str, message: str) -> None:
        problems.append({"where": where, "message": message})

    name = str(data.get("name") or "").strip()
    if not name:
        bad("name", "give the search a name")
    if len(name) > 120:
        bad("name", "at most 120 characters")
    query = str(data.get("query") or "").strip()
    if len(query) > MAX_QUERY:
        bad("query", f"at most {MAX_QUERY} characters")
    groups_in = data.get("groups") or []
    if not isinstance(groups_in, list):
        bad("groups", "a list of groups")
        groups_in = []
    if len(groups_in) > MAX_GROUPS:
        bad("groups", f"at most {MAX_GROUPS} groups")
    groups: list[dict[str, Any]] = []
    names: set[str] = set()
    total_terms = 0
    for index, group in enumerate(groups_in):
        where = f"groups[{index}]"
        if not isinstance(group, dict):
            bad(where, "a group is {name, mode, terms}")
            continue
        gname = str(group.get("name") or "").strip()
        if not _NAME.match(gname):
            bad(where + ".name", "a name of letters, digits and _, starting with a letter (FMRI, INNER_SPEECH)")
        elif gname in names:
            bad(where + ".name", f"{gname} is used twice")
        names.add(gname)
        mode = str(group.get("mode") or "any")
        if mode not in MODES:
            bad(where + ".mode", "any, all, none or at_least")
        terms = [str(t).strip() for t in (group.get("terms") or []) if str(t).strip()]
        terms = list(dict.fromkeys(terms))
        for term in terms:
            if len(term) > MAX_TERM:
                bad(where + ".terms", f"a term is at most {MAX_TERM} characters")
            elif not q.fold(term):
                bad(where + ".terms", f"{term!r} has no letters or digits")
        total_terms += len(terms)
        out: dict[str, Any] = {"name": gname, "mode": mode, "required": bool(group.get("required", True))}
        if mode == "at_least":
            of = [str(o).strip() for o in (group.get("of") or []) if str(o).strip()]
            try:
                n = int(group.get("n") or 1)
            except (TypeError, ValueError):
                n = 0
            if not of:
                bad(where + ".of", "name the groups it counts")
            if not 1 <= n <= max(len(of), 1):
                bad(where + ".n", f"between 1 and {max(len(of), 1)}")
            out.update(n=n, of=of)
        else:
            if not terms:
                bad(where + ".terms", "add at least one term")
            out["terms"] = terms
        groups.append(out)
    if total_terms > MAX_TERMS:
        bad("groups", f"at most {MAX_TERMS} terms in all")
    # at_least names groups defined here, and never itself through a cycle.
    by_name = {g["name"]: g for g in groups}
    for index, group in enumerate(groups):
        for other in group.get("of", []):
            if other not in by_name:
                bad(f"groups[{index}].of", f"no group named {other}")
    for group in groups:
        if group["mode"] == "at_least" and _cycles(group["name"], by_name, set()):
            bad(f"groups[{groups.index(group)}].of", f"{group['name']} counts itself")
    if not query and not any(g["required"] for g in groups):
        bad("query", "give a query or a required group: as it is the search matches everything")
    if problems:
        raise SearchError(problems)
    return {"name": name, "description": str(data.get("description") or "").strip()[:2000], "query": query, "groups": groups}


def _cycles(name: str, by_name: dict[str, dict[str, Any]], seen: set[str]) -> bool:
    if name in seen:
        return True
    group = by_name.get(name)
    if group is None:
        return False
    return any(_cycles(other, by_name, seen | {name}) for other in group.get("of", []))


def evaluate(search: dict[str, Any], term_set: Callable[[str], set[str]], query_set: Callable[[str], set[str]],
             universe: set[str]) -> tuple[set[str], dict[str, int]]:
    """The ids a search matches, and how many each group matched on its own
    (over the whole universe). term_set(term) and query_set(query) answer
    from an index."""
    cache: dict[str, set[str]] = {}
    groups = {g["name"]: g for g in search.get("groups", [])}
    memo: dict[str, set[str]] = {}

    def terms(term: str) -> set[str]:
        if term not in cache:
            cache[term] = term_set(term)
        return cache[term]

    def group_set(name: str) -> set[str]:
        if name in memo:
            return memo[name]
        group = groups[name]
        mode = group["mode"]
        if mode == "any":
            found: set[str] = set()
            for term in group["terms"]:
                found |= terms(term)
        elif mode == "all":
            found = set(universe)
            for term in group["terms"]:
                found &= terms(term)
        elif mode == "none":
            found = set(universe)
            for term in group["terms"]:
                found -= terms(term)
        else:
            counts: dict[str, int] = {}
            for other in group["of"]:
                for item in group_set(other):
                    counts[item] = counts.get(item, 0) + 1
            found = {item for item, n in counts.items() if n >= group["n"]}
        memo[name] = found
        return found

    matched = set(universe) if not search.get("query") else query_set(search["query"]) & universe
    tally = {}
    for name, group in groups.items():
        found = group_set(name)
        tally[name] = len(found)
        if group["required"]:
            matched &= found
    return matched, tally


def keywords(search: dict[str, Any]) -> list[str]:
    """The search's positive vocabulary: its query's terms and every term of
    an any / all group, folded and deduplicated. The crawl scores with these."""
    out: list[str] = []
    for clause in q.parse(search.get("query") or ""):
        out.extend(clause.pos)
    for group in search.get("groups", []):
        if group["mode"] in ("any", "all"):
            out.extend(q.fold(t) for t in group["terms"])
    return [t for t in dict.fromkeys(out) if t]


class SavedSearches:
    """The saved searches, in db.BUCKET_SAVED_SEARCHES, and running them."""

    def __init__(self, store: db.Store, catalogue: Any, pool_fn: Callable[[], Any], skipped_fn: Callable[[], set[str]]) -> None:
        self.store = store
        self.catalogue = catalogue
        self.pool_fn = pool_fn
        self.skipped_fn = skipped_fn
        self._lock = threading.Lock()

    def all(self) -> list[dict[str, Any]]:
        found = [record for _, record in self.store.all(db.BUCKET_SAVED_SEARCHES)]
        return sorted(found, key=lambda r: (r.get("name") or "").lower())

    def get(self, search_id: str) -> dict[str, Any] | None:
        return self.store.get(db.BUCKET_SAVED_SEARCHES, search_id)

    def find(self, spec: str) -> dict[str, Any] | None:
        """By id, or by name (case-insensitive)."""
        found = self.get(spec)
        if found:
            return found
        spec = spec.strip().lower()
        return next((r for r in self.all() if (r.get("name") or "").lower() == spec), None)

    def save(self, data: dict[str, Any], by: str, search_id: str = "") -> dict[str, Any]:
        tidy = clean(data)
        with self._lock:
            others = [r for r in self.all() if r["id"] != search_id]
            if any(r["name"].lower() == tidy["name"].lower() for r in others):
                raise SearchError([{"where": "name", "message": f"a search named {tidy['name']} exists"}])
            old = self.get(search_id) if search_id else None
            if search_id and old is None:
                raise KeyError(search_id)
            if not search_id and len(others) >= MAX_SEARCHES:
                raise SearchError([{"where": "name", "message": f"at most {MAX_SEARCHES} saved searches"}])
            now = time.time()
            record = {
                **tidy, "id": search_id or secrets.token_hex(6),
                "created_at": (old or {}).get("created_at", now), "created_by": (old or {}).get("created_by", by),
                "updated_at": now, "updated_by": by,
            }
            self.store.put(db.BUCKET_SAVED_SEARCHES, record["id"], record)
        return record

    def delete(self, search_id: str) -> dict[str, Any] | None:
        with self._lock:
            old = self.get(search_id)
            if old is not None:
                self.store.delete(db.BUCKET_SAVED_SEARCHES, search_id)
        return old

    def restore(self, record: dict[str, Any]) -> None:
        """Put back a deleted search as it was (undo)."""
        self.store.put(db.BUCKET_SAVED_SEARCHES, record["id"], record)

    # -- running ----------------------------------------------------------------------

    def run_library(self, search: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
        """Library keys matched, newest first, and each group's count."""
        catalogue = self.catalogue
        papers = catalogue.all()
        universe = {p.key for p in papers}
        found, tally = evaluate(search, catalogue.term_keys, catalogue.query_keys, universe)
        order = sorted((p for p in papers if p.key in found), key=lambda p: p.record.get("date_added") or "", reverse=True)
        return [p.key for p in order], tally

    def run_missing(self, search: dict[str, Any], limit: int = 1000, include_skipped: bool = False,
                    cache: dict[str, set[int]] | None = None) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        """Missing works matched, nearest your library first, at most limit;
        how many matched in all; and each group's count. cache carries term
        hits from one search to the next (missing.xlsx runs every search)."""
        pool = self.pool_fn()
        universe: set[int] | frozenset[int] = pool.universe_ids()
        if not include_skipped:
            skipped = self.skipped_fn()
            if skipped:
                universe = universe - pool.ids_of(skipped)
        cache = {} if cache is None else cache

        def term_set(term: str) -> set[int]:
            if term not in cache:
                cache[term] = pool.term_ids(term)
            return cache[term]

        found, tally = evaluate(search, term_set, pool.query_ids, set(universe))
        wids = pool.top_of(found, limit)
        by_wid = {row["wid"]: row for row in pool.works_by_wid(wids)}
        return [by_wid[w] for w in wids if w in by_wid], len(found), tally


# -- the old searches/*.py ----------------------------------------------------------------

class _Untranslatable(Exception):
    pass


def translate_legacy(source: str, stem: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The old predicate file's searches as saved searches, read from its
    syntax tree (never run). -> (searches, what could not be translated).

    Each (name, predicate) the file's search() returns becomes one search.
    any_of / all_of / none_of become groups; combine_or of any_of calls
    merges into one any group; combine_and makes its parts required groups;
    at_least(n, ...) becomes an at_least group over its parts; a variable
    keeps its name as the group's. A lambda, `not`, or anything else is
    reported and that search left out."""
    tree = ast.parse(source)
    func = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "search"), None)
    if func is None:
        return [], [f"{stem}: no search() function"]
    env: dict[str, ast.AST] = {}
    result: ast.AST | None = None
    for node in func.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            env[node.targets[0].id] = node.value
        elif isinstance(node, ast.Return):
            result = node.value
    if not isinstance(result, (ast.List, ast.Tuple)):
        return [], [f"{stem}: search() does not return a list"]
    out: list[dict[str, Any]] = []
    problems: list[str] = []
    for item in result.elts:
        if not (isinstance(item, ast.Tuple) and len(item.elts) == 2 and isinstance(item.elts[0], ast.Constant)):
            problems.append(f"{stem}: an entry is not (name, predicate)")
            continue
        name = str(item.elts[0].value)
        try:
            groups: dict[str, dict[str, Any]] = {}
            top = _translate(item.elts[1], env, groups, name="MATCH")
            for group in groups.values():
                group["required"] = False
            for gname in top:
                groups[gname]["required"] = True
            out.append({"name": name, "description": f"From searches/{stem}.py", "query": "", "groups": list(groups.values())})
        except _Untranslatable as error:
            problems.append(f"{stem}: {name}: {error}")
    return out, problems


def _terms(call: ast.Call) -> list[str]:
    terms = []
    for arg in call.args:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            raise _Untranslatable("a term that is not a plain string")
        terms.append(arg.value)
    return terms


def _translate(node: ast.AST, env: dict[str, ast.AST], groups: dict[str, dict[str, Any]], name: str) -> list[str]:
    """Adds the groups node needs; answers the names that must all match."""
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise _Untranslatable(f"{node.id} is not defined in search()")
        if node.id in groups:
            return [node.id]
        return _translate(env[node.id], env, groups, node.id)
    if isinstance(node, ast.Lambda):
        # `lambda h: not X(h)` with X an any group (or a combine_or of them)
        # is a none group over the same terms.
        body = node.body
        if (isinstance(body, ast.UnaryOp) and isinstance(body.op, ast.Not) and isinstance(body.operand, ast.Call)
                and isinstance(body.operand.func, ast.Name) and len(body.operand.args) == 1):
            inner = _translate(body.operand.func, env, groups, body.operand.func.id)
            if len(inner) == 1 and groups[inner[0]]["mode"] == "any":
                unique = name if name not in groups else f"{name}_{len(groups)}"
                groups[unique] = {"name": unique, "mode": "none", "terms": list(groups[inner[0]]["terms"])}
                return [unique]
        raise _Untranslatable("a lambda (rewrite it as none_of or a group)")
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        raise _Untranslatable("not a call to any_of / all_of / none_of / combine_and / combine_or / at_least")
    fn = node.func.id
    unique = name
    while unique in groups:
        unique = f"{name}_{len(groups)}"
    if fn in ("any_of", "all_of", "none_of"):
        groups[unique] = {"name": unique, "mode": fn.split("_")[0], "terms": _terms(node)}
        return [unique]
    if fn == "combine_and":
        needed: list[str] = []
        for index, arg in enumerate(node.args):
            needed.extend(_translate(arg, env, groups, f"{name}_{index + 1}"))
        return needed
    if fn == "combine_or":
        terms = _any_terms(node, env)
        if terms is not None:
            # Only any_of underneath: one any group with every term.
            groups[unique] = {"name": unique, "mode": "any", "terms": terms}
            return [unique]
        # Otherwise "at least one of" its parts, each part one group.
        groups[unique] = {"name": unique, "mode": "at_least", "n": 1, "of": []}
        parts = [_one_group(arg, env, groups, f"{name}_{index + 1}") for index, arg in enumerate(node.args)]
        groups[unique]["of"] = parts
        return [unique]
    if fn == "at_least":
        if not node.args or not isinstance(node.args[0], ast.Constant):
            raise _Untranslatable("at_least without a number first")
        groups[unique] = {"name": unique, "mode": "at_least", "n": int(node.args[0].value), "of": []}
        groups[unique]["of"] = [_one_group(arg, env, groups, f"{name}_{index + 1}") for index, arg in enumerate(node.args[1:])]
        return [unique]
    raise _Untranslatable(f"{fn}() is not understood")


def _one_group(node: ast.AST, env: dict[str, ast.AST], groups: dict[str, dict[str, Any]], name: str) -> str:
    """node as a single group: a combine_and of several becomes "at least
    all n of them"."""
    named = _translate(node, env, groups, name)
    if len(named) == 1:
        return named[0]
    unique = name
    while unique in groups:
        unique = f"{name}_{len(groups)}"
    groups[unique] = {"name": unique, "mode": "at_least", "n": len(named), "of": named}
    return unique


def _any_terms(node: ast.AST, env: dict[str, ast.AST]) -> list[str] | None:
    """Every term, when node is any_of or a combine_or of only those (through
    variables); None otherwise."""
    if isinstance(node, ast.Name):
        target = env.get(node.id)
        return None if target is None else _any_terms(target, env)
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return None
    if node.func.id == "any_of":
        try:
            return _terms(node)
        except _Untranslatable:
            return None
    if node.func.id == "combine_or":
        out: list[str] = []
        for arg in node.args:
            found = _any_terms(arg, env)
            if found is None:
                return None
            out.extend(found)
        return out
    return None


def import_legacy(saved: SavedSearches, folder: Path, by: str) -> tuple[int, list[str]]:
    """Every searches/*.py under folder, translated and saved (a name already
    saved is left as it is). -> (how many saved, problems)."""
    count = 0
    problems: list[str] = []
    have = {r["name"].lower() for r in saved.all()}
    for path in sorted(folder.glob("*.py")):
        found, issues = translate_legacy(path.read_text(encoding="utf-8"), path.stem)
        problems.extend(issues)
        for search in found:
            if search["name"].lower() in have:
                continue
            try:
                saved.save(search, by)
                have.add(search["name"].lower())
                count += 1
            except SearchError as error:
                problems.append(f"{path.stem}: {search['name']}: {error}")
    return count, problems
