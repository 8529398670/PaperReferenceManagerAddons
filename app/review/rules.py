"""The screener's rules as data.

Every word list, threshold, extraction field and dataset the old screener had
as Python constants lives in one document: config/review.yaml holds the
defaults, and the owner's edits (the Screener rules page) are a whole copy of
the document kept in the database. load() checks the document's shape,
compiles every pattern, and returns a frozen Rules; a mistake is reported with
where it is ("extraction.fields[TR].patterns[2]: unbalanced parenthesis") and
nothing is saved.

Rules.signature is a hash of the document: the review stage's input includes
it, so a saved change re-screens each paper as the queue reaches it.
"""
from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import msgspec
import yaml

GROUPS = ("Architecture", "Acquisition", "Preprocessing")
POST_KINDS = ("template", "seconds_or_ms", "count", "negation")
PARAMS = ("Field_Strength", "Scanner", "TR", "TE", "Flip_Angle", "Voxel_Size", "N_Slices", "Multiband")
MACRO = re.compile(r"<<(\w+)>>")
PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


class RulesError(Exception):
    """The document is not usable: problems is [{path, message}]."""

    def __init__(self, problems: list[dict[str, str]]) -> None:
        super().__init__("; ".join(f"{p['path']}: {p['message']}" for p in problems[:5]))
        self.problems = problems


# -- the document's shape ------------------------------------------------------------

class Doc(msgspec.Struct, forbid_unknown_fields=True):
    pass


class Threshold(Doc):
    value: float
    why: str = ""


class Vocab(Doc):
    label: str
    patterns: list[str]
    help: str = ""


class VocabSet(Doc):
    fmri_evidence: Vocab
    fmri_strong: Vocab
    other_modality: Vocab
    attn_built: Vocab
    attn_pretrained: Vocab
    ours: Vocab
    decode_generic: Vocab


class SurveyTitle(Doc):
    pattern: str
    label: str = ""
    help: str = ""


class Role(Doc):
    label: str
    patterns: list[str] = []
    use_vocab: str = ""


class Task(Doc):
    name: str
    priority: int
    patterns: list[str]


class Exclusion(Doc):
    label: str
    patterns: list[str]


class Exclusions(Doc):
    survey: Exclusion
    encoding: Exclusion
    reconstruction: Exclusion


class Reasons(Doc):
    survey: str
    not_fmri: str
    no_fmri_named: str
    no_attention: str
    no_attention_abstract: str
    encoding: str
    reconstruction: str
    no_decoding: str
    no_text: str


class CriteriaText(Doc):
    full: list[str]
    abstract: list[str]


class FullThresholds(Doc):
    methods_min_chars: Threshold
    fmri_full_min: Threshold
    fmri_core_min: Threshold
    dom_core_min: Threshold
    dom_core_ratio: Threshold
    dom_full_min: Threshold
    dom_full_ratio: Threshold
    multimodal_min: Threshold
    attn_near_window: Threshold
    attn_methods_min: Threshold
    attn_total_min: Threshold
    attn_total_with_ours_min: Threshold
    attn_methods_with_ours_min: Threshold
    task_weight_title: Threshold
    task_weight_abstract: Threshold
    task_weight_full: Threshold
    decoding_min: Threshold
    survey_weight_title: Threshold
    survey_weight_abstract: Threshold
    survey_weight_body: Threshold
    survey_body_chars: Threshold
    survey_min: Threshold
    encoding_min: Threshold
    reconstruction_min: Threshold
    borderline_attn_min: Threshold
    borderline_attn_max: Threshold


class AbstractThresholds(Doc):
    fmri_min: Threshold
    multimodal_min: Threshold
    attn_near_window: Threshold
    attn_total_min: Threshold
    task_weight_title: Threshold
    task_weight_abstract: Threshold
    decoding_min: Threshold
    survey_weight_title: Threshold
    survey_weight_abstract: Threshold
    survey_min: Threshold
    encoding_min: Threshold
    reconstruction_min: Threshold


class Thresholds(Doc):
    full: FullThresholds
    abstract: AbstractThresholds


class Post(Doc):
    kind: Literal["template", "seconds_or_ms", "count", "negation"]
    template: str = ""
    lower: bool = False
    strip: str = ""
    replace: dict[str, str] = {}
    ms_above: float = 50.0
    when: str = ""
    value: str = ""


class Plausible(Doc):
    range: list[float] | None = None
    range_seconds: list[float] | None = None


