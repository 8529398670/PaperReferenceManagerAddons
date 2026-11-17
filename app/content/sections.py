"""Sections of a paper, from Zotero's extracted text alone.

Zotero's `.zotero-ft-cache` is plain text with line breaks and no layout: no
boxes, no fonts, no reading order beyond the order PDF.js emitted. So where
the old pipeline classified YOLO "title" detections as section anchors, here a
LINE is a heading candidate when it is short, looks like a heading, and
classifies as a section keyword. The keyword table, the numbering-prefix
strip, the caption test, the reference-entry patterns and the anchor state
machine are the old ones (prma src/pdf/preprocess.py), re-applied to lines.

The state machine, as before:
  - text before the first anchor is front matter ("front": banner, title,
    authors, affiliations -- and the abstract, when it has no heading);
  - everything after an anchor inherits its key until the next anchor, so a
    numbered subsection the table does not know ("2.2 Stimuli") stays in
    Methods instead of falling out of it;
  - figure / table captions are routed aside to "figures" / "tables" and the
    section they interrupted resumes after them;
  - when there is no References heading at all, a trailing run of
    reference-shaped paragraphs is reclassified as "references".

Keys: front, abstract, introduction, background, methods, results,
discussion, conclusion, future, other (back matter: acknowledgements,
funding, data availability, appendix, ...), references, figures, tables.
"""
from __future__ import annotations

import re
from collections import Counter

# Section-header keyword patterns. Tested in order; the first match wins.
# Ordered most-specific first so "results and discussion" maps to results
# rather than to discussion. Two changes from the old table: "discussion" has
# its own key (the old bucket list had none, so it folded into results), and
# back matter gets "other" -- it ends the section before it (a Data
# availability statement is not Methods), which the old YOLO flow got from
# the page layout for free.
SECTION_HEADER_PATTERNS = (
    ("references", r"^(references?|bibliography|literature\s+cited|works?\s+cited|reference\s+list)\b"),
    (
        "other",
        r"^(acknowledge?ments?|funding(\s+(information|sources?))?|author\s+contributions?|"
        r"(declaration\s+of\s+)?(competing|conflicts?\s+of)\s+interests?|declarations?|"
        r"(data|code|data\s+and\s+code|software)\s+availability(\s+statement)?|"
        r"supplementary\s+(materials?|information|data)|supporting\s+information|appendix|"
        r"ethics(\s+statement)?)\b",
    ),
    ("future", r"^(future\s+(work|directions?|research|prospects?)|limitations?(\s+and\s+future)?)\b"),
    ("conclusion", r"^(conclusions?|concluding\s+remarks|summary\s+and\s+conclusions?)\b"),
    ("results", r"^(results?(\s+and\s+discussion)?|findings?)\b"),
    ("discussion", r"^((general\s+)?discussion)\b"),
    (
        "methods",
        r"^(methods?|methodology|materials?\s+(and|&)\s+methods?|patients?\s+(and|&)\s+methods?|"
        r"experimental(\s+(methods?|design|procedures?))?|study\s+design|participants?|procedures?|"
        r"data\s+collection|data\s+analysis|statistical\s+analysis)\b",
    ),
    ("background", r"^(background|related\s+work|prior\s+work|literature\s+review|prior\s+art)\b"),
    ("introduction", r"^(introduction)\b"),
    ("abstract", r"^(abstract|summary)\b"),
)

_COMPILED_HEADERS = tuple((name, re.compile(pat, re.IGNORECASE)) for name, pat in SECTION_HEADER_PATTERNS)

# Strip a leading "1." / "1.2" / "III." / "A." numbering prefix from a header
# line before matching keywords. The old pattern, ^[\divxlcDIVXLC]{1,5}..., had
# no boundary after the prefix, so it ate the first letters of real headings:
# "Discussion" -> "scussion", "Introduction" -> "ntroduction", "Conclusions"
# -> "onclusions", and none of those ever matched. The prefix must now be
# followed by whitespace or the end of the line, and a lone letter needs its
# dot ("A. Participants", never the "A" of "A study").
_HEADER_PREFIX_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3})*\.?|[IVXLC]{1,5}\.?|[ivxlc]{1,5}\.|[A-Z]\.)(?=\s|$)\s*")

