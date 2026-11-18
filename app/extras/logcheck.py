"""The research-log check: which papers in a Markdown research log are not in
the library. Ported from the old prma src/tasks/check_missing_file.py.

The log is the running notebook kept while reading: dated headings
("# 03SEP2026"), and under each a run of `&nbsp;`-separated blocks, where a
block is a paper's title on one line and its link(s) below:

  # 03SEP2026

  Naturalistic auditory semantic mapping using high-density diffuse optical tomography

  [https://www-spiedigitallibrary-org...](https://www-spiedigitallibrary-org...)

  &nbsp;

Each block is one paper. Its DOI is lifted out of the link when the link
carries one (doi.org, publisher article routes, bioRxiv, ezproxy'd copies),
with what a browser glues on (.full, .abstract, v1, /pdf, MIT Press's
article number) cut off. Each paper is checked the way /api/exists checks: a
DOI settles it; with none, the title is matched (exactly, or at 96). A DOI
miss is retried on the title alone -- the log may carry the preprint's DOI
while the library holds the journal version -- and those are listed apart
("recovered").
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from app.library.zotero import normalize_doi
from app.search import query as q

_DATE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s+(\d{1,2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{4})\s*$", re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s]+)\)", re.IGNORECASE)
_BARE_URL_RE = re.compile(r"https?://[^\s<>)\]]+", re.IGNORECASE)
# The log is written in an editor that writes `&nbsp;` for an empty
# paragraph: that is the block boundary.
_BLOCK_BREAKS = {"&nbsp;", "<br>", "<br/>", "<br />"}
# Bare words where a title would be that are organisation, not a paper.
_NON_TITLE = {
    "abstract", "code", "data", "dataset", "datasets", "github", "notes", "paper", "papers", "pdf", "project",
    "resources", "supplement", "supplementary material", "tangent", "todo", "video",
}
_DOI_DOT_SUFFIX_RE = re.compile(r"(?i)(?:\.full|\.abstract|\.pdf)+$")
_DOI_PATH_SUFFIX_RE = re.compile(r"(?i)(?:/html|/_p)$")
_DOI_VERSION_RE = re.compile(r"(?i)/?v\d+$")
MAX_LOG_BYTES = 8 * 1024 * 1024


def strip_markdown(value: str) -> str:
    """The Markdown a title line gets wrapped in: list markers, blockquote,
    heading hashes, bold / italic, backslash escapes."""
    value = html.unescape(value.strip())
    value = re.sub(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)", "", value)
    value = re.sub(r"^\s*>\s?", "", value)
    value = re.sub(r"^#{1,6}\s+", "", value)
    value = re.sub(r"^\*\*(.*?)\*\*$", r"\1", value)
    value = re.sub(r"^__(.*?)__$", r"\1", value)
    value = re.sub(r"^\*(.*?)\*$", r"\1", value)
    value = re.sub(r"^_(.*?)_$", r"\1", value)
    value = value.replace(r"\_", "_").replace(r"\#", "#").replace(r"\&", "&")
    return " ".join(value.split())


def urls_in(line: str) -> list[str]:
    """The targets of Markdown links when there are any, else the bare URLs.
    Trailing punctuation is prose."""
    found = [u.rstrip(").,;") for u in _MD_LINK_RE.findall(line)]
    if found:
        return found
    return [u.rstrip(".,;") for u in _BARE_URL_RE.findall(line)]


def doi_in(value: str) -> str:
    """A clean DOI out of a URL or a line, or ""."""
    value = unquote(value).replace(r"\_", "_").replace(r"\#", "#")
    doi = normalize_doi(value) or ""
    if not doi:
        return ""
    doi = _DOI_DOT_SUFFIX_RE.sub("", doi)
    doi = _DOI_PATH_SUFFIX_RE.sub("", doi)
    doi = _DOI_VERSION_RE.sub("", doi).rstrip("/")
    # MIT Press puts an article number and a slug after the DOI
    # (.../doi/10.1162/jocn_a_02087/118023/Title); their suffixes never hold
    # a slash, so cut to two parts.
    host = (urlparse(value).hostname or "").lower()
    if host == "direct.mit.edu" or host.startswith("direct-mit-edu."):
        doi = "/".join(doi.split("/")[:2])
    return doi


def looks_like_title(line: str) -> bool:
    raw = line.strip()
    if not raw or raw.lower() in _BLOCK_BREAKS or urls_in(raw):
        return False
    if raw.startswith(("```", "<!--", "|")) or raw.endswith("-->"):
        return False
    # Tab-indented lines are annotations, never the paper.
    if line.startswith("\t"):
        return False
    title = strip_markdown(raw)
    if len(title) < 2 or title.lower() in _NON_TITLE:
        return False
    if _DATE_HEADING_RE.match(raw) or re.fullmatch(r"\d{4}", title):
        return False
    return True


def _parse_block(block: list[tuple[int, str]], date: str) -> dict[str, Any] | None:
    """One block -> one paper, or None: no link (a note, not a paper), or no
    title above the first link. The title is the first eligible line."""
    urls: list[str] = []
    first_url_at = None
    for pos, (_, line) in enumerate(block):
        found = urls_in(line)
        if found:
            if first_url_at is None:
                first_url_at = pos
            urls.extend(found)
    if first_url_at is None:
        return None
    for line_no, line in block[:first_url_at]:
        if looks_like_title(line):
            break
    else:
        return None
    doi = ""
    for candidate in [*urls, *(text for _, text in block)]:
        doi = doi_in(candidate)
        if doi:
            break
    return {"title": strip_markdown(line), "line": line_no, "date": date, "url": urls[0], "doi": doi, "occurrences": [line_no]}


def extract(text: str) -> tuple[list[dict[str, Any]], int]:
    """Every paper block in the log, in order: {title, line, date, url, doi,
    occurrences}. -> (papers, lines)."""
    lines = text.lstrip("﻿").splitlines()
    papers: list[dict[str, Any]] = []
    block: list[tuple[int, str]] = []
    date = ""

    def flush() -> None:
        nonlocal block
        paper = _parse_block(block, date)
        if paper:
            papers.append(paper)
        block = []

    for line_no, line in enumerate(lines, start=1):
        match = _DATE_HEADING_RE.match(line)
        if match:
            flush()
            date = match.group(1).upper()
            continue
        if line.strip().lower() in _BLOCK_BREAKS:
            flush()
            continue
        block.append((line_no, line))
    flush()
    return papers, len(lines)


def deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per paper, on the folded title. The first mention keeps the
    row; later ones add their line and fill in a missing DOI or link."""
    unique: dict[str, dict[str, Any]] = {}
    for paper in papers:
        key = q.fold(paper["title"]) or paper["title"]
        seen = unique.get(key)
        if seen is None:
            unique[key] = paper
            continue
        seen["occurrences"].extend(paper["occurrences"])
        seen["doi"] = seen["doi"] or paper["doi"]
        seen["url"] = seen["url"] or paper["url"]
    return list(unique.values())


