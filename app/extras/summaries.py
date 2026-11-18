"""LLM summaries of a paper's sections, and their rollup. Ported from the old
prma src/tasks/summarize.py and summarize_rollup.py.

Only on request: the Paper screen's Summarize button, or a list's selection.
A request queues (paper, section) tasks; one thread works through them, one
call each, and says so on the library stream ("summary" {key, section,
state}). Each answer, {hashtags, summary, provider, model, at, by}, is kept
in db.BUCKET_SUMMARIES under "<key>|<section>": summaries cost money, so they
are kept and backed up rather than derived.

The text a section gets is the content stage's heading split
(sections.json); the abstract is Zotero's, else the split's, else
OpenAlex's. "all" is the whole text but the references, captions and back
matter.

Prompts: config/llm-prompts/<section>.txt, else all.txt, else the built-in
one, each with --- SYSTEM --- / --- USER --- blocks and {title} {doi}
{section_display} {text} placeholders.

The rollup turns one section's summaries into a table: the "**Subsection.**"
headers the prompts ask for become columns, then the hashtags, a hashtag
histogram, and the extra columns config/rollup-extra-columns.yaml declares
(keyword / regex snippets from the summary and the section's text).
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import yaml

from app.core import db
from app.extras import llm

SECTIONS = (
    ("all", "Full Paper"), ("abstract", "Abstract"), ("introduction", "Introduction"), ("background", "Background"),
    ("methods", "Methods"), ("results", "Results"), ("conclusions", "Conclusions"), ("future", "Future Work"),
)
SECTION_KEYS = tuple(k for k, _ in SECTIONS)
DISPLAY = dict(SECTIONS)
# Which keys of the heading split each section reads.
SPLIT_KEYS = {
    "introduction": ("introduction",), "background": ("background",), "methods": ("methods",),
    "results": ("results", "discussion"), "conclusions": ("conclusion",), "future": ("future",),
}
LEFT_OUT_OF_ALL = ("references", "figures", "tables", "other")
MAX_QUEUE = 5000
SEP = "|"


def record_key(key: str, section: str) -> str:
    return f"{key}{SEP}{section}"


class Summaries:
    def __init__(self, store: db.Store, catalogue: Any, content: Any, prompts_dir: Path, extra_columns_file: Path,
                 settings: Callable[[], Any], publish: Callable[[str, dict[str, Any]], None] = lambda n, d: None) -> None:
        self.store = store
        self.catalogue = catalogue
        self.content = content
        self.prompts_dir = prompts_dir
        self.extra_columns_file = extra_columns_file
        self.settings = settings
        self.publish = publish
        # Replaced in tests: a Choice -> something with complete(system, user).
        self.client_factory: Callable[[llm.Choice], Any] = llm.Client
        self._queue: list[tuple[str, str, bool, str]] = []
        self._queued: set[tuple[str, str]] = set()
        self._running: tuple[str, str] | None = None
        self._errors: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None
        self.done_count = 0
        # The rollup's extra columns per (key, section), with what they were
        # made from: the summary's time and the section text's length.
        self._extras: dict[tuple[str, str], tuple[tuple[Any, int], dict[str, str]]] = {}

    # -- reading ----------------------------------------------------------------------

    def choice(self) -> llm.Choice | None:
        return llm.choose(self.settings())

    def get(self, key: str, section: str) -> dict[str, Any] | None:
        return self.store.get(db.BUCKET_SUMMARIES, record_key(key, section))

    def of_paper(self, key: str) -> dict[str, dict[str, Any]]:
        """Every summary of one paper, by section, and each queued or failed."""
        out: dict[str, dict[str, Any]] = {}
        for section in SECTION_KEYS:
            found = self.get(key, section)
            if found:
                out[section] = {**found, "state": "done"}
        with self._lock:
            for k, s, _, _ in self._queue:
                if k == key:
                    out.setdefault(s, {})["state"] = "queued"
            if self._running and self._running[0] == key:
                out.setdefault(self._running[1], {})["state"] = "running"
            for (k, s), error in self._errors.items():
                if k == key and out.get(s, {}).get("state") != "queued":
                    out.setdefault(s, {}).update(state="failed" if "summary" not in out.get(s, {}) else "done", error=error)
        return out

    def all(self, section: str) -> list[tuple[str, dict[str, Any]]]:
        """(paper key, summary) of one section, every one kept."""
        suffix = SEP + section
        return [(str(k)[: -len(suffix)], r) for k, r in self.store.all(db.BUCKET_SUMMARIES) if str(k).endswith(suffix)]

    def counts(self) -> dict[str, int]:
        found: Counter[str] = Counter()
        for k, _ in self.store.all(db.BUCKET_SUMMARIES):
            found[str(k).rsplit(SEP, 1)[-1]] += 1
        return dict(found)

    def status(self) -> dict[str, Any]:
        choice = self.choice()
        with self._lock:
            return {
                "provider": choice.provider if choice else "", "model": choice.model if choice else "",
                "queued": len(self._queue), "running": list(self._running) if self._running else None,
                "failed": len(self._errors), "done": self.done_count,
            }

    # -- the section's text -------------------------------------------------------------

    def section_text(self, key: str, section: str) -> str:
        paper = self.catalogue.get(key)
        parts = (self.content.files.read(key, "sections.json") or {}).get("sections") or []
        if section == "abstract":
            text = (paper.record.get("abstract") if paper else "") or ""
            if not text:
                text = "\n\n".join(p["text"] for p in parts if p["key"] == "abstract" and p.get("text"))
            if not text:
                text = self.content.oa_abstract(key)
            return text.strip()
        if section == "all":
            kept = []
            for part in parts:
                if part["key"] in LEFT_OUT_OF_ALL:
                    continue
                if part.get("heading"):
                    kept.append(part["heading"])
                if part.get("text"):
                    kept.append(part["text"])
            return "\n\n".join(kept).strip()
        wanted = SPLIT_KEYS.get(section, ())
        return "\n\n".join(p["text"] for p in parts if p["key"] in wanted and p.get("text")).strip()

    def prompt(self, section: str) -> tuple[str, str]:
        for name in (section, "all"):
            path = self.prompts_dir / f"{name}.txt"
            try:
                parsed = llm.parse_prompt(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if parsed:
                return parsed
        return llm.BUILTIN_SYSTEM, llm.BUILTIN_USER

    # -- asking ----------------------------------------------------------------------------

    def request(self, keys: list[str], sections: list[str], force: bool, by: str, first: bool = False) -> dict[str, int]:
        """Queue (paper, section) for each pair; a summary already kept is left
        alone unless force. first puts them at the front (one paper's button).
        -> {queued, kept (already summarised), unknown (no such paper)}."""
        out = {"queued": 0, "kept": 0, "unknown": 0}
        fresh: list[tuple[str, str, bool, str]] = []
        with self._lock:
            for key in keys:
                if self.catalogue.get(key) is None:
                    out["unknown"] += 1
                    continue
                for section in sections:
                    pair = (key, section)
                    if pair in self._queued or self._running == pair:
                        continue
                    if not force and self.store.get(db.BUCKET_SUMMARIES, record_key(key, section)):
                        out["kept"] += 1
                        continue
                    if len(self._queue) + len(fresh) >= MAX_QUEUE:
                        break
                    fresh.append((key, section, force, by))
                    self._queued.add(pair)
                    self._errors.pop(pair, None)
                    out["queued"] += 1
            self._queue = fresh + self._queue if first else self._queue + fresh
        if fresh:
            self._wake.set()
            for key, section, _, _ in fresh:
                self.publish("summary", {"key": key, "section": section, "state": "queued"})
        return out

    def cancel(self) -> int:
        with self._lock:
            dropped = len(self._queue)
            for key, section, _, _ in self._queue:
                self._queued.discard((key, section))
            self._queue = []
        self.publish("summary", {"state": "cancelled"})
        return dropped

    def delete(self, key: str, section: str) -> dict[str, Any] | None:
        old = self.get(key, section)
        if old is not None:
            self.store.delete(db.BUCKET_SUMMARIES, record_key(key, section))
            self.publish("summary", {"key": key, "section": section, "state": "deleted"})
        return old

    def put(self, key: str, section: str, record: dict[str, Any]) -> None:
        self.store.put(db.BUCKET_SUMMARIES, record_key(key, section), record)

    def summarize_one(self, key: str, section: str, by: str) -> dict[str, Any]:
        """One call, now, on this thread. Raises llm.LlmError, or ValueError
        when there is no key or no text."""
        choice = self.choice()
        if choice is None:
            raise ValueError("no language model is set up: add a key to the llm: section of config.yaml")
        paper = self.catalogue.get(key)
        if paper is None:
            raise ValueError("no such paper")
        text = self.section_text(key, section)
        if not text:
            raise ValueError(f"the paper has no {DISPLAY[section]} text to summarise")
        text, cut = llm.clip(text, choice.provider)
        system, user = self.prompt(section)
        args = (paper.record.get("title") or "", paper.record.get("doi") or "", DISPLAY[section], text)
        answer = self.client_factory(choice).complete(llm.fill(system, *args), llm.fill(user, *args))
        parsed = llm.parse_answer(answer)
        if not parsed["summary"]:
            raise llm.LlmError("the model answered with nothing")
        record = {**parsed, "provider": choice.provider, "model": choice.model, "at": time.time(), "by": by, "cut": cut}
        self.put(key, section, record)
        return record

    # -- the thread ---------------------------------------------------------------------------

    def start(self) -> None:
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="summaries", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop:
            with self._lock:
                job = self._queue.pop(0) if self._queue else None
                if job:
                    self._queued.discard((job[0], job[1]))
                    self._running = (job[0], job[1])
            if job is None:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            key, section, _, by = job
            self.publish("summary", {"key": key, "section": section, "state": "running"})
            state, error = "done", ""
            try:
                self.summarize_one(key, section, by)
                self.done_count += 1
            except (llm.LlmError, ValueError) as problem:
                state, error = "failed", str(problem)
            except Exception as problem:  # noqa: BLE001 -- one bad paper never stops the queue
                state, error = "failed", repr(problem)
            with self._lock:
                self._running = None
                if error:
                    self._errors[(key, section)] = error
            self.publish("summary", {"key": key, "section": section, "state": state, "error": error})

    # -- the rollup -----------------------------------------------------------------------------

    def extra_columns(self) -> list[dict[str, Any]]:
        try:
            data = yaml.safe_load(self.extra_columns_file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return []
        out = []
        for raw in data.get("extra_columns") or []:
            if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
                continue
            spec = {
                "name": str(raw["name"]).strip(),
                "sources": list(raw.get("sources") or ("summary", "section_text")),
                "context_chars": int(raw.get("context_chars", 300)),
                "max_snippets": int(raw.get("max_snippets", 4)),
                "keywords": [str(k).strip().lower() for k in raw.get("keywords") or [] if str(k).strip()],
                "regex_re": [],
            }
            for pattern in raw.get("regex") or []:
                try:
                    spec["regex_re"].append(re.compile(str(pattern), re.IGNORECASE))
                except re.error:
                    continue
            out.append(spec)
        return out

    def rollup(self, section: str) -> dict[str, Any]:
        """One section's summaries as a table: {columns (subsection headers in
        first-seen order), extra (extra column names), rows: [{key, title, doi,
        year, journal, hashtags, parts: {header: text}, extra: {name: text},
        summary}], hashtags: [[tag, n]]}."""
        found = self.all(section)
        found.sort(key=lambda item: item[0])
        extras = self.extra_columns()
        try:
            self._extras_sig = self.extra_columns_file.stat().st_mtime
        except OSError:
            self._extras_sig = 0
        columns: list[str] = []
        tags: Counter[str] = Counter()
        rows = []
        for key, record in found:
            paper = self.catalogue.get(key)
            parts = split_subsections(record.get("summary") or "")
            for header, _ in parts:
                if header not in columns:
                    columns.append(header)
            for tag in (record.get("hashtags") or "").split():
                tags[tag.lower()] += 1
            extra: dict[str, str] = {}
            if extras:
                sources = {"summary": record.get("summary") or ""}
                if any("section_text" in spec["sources"] for spec in extras):
                    sources["section_text"] = self.section_text(key, section) if paper else ""
                made_from = (record.get("at"), len(sources.get("section_text", "")), self._extras_sig)
                kept = self._extras.get((key, section))
                if kept and kept[0] == made_from:
                    extra = kept[1]
                else:
                    for spec in extras:
                        snippets: list[str] = []
                        for name in spec["sources"]:
                            snippets.extend(snippets_of(sources.get(name, ""), spec))
                        extra[spec["name"]] = "\n\n".join(dict.fromkeys(snippets))
                    self._extras[(key, section)] = (made_from, extra)
            record_of = paper.record if paper else {}
            rows.append({
                "key": key, "title": record_of.get("title") or key, "doi": record_of.get("doi") or "", "year": record_of.get("year"),
                "journal": record_of.get("journal") or "", "hashtags": record.get("hashtags") or "", "parts": dict(parts),
                "extra": extra, "summary": record.get("summary") or "", "model": record.get("model") or "", "at": record.get("at"),
            })
        return {"section": section, "columns": columns, "extra": [s["name"] for s in extras], "rows": rows,
                "hashtags": [[t, n] for t, n in tags.most_common()]}


# A line that is one bold label, alone or as a list item ("- **Participants.**").
_SUBSECTION = re.compile(r"^[ \t]*(?:[-*•][ \t]+)?\*\*([^*\n]{1,80}?)\*\*[ \t]*:?[ \t]*$", re.MULTILINE)


def split_subsections(body: str) -> list[tuple[str, str]]:
    """[(header, text)] split on lines that are one bold label
    ("**Study design.**", or "- **Study design.**"); the whole body as
    "(body)" when there are none."""
    matches = list(_SUBSECTION.finditer(body))
    if not matches:
        stripped = body.strip()
        return [("(body)", stripped)] if stripped else []
    out = []
    for index, match in enumerate(matches):
        header = re.sub(r"\s+", " ", match.group(1).strip().rstrip(".:").strip())
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        if header:
            out.append((header, body[match.end():end].strip()))
    return out


def keyword_hits(text: str, keywords: list[str]) -> list[tuple[int, int]]:
    """Where each lowercased keyword stands as whole words ("fMRI task" yes,
    "subscanner" for "scanner" no). str.find, not one big regex: a regex of
    alternatives with lookbehinds tried every position, and took seconds a
    paper."""
    lower = text.lower()
    hits = []
    for word in keywords:
        start = lower.find(word)
        while start >= 0:
            end = start + len(word)
            before = lower[start - 1] if start else " "
            after = lower[end] if end < len(lower) else " "
            if (not word[0].isalnum() or not before.isalnum() and before != "_") and (not word[-1].isalnum() or not after.isalnum() and after != "_"):
                hits.append((start, end))
            start = lower.find(word, start + 1)
    return hits


def _snap(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) to the sentence (or paragraph) around it."""
    back_para = text.rfind("\n\n", 0, start)
    back_sent = max(text.rfind(". ", 0, start), text.rfind("! ", 0, start), text.rfind("? ", 0, start), text.rfind("\n", 0, start))
    new_start = max(back_para + 2 if back_para >= 0 else 0, back_sent + 2 if back_sent >= 0 else 0)
    ends = [i + len(sep) for sep in (". ", "! ", "? ", "\n\n", "\n") if (i := text.find(sep, end)) >= 0]
    return new_start, min(min(ends) if ends else len(text), len(text))