# A real figure / table caption starts with "Figure" / "Fig" / "Table" and a
# number. In plain text every paragraph is a candidate (there is no YOLO class
# to pre-filter), so the number must be followed by caption punctuation or a
# capitalised word: "Figure 2. Overview" is a caption, "Figure 2 shows" is prose.
_FIGURE_CAPTION_RE = re.compile(r"^\s*(figure|figures|fig|figs)\.?\s*\d+[a-z]?\s*(?:[.:|—–-]|\s+[A-Z(])", re.IGNORECASE)
_TABLE_CAPTION_RE = re.compile(r"^\s*table\.?\s*\d+[a-z]?\s*(?:[.:|—–-]|\s+[A-Z(])", re.IGNORECASE)

# Patterns that recognise reference / bibliography entries when no
# "References" heading was found. ANY of them on a paragraph is evidence, and
# we walk from the tail backwards while the run stays reference-ish.
_REFERENCE_PATTERNS = (
    re.compile(r"\bet\s+al\.?\b", re.IGNORECASE),  # author lists
    re.compile(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)"),  # (2024), (1999a)
    re.compile(r"\bdoi[\.:]?\s*10\.", re.IGNORECASE),  # 'doi:10.xxxx'
    re.compile(r"10\.\d{4,}/\S+"),  # bare DOI
    re.compile(r"^\s*\[\s*\d+\s*\]"),  # [1] -style
    re.compile(r"^\s*\d{1,3}\.\s+[A-Z]"),  # 1. Author, ...
)
# A YOLO block was one entry, so "et al." alone was enough. A plain-text
# paragraph of discussion prose says "Smith et al. (2019)" all the time, so
# here the weak patterns (et al., a year in parens) only count when the
# paragraph STARTS like an entry: a number, a bracket, or "Surname, I." /
# "Surname I," -- the strong ones (a DOI) count anywhere.
_ENTRY_START_RE = re.compile(r"^\s*(?:\[\s*\d+\s*\]|\d{1,3}\.\s+[A-Z]|[A-Z][\w'’-]+,?\s+(?:[A-Z]\.|[A-Z]{1,3}[,.]))")
_STRONG_REFERENCE = (_REFERENCE_PATTERNS[2], _REFERENCE_PATTERNS[3])

# Run-in headings ("Abstract—Facing the prevalence ...", "Abstract: ...") are
# only honoured for the abstract. A structured abstract is full of
# "Methods: ..." / "Results: ..." run-ins, and splitting those out would carve
# the abstract into fake Methods and Results sections.
_RUN_IN_RE = re.compile(r"^\s*(abstract)\s*(?:[—–:]|-{1,2}|\.\s)\s*(\S.*)$", re.IGNORECASE)
_ALLCAPS_RUN_IN_RE = re.compile(r"^\s*(ABSTRACT)\s+(\S.*)$")

# A heading line is short. Anything longer is prose that happens to start
# with "Results ..." or "Participants ...".
MAX_HEADING_CHARS = 80
MAX_HEADING_WORDS = 10

# Lines that are page furniture rather than reading flow (the old pipeline
# dropped YOLO 'abandon' boxes): bare page numbers, and short lines repeated on
# many pages -- running heads like "4046 IEEE TRANSACTIONS ..." once digits are
# folded away.
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")
RUNNING_HEAD_MIN_REPEATS = 3
RUNNING_HEAD_MAX_CHARS = 150

_SENTENCE_END_RE = re.compile(r"[.!?:][\"'”’)\]]*$")
_URLISH_RE = re.compile(r"(?i)(?:https?://|www\.|\w\.(?:com|org|io|net|edu|gov|eu|co|ca|uk)/)\S*$")


def _first_line(text: str) -> str:
    if not text:
        return ""
    return text.strip().split("\n", 1)[0].strip()


def classify_header(text: str) -> str | None:
    """The section key a heading names, or None. Strips a leading "1." /
    "III." style prefix before matching the keyword patterns."""
    first = _first_line(text)
    if not first:
        return None
    cleaned = _HEADER_PREFIX_RE.sub("", first).strip()
    if not cleaned:
        return None
    for name, rx in _COMPILED_HEADERS:
        if rx.match(cleaned):
            return name
    return None


def _is_numbered(line: str) -> bool:
    return bool(_HEADER_PREFIX_RE.match(line.strip()))


