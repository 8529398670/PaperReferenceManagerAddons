"""Citations for a list's rows: the in-text one, "(Cunningham et al., 2021)",
and the full reference, rendered through a real CSL style file. Ported from
the old prma src/db/cite.py; the rules are its rules:

- Styles are the .csl files in config/citation-styles/, named by file name
  without the extension (what zotero.org/styles calls them).
- A DEPENDENT style (only a link to its "independent-parent") cannot be
  rendered by citeproc-py: it is listed, greyed out, naming the parent to
  download. A style with no <citation> is unusable too.
- A style id comes from browsers and list documents and names a file, so it
  is never joined onto a path: it must match an id the listing produced.
- Each paper is rendered ALONE, in its own bibliography, so two 2021 papers
  never come out 2021a / 2021b.
- No author and no editor -> no citation, never "(Anon, n.d.)".

Authors come from Zotero's creators (already split into first / last); the
row's own authors string is used, as a CSL literal, only for a paper that
is not in the library. Rendering costs a few ms a paper, so results are
memoised per (style, key, the paper's Zotero dateModified).
"""
from __future__ import annotations

import logging
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.core.config import CODE_ROOT

log = logging.getLogger(__name__)

STYLES_DIR = CODE_ROOT / "config" / "citation-styles"
DEFAULT_STYLE = "the-journal-of-neuroscience"
EMPTY = {"intext": "", "full": ""}
_NS = "{http://purl.org/net/xbiblio/csl}"
_PARTICLES = {"van", "von", "de", "del", "della", "der", "den", "da", "di", "du", "la", "le", "los", "dos", "bin", "ibn", "al", "ter", "ten", "op", "st"}
# Zotero item type -> CSL type, where it changes the rendering.
_CSL_TYPE = {
    "journalArticle": "article-journal",
    "preprint": "article",
    "bookSection": "chapter",
    "book": "book",
    "thesis": "thesis",
    "report": "report",
    "conferencePaper": "paper-conference",
    "dataset": "dataset",
    "encyclopediaArticle": "entry-encyclopedia",
}

_lock = threading.Lock()
_listing: tuple[float, list[dict[str, Any]]] | None = None
_styles: dict[str, tuple[float, Any]] = {}
_memo: dict[tuple[str, str, str], dict[str, str]] = {}
_MEMO_MAX = 20000


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _probe(path: Path) -> dict[str, Any]:
    """One .csl file -> what the picker shows, without parsing it as a style."""
    out = {"id": path.stem, "title": path.stem, "ok": False, "why": ""}
    try:
        root = ET.parse(path).getroot()
    except Exception as e:  # noqa: BLE001 - any unreadable file is just unusable
        out["why"] = f"not readable as XML ({e})"
        return out
    info = root.find(f"{_NS}info")
    if info is not None:
        out["title"] = _text(info.find(f"{_NS}title")) or path.stem
        for link in info.findall(f"{_NS}link"):
            if link.get("rel") == "independent-parent":
                parent = (link.get("href") or "").rstrip("/").rsplit("/", 1)[-1]
                out["parent"] = parent
                out["why"] = f"a dependent style: it only points to '{parent}'. Download that one from zotero.org/styles and pick it instead."
                return out
    if root.find(f"{_NS}citation") is None:
        out["why"] = "the file has no <citation> rules"
        return out
    out["ok"] = True
    return out


def list_styles() -> list[dict[str, Any]]:
    """Every style on disk, by title, usable or not (with the reason)."""
    global _listing
    try:
        token = STYLES_DIR.stat().st_mtime
    except OSError:
        return []
    with _lock:
        if _listing and _listing[0] == token:
            return _listing[1]
    found = sorted((_probe(p) for p in STYLES_DIR.glob("*.csl")), key=lambda s: s["title"].lower())
    with _lock:
        _listing = (token, found)
    return found


def usable() -> list[str]:
    return [s["id"] for s in list_styles() if s["ok"]]


def resolve_style(*wanted: str) -> str:
    """The first usable style among `wanted` (a list's own, then config's),
    else the bundled default, else the first usable one, else ""."""
    ok = usable()
    for name in wanted:
        name = str(name or "").strip()
        if name and "/" not in name and "\\" not in name and ".." not in name and name in ok:
            return name
    if DEFAULT_STYLE in ok:
        return DEFAULT_STYLE
    return ok[0] if ok else ""