def snippets_of(text: str, spec: dict[str, Any]) -> list[str]:
    """Up to max_snippets sentences where a keyword or pattern matches."""
    if not text:
        return []
    hits = []
    hits.extend(keyword_hits(text, spec.get("keywords") or []))
    for pattern in spec.get("regex_re", []):
        hits.extend((m.start(), m.end()) for m in pattern.finditer(text))
    hits.sort()
    half = max(80, spec.get("context_chars", 300)) // 2
    out: list[str] = []
    last_end = -1
    for start, end in hits:
        s, e = _snap(text, max(0, start - half), min(len(text), end + half))
        if s < last_end:
            continue
        snippet = text[s:e].strip()
        if snippet:
            out.append(snippet)
            last_end = e
        if len(out) >= max(1, spec.get("max_snippets", 4)):
            break
    return out


# -- the old output/summaries/<section>/*.md --------------------------------------------------

_DOI_LINE = re.compile(r"^\*\*DOI:\*\*\s+\[([^\]]+)\]", re.MULTILINE)
_PROVIDER = re.compile(r"^\*\*Provider:\*\*\s+(\S+)", re.MULTILINE)
_MODEL = re.compile(r"^\*\*Model:\*\*\s+(\S+)", re.MULTILINE)
_TAGS = re.compile(r"^\*\*Hashtags:\*\*\s+(.+?)\s*$", re.MULTILINE)
_BODY = re.compile(r"^##\s+Summary\s*$", re.MULTILINE)