class FieldDef(Doc):
    name: str
    group: Literal["Architecture", "Acquisition", "Preprocessing"]
    patterns: list[str]
    post: Post
    plausible: Plausible | None = None


class Extraction(Doc):
    text_cap: Threshold
    context_window: Threshold
    evidence_quotes: Threshold
    evidence_chars: Threshold
    word_numbers: dict[str, int]
    macros: dict[str, str]
    fields: list[FieldDef]


class Dataset(Doc):
    name: str
    aliases: list[str]
    home: str = ""
    description: str = ""


class Param(Doc):
    name: Literal["Field_Strength", "Scanner", "TR", "TE", "Flip_Angle", "Voxel_Size", "N_Slices", "Multiband"]
    pattern: str
    ignore_case: bool = True


class Consensus(Doc):
    min_hits_full: Threshold
    min_hits_abstract: Threshold
    window: Threshold
    max_spots: Threshold
    voxel_max_mm: Threshold
    min_papers: Threshold
    top_k: Threshold
    params: list[Param]
    voxel_noise_left: str
    fallback: dict[str, str]
    aliases_ignore_case: bool = False


class Missing(Doc):
    precision: Threshold
    max_nearmiss: Threshold
    miss_labels: dict[str, str]
    caveat: str = ""


class RulesDoc(Doc):
    version: int
    criteria_text: CriteriaText
    vocab: VocabSet
    survey_title: SurveyTitle
    attention_roles: list[Role]
    tasks: list[Task]
    unclassified_priority: int
    exclusions: Exclusions
    reasons: Reasons
    thresholds: Thresholds
    extraction: Extraction
    datasets: list[Dataset]
    consensus: Consensus
    missing: Missing


VOCAB_NAMES = tuple(VocabSet.__struct_fields__)


# -- compiled -------------------------------------------------------------------------

@dataclass(frozen=True)
class CompiledField:
    name: str
    group: str
    patterns: tuple[re.Pattern[str], ...]
    post: Post
    when: re.Pattern[str] | None
    plausible: Plausible | None


@dataclass(frozen=True)
class Rules:
    doc: RulesDoc
    data: dict[str, Any]
    signature: str
    # name -> (each pattern compiled, the alternation of them all)
    vocab: dict[str, tuple[tuple[re.Pattern[str], ...], re.Pattern[str] | None]]
    survey_title: re.Pattern[str]
    roles: tuple[tuple[str, re.Pattern[str] | None], ...]
    tasks: tuple[tuple[str, int, tuple[re.Pattern[str], ...], re.Pattern[str] | None], ...]
    exclusions: dict[str, tuple[tuple[re.Pattern[str], ...], re.Pattern[str] | None]]
    fields: tuple[CompiledField, ...]
    word_numbers: dict[str, int]
    datasets: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]
    params: tuple[tuple[str, re.Pattern[str]], ...]
    voxel_noise_left: re.Pattern[str]
    priority: dict[str, int] = field(default_factory=dict)

    def full(self, name: str) -> float:
        return getattr(self.doc.thresholds.full, name).value

    def abstract(self, name: str) -> float:
        return getattr(self.doc.thresholds.abstract, name).value

    def ext(self, name: str) -> float:
        return getattr(self.doc.extraction, name).value

    def cons(self, name: str) -> float:
        return getattr(self.doc.consensus, name).value


def signature_of(data: dict[str, Any]) -> str:
    raw = msgspec.json.encode(data, order="sorted")
    return hashlib.sha1(raw).hexdigest()[:16]