def _load(style_id: str) -> Any:
    path = STYLES_DIR / f"{style_id}.csl"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    with _lock:
        hit = _styles.get(style_id)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        from citeproc import CitationStylesStyle

        style = CitationStylesStyle(str(path), validate=False)
    except Exception as e:  # noqa: BLE001
        log.warning("could not parse citation style %s: %s", style_id, e)
        return None
    with _lock:
        _styles[style_id] = (mtime, style)
    return style


def _split_name(display: str) -> tuple[str, str]:
    """'Jan van der Berg' -> ('van der Berg', 'Jan'). Only for a display name."""
    parts = str(display or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    cut = len(parts) - 1
    while cut > 1 and parts[cut - 1].lower().strip(".") in _PARTICLES:
        cut -= 1
    return " ".join(parts[cut:]), " ".join(parts[:cut])


def _name(first: str, last: str) -> dict[str, str] | None:
    first, last = (first or "").strip(), (last or "").strip()
    if last and not first:
        last, first = _split_name(last)
    if not (first or last):
        return None
    return {"family": last, "given": first} if first else {"family": last}


def csl_json(key: str, record: dict[str, Any] | None, row: dict[str, Any] | None = None) -> dict[str, Any]:
    """One paper -> the CSL-JSON reference. `record` is the Zotero record
    (None for a paper not in the library); `row` is the list row."""
    record = record or {}
    row = row or {}
    first = lambda *values: next((str(v).strip() for v in values if str(v or "").strip()), "")  # noqa: E731
    ref: dict[str, Any] = {"id": key, "type": _CSL_TYPE.get(record.get("type", ""), "article-journal")}
    title = first(record.get("title"), row.get("title"))
    if title:
        ref["title"] = title
    creators = record.get("creators") or []
    authors = [n for c in creators if c.get("type") == "author" for n in [_name(c.get("first", ""), c.get("last", ""))] if n]
    editors = [n for c in creators if c.get("type") == "editor" for n in [_name(c.get("first", ""), c.get("last", ""))] if n]
    if authors:
        ref["author"] = authors
    elif editors:
        ref["editor"] = editors
    elif not record:
        raw = str(row.get("authors") or "").strip()
        if raw:
            ref["author"] = [{"literal": raw[:600]}]
    journal = first(record.get("journal"), row.get("journal"))
    if journal:
        ref["container-title"] = journal
    for field in ("volume", "issue", "page"):
        value = first(record.get(field))
        if value:
            ref[field] = value
    try:
        year = int(record.get("year") or row.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    if year:
        ref["issued"] = {"date-parts": [[year]]}
    doi = first(record.get("doi"), row.get("doi"))
    if doi:
        ref["DOI"] = doi
    return ref


def _flat(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return "".join(str(x) for x in value)
    except TypeError:
        return str(value)


def _render(style_id: str, ref: dict[str, Any]) -> dict[str, str]:
    if not (ref.get("author") or ref.get("editor")):
        return dict(EMPTY)
    style = _load(style_id)
    if style is None:
        return dict(EMPTY)
    try:
        from citeproc import Citation, CitationItem, CitationStylesBibliography, formatter
        from citeproc.source.json import CiteProcJSON

        bib = CitationStylesBibliography(style, CiteProcJSON([ref]), formatter.plain)
        citation = Citation([CitationItem(ref["id"])])
        bib.register(citation)
        intext = _flat(bib.cite(citation, lambda item: None)).strip()
        out = bib.bibliography()
        full = _flat(out[0]).strip() if out else ""
    except Exception as e:  # noqa: BLE001 - a broken render costs one row its citation
        log.warning("could not cite %s in %s: %s", ref.get("id"), style_id, e)
        return dict(EMPTY)
    return {"intext": re.sub(r"\s+", " ", intext), "full": re.sub(r"\s+", " ", full)}


def render(style_id: str, key: str, record: dict[str, Any] | None, row: dict[str, Any] | None = None) -> dict[str, str]:
    """{intext, full} for one paper in an already-resolved style. Never raises."""
    if not style_id:
        return dict(EMPTY)
    stamp = (record or {}).get("date_modified") or "row:" + "|".join(str((row or {}).get(k) or "") for k in ("title", "authors", "year", "journal", "doi"))
    memo_key = (style_id, key, stamp)
    with _lock:
        hit = _memo.get(memo_key)
    if hit is not None:
        return hit
    out = _render(style_id, csl_json(key, record, row))
    with _lock:
        if len(_memo) >= _MEMO_MAX:
            _memo.clear()
        _memo[memo_key] = out
    return out