def _looks_like_heading_line(line: str) -> bool:
    """Short, not ending mid-sentence, and set like a heading. A heading
    either IS the keyword ("Methods", "Materials and Methods"), or is
    numbered, Title Cased or ALL CAPS ("Data Analysis and Statistics"), or
    continues the keyword with "and ..." ("Study design and participants").
    That is what keeps "Participants were 20 adults" in the prose."""
    s = line.strip()
    if not s or len(s) > MAX_HEADING_CHARS or len(s.split()) > MAX_HEADING_WORDS:
        return False
    if s[-1] in ",;-" or s.endswith(" and"):
        return False
    cleaned = _HEADER_PREFIX_RE.sub("", s).strip()
    if not cleaned:
        return False
    if _is_numbered(s):
        return not cleaned.endswith(".") or len(cleaned.split()) <= 4
    for _, rx in _COMPILED_HEADERS:
        m = rx.match(cleaned)
        if not m:
            continue
        rest = cleaned[m.end():].strip(" .:")
        if not rest:
            return True
        if cleaned.endswith("."):
            return False
        if cleaned.isupper():
            return True
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", cleaned) if len(w) > 3]
        if words and all(w[0].isupper() for w in words):
            return True
        return bool(re.match(r"(?i)^(and|&|,)\s", rest)) and len(cleaned.split()) <= 6
    return False


def _heading(line: str) -> tuple[str, str, str] | None:
    """(key, heading, run-in text) when `line` is a section heading."""
    s = line.strip()
    m = _RUN_IN_RE.match(s) or _ALLCAPS_RUN_IN_RE.match(s)
    if m and len(m.group(2)) > 20:
        return "abstract", m.group(1), m.group(2).strip()
    if not _looks_like_heading_line(s):
        return None
    key = classify_header(s)
    if key is None:
        return None
    return key, s, ""


def _is_subheading(line: str) -> bool:
    """A numbered heading the keyword table doesn't know ("2.2 Stimuli"). It
    keeps the current key (old: a non-anchor title inherits), but it must not
    be glued onto the first line of the paragraph under it."""
    s = line.strip()
    return _is_numbered(s) and _looks_like_heading_line(s) and not _SENTENCE_END_RE.search(s)


def _caption_kind(paragraph: str) -> str | None:
    first = _first_line(paragraph)
    if _FIGURE_CAPTION_RE.match(first):
        return "figures"
    if _TABLE_CAPTION_RE.match(first):
        return "tables"
    return None


def looks_like_reference(text: str) -> bool:
    """True if `text` reads like a bibliography entry (see _ENTRY_START_RE
    for why the weak patterns need an entry-shaped start in plain text)."""
    if not text:
        return False
    if any(rx.search(text) for rx in _STRONG_REFERENCE):
        return True
    if not _ENTRY_START_RE.match(text):
        return False
    return any(rx.search(text) for rx in _REFERENCE_PATTERNS)


def _furniture(lines: list[str]) -> set[int]:
    """Indexes of page-furniture lines: bare page numbers, and running heads
    (short lines that recur, digits folded so the page number can change).
    A recurring line that reads like a bibliography entry is kept: with its
    digits folded, "12. Smith, J. ... (2019)." can repeat by accident."""
    folded = [re.sub(r"\d+", "#", ln.strip().lower()) for ln in lines]
    counts = Counter(f for f in folded if f and len(f) <= RUNNING_HEAD_MAX_CHARS)
    out = set()
    for i, ln in enumerate(lines):
        if _PAGE_NUMBER_RE.match(ln):
            out.add(i)
        elif (
            folded[i]
            and counts.get(folded[i], 0) >= RUNNING_HEAD_MIN_REPEATS
            and classify_header(ln) is None
            and not looks_like_reference(ln)
        ):
            out.add(i)
    return out


def _join(paragraph: str, line: str) -> str:
    """Append a wrapped line to a paragraph. A word hyphenated at the break
    ("electroencephalo-" + "graphy") loses its hyphen; a URL keeps it and is
    glued without a space ("github.com/kelseyhan-" + "lab/repo"), as is a URL
    cut right after a slash -- the link scanner then sees the whole link."""
    if not paragraph:
        return line
    last = paragraph.rsplit(None, 1)[-1]
    urlish = bool(_URLISH_RE.search(last))
    if paragraph.endswith("-") and len(paragraph) > 1 and paragraph[-2].isalpha():
        if not urlish and line[:1].islower():
            return paragraph[:-1] + line
        return paragraph + line
    if urlish and paragraph.endswith("/"):
        return paragraph + line
    return paragraph + " " + line