def check(papers: list[dict[str, Any]], match: Callable[[str, str], tuple[Any, str]]) -> None:
    """Stamp each paper: found "doi" | "title" | "" (missing), key (the
    library paper), and recovered (its DOI is not in the library but its
    title is). match is Catalogue.match."""
    for paper in papers:
        found, how = match(paper["doi"], paper["title"])
        paper["found"], paper["recovered"], paper["key"] = "", False, ""
        if found is not None:
            paper["found"] = "doi" if how == "doi" else "title"
            paper["key"] = found.key
        elif paper["doi"]:
            found, how = match("", paper["title"])
            if found is not None:
                paper["found"], paper["recovered"], paper["key"] = "title", True, found.key


def _cell(value: Any) -> str:
    return str(value or "").replace("|", r"\|").replace("\n", " ")


def _link(url: str) -> str:
    if not url:
        return "—"
    return "[source](" + url.replace("\\", "").replace("(", "%28").replace(")", "%29") + ")"


_TABLE_HEAD = ("| # | Title | DOI | Date | Line | Link | Mentions |", "|---:|---|---|---|---:|---|---:|")


def _rows(papers: list[dict[str, Any]]) -> list[str]:
    return [
        f"| {i} | {_cell(p['title'])} | {_cell(p['doi']) or '—'} | {p['date'] or '—'} | {p['line']} | {_link(p['url'])} | {len(p['occurrences'])} |"
        for i, p in enumerate(papers, start=1)
    ]


def report(source: str, extracted: int, papers: list[dict[str, Any]]) -> str:
    """The Markdown report the old command wrote."""
    missing = [p for p in papers if not p["found"]]
    recovered = [p for p in papers if p["recovered"]]
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Missing papers report", "",
        f"- Generated: {generated}",
        f"- Source: `{source}`",
        f"- Extracted entries: {extracted}",
        f"- Unique papers checked: {len(papers)}",
        f"- Missing: {len(missing)}",
        f"- Found by title only (DOI not in library): {len(recovered)}", "",
    ]
    if not missing:
        lines += ["Every paper in the log is in the library.", ""]
    else:
        lines += ["## Missing", "", *_TABLE_HEAD, *_rows(missing), ""]
    if recovered:
        lines += [
            "## Found by title only", "",
            "The DOI the log carries is not in the library, but the title matched. Usually a preprint DOI where the "
            "library holds the journal version -- worth a glance.", "",
            *_TABLE_HEAD, *_rows(recovered), "",
        ]
    return "\n".join(lines)


def run(text: str, source: str, match: Callable[[str, str], tuple[Any, str]] | None) -> dict[str, Any]:
    """The whole check on a log's text. match None is "list only": what the
    parser extracted, unchecked."""
    extracted, lines = extract(text)
    papers = deduplicate(extracted)
    for paper in papers:
        paper["mentions"] = len(paper["occurrences"])
    out: dict[str, Any] = {"source": source, "lines": lines, "extracted": len(extracted), "unique": len(papers)}
    if match is None:
        out["papers"] = papers
        return out
    check(papers, match)
    out["papers"] = papers
    out["missing"] = sum(1 for p in papers if not p["found"])
    out["recovered"] = sum(1 for p in papers if p["recovered"])
    out["report"] = report(source, len(extracted), papers)
    return out