def parse_legacy(text: str) -> dict[str, Any] | None:
    """One old summary file -> {doi, hashtags, summary, provider, model}."""
    doi = _DOI_LINE.search(text)
    body = _BODY.search(text)
    if not doi or not body:
        return None
    tags = _TAGS.search(text)
    provider = _PROVIDER.search(text)
    model = _MODEL.search(text)
    return {
        "doi": doi.group(1).strip(), "hashtags": tags.group(1).strip() if tags else "", "summary": text[body.end():].strip(),
        "provider": provider.group(1) if provider else "", "model": model.group(1) if model else "",
    }


def import_legacy(summaries: Summaries, folder: Path, by: str) -> tuple[int, int, int]:
    """<old output>/summaries/<section>/*.md into the bucket, matched to the
    library by DOI; one already kept is left as it is.
    -> (imported, already kept, not in the library)."""
    imported = kept = unknown = 0
    catalogue = summaries.catalogue
    for section in SECTION_KEYS:
        for path in sorted((folder / section).glob("*.md")) if (folder / section).is_dir() else []:
            found = parse_legacy(path.read_text(encoding="utf-8", errors="replace"))
            if not found:
                continue
            paper, how = catalogue.match(found["doi"], "")
            if paper is None:
                unknown += 1
                continue
            if summaries.get(paper.key, section):
                kept += 1
                continue
            summaries.put(paper.key, section, {
                "hashtags": found["hashtags"], "summary": found["summary"], "provider": found["provider"], "model": found["model"],
                "at": path.stat().st_mtime, "by": by, "cut": False, "legacy": True,
            })
            imported += 1
    return imported, kept, unknown