def _paragraph_events(text: str) -> list[tuple[str, object]]:
    """The text as a stream of ("heading", (key, heading)) and
    ("para", str) events, furniture dropped and wrapped lines joined. A
    paragraph ends at a blank line, a heading, or a line ending a sentence."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    skip = _furniture(lines)
    events: list[tuple[str, object]] = []
    para = ""

    def flush() -> None:
        nonlocal para
        if para.strip():
            events.append(("para", para.strip()))
        para = ""

    for i, raw in enumerate(lines):
        if i in skip:
            continue
        line = raw.strip()
        if not line:
            flush()
            continue
        head = _heading(line)
        if head:
            flush()
            events.append(("heading", (head[0], head[1])))
            if head[2]:
                para = head[2]
                if _SENTENCE_END_RE.search(para):
                    flush()
            continue
        if _is_subheading(line) or _caption_kind(line) or (_ENTRY_START_RE.match(line) and looks_like_reference(line)):
            flush()
            if _is_subheading(line):
                events.append(("para", line))
                continue
        para = _join(para, line)
        if _SENTENCE_END_RE.search(line):
            flush()
    flush()
    return events


def split(text: str) -> list[dict]:
    """Split a paper's plain text into sections, in document order:
    [{"key", "heading", "text"}], text being paragraphs separated by "\\n\\n".
    Text before the first heading is key "front"."""
    segments: list[dict] = [{"key": "front", "heading": "", "paras": []}]
    for kind, value in _paragraph_events(text):
        if kind == "heading":
            key, heading = value  # type: ignore[misc]
            segments.append({"key": key, "heading": heading, "paras": []})
            continue
        para = str(value)
        cap = _caption_kind(para)
        if cap:
            # Route the caption aside, then resume the section it interrupted.
            cur = segments[-1]
            segments.append({"key": cap, "heading": "", "paras": [para]})
            segments.append({"key": cur["key"], "heading": cur["heading"], "paras": [], "resumed": True})
            continue
        segments[-1]["paras"].append(para)

    _references_fallback(segments)

    out = []
    for seg in segments:
        if not seg["paras"] and (seg.get("resumed") or not seg["heading"]):
            continue
        if seg.get("resumed") and out and out[-1]["key"] == seg["key"] and out[-1]["heading"] == seg["heading"]:
            out[-1]["paras"].extend(seg["paras"])
            continue
        out.append(seg)
    return [{"key": s["key"], "heading": s["heading"], "text": "\n\n".join(s["paras"])} for s in out]


def _references_fallback(segments: list[dict]) -> None:
    """No References heading: walk back from the last paragraph while the run
    stays reference-like, allowing a couple of stray blocks (affiliations,
    copyright lines tucked between entries), and commit only when at least
    three paragraphs looked like entries. Mutates `segments` in place."""
    if any(s["key"] == "references" for s in segments):
        return
    flow = [(si, pi) for si, s in enumerate(segments) if s["key"] not in ("figures", "tables") for pi in range(len(s["paras"]))]
    n = len(flow)
    if n < 6:
        return
    ref_start, gap, gap_budget = n, 0, 2
    for i in range(n - 1, -1, -1):
        si, pi = flow[i]
        if looks_like_reference(segments[si]["paras"][pi]):
            ref_start, gap = i, 0
        else:
            gap += 1
            if gap > gap_budget:
                break
    ref_like = sum(1 for j in range(ref_start, n) if looks_like_reference(segments[flow[j][0]]["paras"][flow[j][1]]))
    if ref_like < 3:
        return
    si, pi = flow[ref_start]
    moved = segments[si]["paras"][pi:]
    del segments[si]["paras"][pi:]
    for later in segments[si + 1:]:
        if later["key"] not in ("figures", "tables"):
            moved.extend(later["paras"])
            later["paras"] = []
    segments.insert(si + 1, {"key": "references", "heading": "", "paras": moved})


def render(sections: list[dict]) -> str:
    """Sections back to one text: each heading, then its paragraphs."""
    parts = []
    for s in sections:
        if s.get("heading"):
            parts.append(s["heading"])
        if s.get("text"):
            parts.append(s["text"])
    return "\n\n".join(parts)


def methods_text(sections: list[dict]) -> str:
    """Every methods-classified section joined -- "Materials and Methods",
    "Experimental procedures", "Participants", "Statistical analysis", ...
    all land on key "methods" through SECTION_HEADER_PATTERNS."""
    return "\n\n".join(s["text"] for s in sections if s["key"] == "methods" and s["text"])


def cut_bibliography(text: str) -> str:
    """The paper up to its bibliography: a reference list is a list of OTHER
    papers' titles, and every one of them would score as evidence (a dataset,
    a modality). Cut at the first references section -- the heading, or the
    positional fallback -- and drop everything after it, as the old strip_refs
    did. Returns cleaned text (render of the sections before the cut)."""
    kept = []
    for s in split(text):
        if s["key"] == "references":
            break
        kept.append(s)
    return render(kept)