_YAML_CACHE: dict[tuple[str, float], dict[str, Any]] = {}
_RULES_CACHE: dict[str, Rules] = {}
_CACHE_MAX = 8
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def read_yaml(path: Path) -> dict[str, Any]:
    """A rules file, parsed (cached by path and mtime: the defaults are read
    by every service and test)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    cached = _YAML_CACHE.get((str(path), mtime))
    if cached is None:
        with open(path, encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=Loader)  # noqa: S506 -- a safe loader
        if not isinstance(data, dict):
            raise RulesError([{"path": str(path), "message": "not a YAML mapping"}])
        if len(_YAML_CACHE) >= _CACHE_MAX:
            _YAML_CACHE.clear()
        _YAML_CACHE[(str(path), mtime)] = data
        cached = data
    return copy.deepcopy(cached)


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000)


def load(data: dict[str, Any]) -> Rules:
    """Check and compile a rules document. Raises RulesError with every
    problem found (the shape first; patterns only once the shape is right).
    The same document twice is compiled once."""
    try:
        key = signature_of(data)
    except (TypeError, msgspec.EncodeError):
        key = ""
    if key and key in _RULES_CACHE:
        return _RULES_CACHE[key]
    rules = _compile(data)
    if key:
        if len(_RULES_CACHE) >= _CACHE_MAX:
            _RULES_CACHE.clear()
        _RULES_CACHE[key] = rules
    return rules


def _compile(data: dict[str, Any]) -> Rules:
    try:
        doc = msgspec.convert(data, RulesDoc)
    except msgspec.ValidationError as error:
        text = str(error)
        where = "$"
        if " - at `" in text:
            text, _, where = text.partition(" - at `")
            where = where.rstrip("`")
        raise RulesError([{"path": _readable(where), "message": text}]) from None
    problems: list[dict[str, str]] = []
    builder = _Builder(problems)
    rules = builder.build(doc, msgspec.to_builtins(doc))
    if problems:
        raise RulesError(problems)
    return rules


def _readable(where: str) -> str:
    return where.removeprefix("$.").removeprefix("$") or "(top)"


class _Builder:
    def __init__(self, problems: list[dict[str, str]]) -> None:
        self.problems = problems

    def bad(self, path: str, message: str) -> None:
        self.problems.append({"path": path, "message": message})

    def rx(self, path: str, pattern: str, flags: int = re.I) -> re.Pattern[str] | None:
        if not pattern.strip():
            self.bad(path, "empty pattern")
            return None
        try:
            return re.compile(pattern, flags)
        except re.error as error:
            self.bad(path, f"not a valid pattern: {error}")
            return None
        except (OverflowError, RecursionError):
            self.bad(path, "pattern too large")
            return None

    def many(self, path: str, patterns: list[str], expand: Any = None, alternate: bool = True) -> tuple[tuple[re.Pattern[str], ...], re.Pattern[str] | None]:
        compiled = []
        sources = []
        for i, pattern in enumerate(patterns):
            source = expand(f"{path}[{i}]", pattern) if expand else pattern
            if source is None:
                continue
            found = self.rx(f"{path}[{i}]", source)
            if found is not None:
                compiled.append(found)
                sources.append(source)
        alt = None
        if alternate and sources:
            try:
                alt = re.compile("|".join(f"(?:{s})" for s in sources), re.I)
            except re.error as error:
                self.bad(path, f"these patterns cannot be combined: {error}")
        return tuple(compiled), alt

    def build(self, doc: RulesDoc, data: dict[str, Any]) -> Rules:
        vocab = {name: self.many(f"vocab.{name}.patterns", getattr(doc.vocab, name).patterns) for name in VOCAB_NAMES}
        survey = self.rx("survey_title.pattern", doc.survey_title.pattern) or re.compile(r"(?!x)x")
        roles = []
        for i, role in enumerate(doc.attention_roles):
            if role.use_vocab:
                if role.use_vocab not in VOCAB_NAMES:
                    self.bad(f"attention_roles[{i}].use_vocab", f"no word list called {role.use_vocab!r}")
                    continue
                roles.append((role.label, vocab[role.use_vocab][1]))
            else:
                roles.append((role.label, self.many(f"attention_roles[{i}].patterns", role.patterns)[1]))
        tasks = []
        names: set[str] = set()
        for i, task in enumerate(doc.tasks):
            if not task.name.strip():
                self.bad(f"tasks[{i}].name", "a task needs a name")
            if task.name in names:
                self.bad(f"tasks[{i}].name", f"{task.name!r} is listed twice")
            names.add(task.name)
            if not 1 <= task.priority <= 9:
                self.bad(f"tasks[{i}].priority", "priority is 1 (most wanted) to 9")
            tasks.append((task.name, task.priority, *self.many(f"tasks[{i}].patterns", task.patterns)))
        if not tasks:
            self.bad("tasks", "at least one task category is needed")
        exclusions = {
            name: self.many(f"exclusions.{name}.patterns", getattr(doc.exclusions, name).patterns)
            for name in Exclusions.__struct_fields__
        }
        for section in ("full", "abstract"):
            block = getattr(doc.thresholds, section)
            for name in block.__struct_fields__:
                if getattr(block, name).value < 0:
                    self.bad(f"thresholds.{section}.{name}.value", "must not be negative")
        for name in ("text_cap", "context_window", "evidence_quotes", "evidence_chars"):
            if getattr(doc.extraction, name).value < 1:
                self.bad(f"extraction.{name}.value", "must be at least 1")
        words = dict(doc.extraction.word_numbers)
        macros = dict(doc.extraction.macros)
        macros["WORDS"] = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True)) or "(?!x)x"

        def expand(path: str, pattern: str) -> str | None:
            missing = [m for m in MACRO.findall(pattern) if m not in macros]
            if missing:
                self.bad(path, f"unknown <<{missing[0]}>> (known: {', '.join('<<' + k + '>>' for k in sorted(macros))})")
                return None
            return MACRO.sub(lambda m: macros[m.group(1)], pattern)

        fields = []
        seen: set[str] = set()
        for i, spec in enumerate(doc.extraction.fields):
            path = f"extraction.fields[{spec.name or i}]"
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", spec.name or ""):
                self.bad(f"{path}.name", "letters, digits and _ only, starting with a letter")
            if spec.name in seen:
                self.bad(f"{path}.name", "listed twice")
            seen.add(spec.name)
            compiled = self.many(f"{path}.patterns", spec.patterns, expand, alternate=False)[0]
            if not spec.patterns:
                self.bad(f"{path}.patterns", "a field needs at least one pattern")
            post = spec.post
            when = None
            if post.kind in ("template", "count", "negation") and not post.template:
                self.bad(f"{path}.post.template", "a template is needed, such as ${v} or ${0}")
            if post.kind == "count" and "${n}" not in post.template:
                self.bad(f"{path}.post.template", "a count template uses ${n}")
            if post.kind == "negation":
                when = self.rx(f"{path}.post.when", post.when)
            if post.kind == "seconds_or_ms":
                for p, c in zip(spec.patterns, compiled, strict=False):
                    if "v" not in c.groupindex:
                        self.bad(f"{path}.patterns", f"seconds_or_ms needs a (?P<v>...) group: {p[:60]}")
                        break
            if spec.plausible is not None:
                for key in ("range", "range_seconds"):
                    span = getattr(spec.plausible, key)
                    if span is not None and (len(span) != 2 or span[0] > span[1]):
                        self.bad(f"{path}.plausible.{key}", "give [lowest, highest]")
            fields.append(CompiledField(spec.name, spec.group, compiled, post, when, spec.plausible))
        flags = re.I if doc.consensus.aliases_ignore_case else 0
        datasets = []
        for i, ds in enumerate(doc.datasets):
            if not ds.name.strip():
                self.bad(f"datasets[{i}].name", "a dataset needs a name")
            pats = tuple(p for j, a in enumerate(ds.aliases) if (p := self.rx(f"datasets[{ds.name or i}].aliases[{j}]", a, flags)) is not None)
            datasets.append((ds.name, pats))
        params = []
        for i, param in enumerate(doc.consensus.params):
            found = self.rx(f"consensus.params[{param.name}].pattern", param.pattern, re.I if param.ignore_case else 0)
            if found is not None:
                if found.groups < 1:
                    self.bad(f"consensus.params[{param.name}].pattern", "needs a capture group around the value")
                params.append((param.name, found))
        for key, value in doc.consensus.fallback.items():
            if value not in PARAMS:
                self.bad(f"consensus.fallback.{key}", f"not a consensus parameter (one of {', '.join(PARAMS)})")
            if key not in seen:
                self.bad(f"consensus.fallback.{key}", "no extraction field by that name")
        noise = self.rx("consensus.voxel_noise_left", doc.consensus.voxel_noise_left) or re.compile(r"(?!x)x")
        priority = {name: prio for name, prio, *_ in tasks}
        return Rules(
            doc=doc, data=data, signature=signature_of(data), vocab=vocab, survey_title=survey, roles=tuple(roles),
            tasks=tuple(tasks), exclusions=exclusions, fields=tuple(fields), word_numbers=words, datasets=tuple(datasets),
            params=tuple(params), voxel_noise_left=noise, priority=priority,
        )


CHANGE_PATHS = (
    "A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), "
    "[name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes "
    "Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; "
    "{path, remove: true} takes it out."
)
MAX_CHANGES = 500


def parse_path(path: str) -> list[str | tuple[str, str]]:
    """thresholds.full.x.value -> ["thresholds", "full", "x", "value"];
    fields[TR].patterns[+] -> ["fields", ("[", "TR"), "patterns", ("[", "+")].
    Raises ValueError for a path it cannot read."""
    steps: list[str | tuple[str, str]] = []
    i, n = 0, len(path)
    if not path.strip():
        raise ValueError("an empty path")
    while i < n:
        if path[i] == "[":
            end = path.find("]", i)
            if end < 0:
                raise ValueError("a [ with no ]")
            steps.append(("[", path[i + 1:end]))
            i = end + 1
        elif path[i] == ".":
            if not steps or i + 1 >= n or path[i + 1] in ".[":
                raise ValueError("a misplaced dot")
            i += 1
        else:
            j = i
            while j < n and path[j] not in ".[":
                j += 1
            steps.append(path[i:j])
            i = j
    return steps


def _item(container: Any, step: str | tuple[str, str], path: str) -> tuple[Any, Any]:
    """(the container holding step, the key or index in it)."""
    if isinstance(step, str):
        if not isinstance(container, dict):
            raise RulesError([{"path": path, "message": f"{step!r} is not under a mapping here"}])
        return container, step
    name = step[1]
    if not isinstance(container, list):
        raise RulesError([{"path": path, "message": f"[{name}] is not under a list here"}])
    if name == "+":
        return container, len(container)
    for i, item in enumerate(container):
        if isinstance(item, dict) and item.get("name") == name:
            return container, i
    if name.isdigit() and int(name) < len(container):
        return container, int(name)
    raise RulesError([{"path": path, "message": f"no item [{name}] in this list"}])


def apply_changes(data: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    """A copy of a rules document with each change made in turn (see
    CHANGE_PATHS). Raises RulesError naming the change that cannot be made;
    the result is not checked here: load() does that."""
    if len(changes) > MAX_CHANGES:
        raise RulesError([{"path": "changes", "message": f"at most {MAX_CHANGES} changes at a time"}])
    out = copy.deepcopy(data)
    for number, change in enumerate(changes):
        path = change.get("path") if isinstance(change, dict) else None
        if not isinstance(path, str):
            raise RulesError([{"path": f"changes[{number}]", "message": "each change needs a path"}])
        remove = bool(change.get("remove"))
        if not remove and "value" not in change:
            raise RulesError([{"path": path, "message": "give a value, or remove: true"}])
        try:
            steps = parse_path(path)
        except ValueError as error:
            raise RulesError([{"path": path, "message": f"not a path: {error}"}]) from None
        node: Any = out
        for step in steps[:-1]:
            holder, at = _item(node, step, path)
            if isinstance(holder, list) and at == len(holder):
                raise RulesError([{"path": path, "message": "[+] only goes at the end"}])
            if isinstance(holder, dict) and at not in holder:
                raise RulesError([{"path": path, "message": f"nothing at {at!r}"}])
            node = holder[at]
        last = steps[-1]
        if isinstance(last, tuple) and last[1] == "+":
            if remove:
                raise RulesError([{"path": path, "message": "nothing to remove at [+]"}])
            if not isinstance(node, list):
                raise RulesError([{"path": path, "message": "[+] is not under a list here"}])
            node.append(copy.deepcopy(change["value"]))
            continue
        holder, at = _item(node, last, path)
        if remove:
            if isinstance(holder, dict) and at not in holder:
                raise RulesError([{"path": path, "message": "nothing there to remove"}])
            del holder[at]
        else:
            holder[at] = copy.deepcopy(change["value"])
    return out


def schema() -> dict[str, Any]:
    """The document's JSON schema, for an agent writing one."""
    return msgspec.json.schema(RulesDoc)


def differences(current: Any, default: Any, path: str = "") -> list[str]:
    """The paths where an edited document differs from the defaults: what the
    page marks "changed"."""
    if isinstance(current, dict) and isinstance(default, dict):
        out = []
        for key in dict.fromkeys(list(current) + list(default)):
            out += differences(current.get(key), default.get(key), f"{path}.{key}" if path else str(key))
        return out
    if isinstance(current, list) and isinstance(default, list) and all(isinstance(x, dict) and "name" in x for x in current + default):
        mine = {x["name"]: x for x in current}
        theirs = {x["name"]: x for x in default}
        out = []
        for name in dict.fromkeys(list(mine) + list(theirs)):
            out += differences(mine.get(name), theirs.get(name), f"{path}[{name}]")
        if not out and [x["name"] for x in current] != [x["name"] for x in default]:
            out.append(path)
        return out
    return [] if current == default else [path]
