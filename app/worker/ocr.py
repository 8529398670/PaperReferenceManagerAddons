"""OCR for PDFs whose own text layer is missing or unreadable.

Two calls:

  needs_ocr(text, pages)   pure: is the text a PDF's own text layer gave
                           usable, or is it empty, too thin per page, or the
                           garbage a font without a ToUnicode map produces?
  ocr_pdf(pdf_path)        RapidOCR on every page rendered at 300 DPI, the
                           pages joined with a blank line.

The text-quality tests (normalize_text, is_garbled, looks_unspaced,
embedded_ok) are the old app's per-box gates from src/pdf/ocr.py, kept with
their thresholds; figures.py uses them to judge a caption's text-layer string.
RapidOCR often misses the narrow spaces of small type ('Thefoundationis'),
so lines that look run together are re-spaced with wordninja when it is
installed, as the old app did. The old deskew step is not ported: it needed
OpenCV and the `deskew` package, and RapidOCR's detector copes with the
slight skew of a scanned page on its own.

Heavy packages (pypdfium2, numpy, rapidocr) are imported inside the functions
that need them, so this module imports in the main app's venv too and the
pure parts can be tested there.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

# 300 is where OCR accuracy stops improving; higher only burns CPU.
OCR_DPI = 300

# Trust a text-layer string only if it has enough characters and is not
# CID-without-ToUnicode garbage (private-use code points, replacement chars).
MIN_EMBEDDED_TEXT = 8
MAX_GARBLED_BAD_RATIO = 0.05
MIN_GARBLED_LETTER_RATIO = 0.20

# Strings shorter than MIN_EMBEDDED_TEXT ('(1)', 'Methods', 'Fig. 2') fail
# the letter-ratio test, so trust them when they are plain label characters.
_SHORT_LABEL_RE = re.compile(
    r"^[A-Za-z0-9 ().,:;\[\]\-–]*[A-Za-z0-9][A-Za-z0-9 ().,:;\[\]\-–]*$"
)

# Text that lost its word spacing ('furthertechnicaladvantageof') reads as a
# few very long tokens.
STUCK_WORD_AVG_LEN_THRESHOLD = 12.0
STUCK_WORD_LONG_FRACTION = 0.15
STUCK_WORD_LONG_LEN = 18

# Below this many characters an OCR result is noise read off the background.
MIN_OCR_TEXT = 4

# A whole document's text layer: fewer characters than this per page on
# average means the pages are scans with at most a stray header in text.
# A real text page holds 2000-5000; a figure-heavy page still a few hundred.
MIN_CHARS_PER_PAGE = 200

# pdfminer-style '(cid:12)' tokens: a font with no Unicode map, spelled out.
_CID_RE = re.compile(r"\(cid:\d+\)")
MAX_CID_FRACTION = 0.02

_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft",
}
_FANCY_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}
_SOFT_HYPHEN = "­"
_NB_HYPHEN = "‑"


# ---------------------------------------------------------------------------
# Text quality (pure)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Unicode-normalize, undo ligatures and curly quotes, drop control
    characters, collapse runs of spaces and of blank lines."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    for k, v in _FANCY_QUOTES.items():
        text = text.replace(k, v)
    text = text.replace(_SOFT_HYPHEN, "").replace(_NB_HYPHEN, "-")
    text = "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C"
    )
    out: list[str] = []
    prev_blank = False
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        out.append(line)
    return "\n".join(out).strip()


def is_garbled(text: str) -> bool:
    """True when the text is dense in private-use, replacement or control
    characters (a font with no Unicode map), or has too few real letters to
    be prose."""
    if not text:
        return False
    n = len(text)
    bad = letters = 0
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF or cp == 0xFFFD or 0xD800 <= cp <= 0xDFFF:
            bad += 1
            continue
        if cp < 0x20 and ch not in "\t\n\r":
            bad += 1
            continue
        if ch.isalpha():
            letters += 1
    if bad / n > MAX_GARBLED_BAD_RATIO:
        return True
    return letters / n < MIN_GARBLED_LETTER_RATIO


def looks_unspaced(text: str) -> bool:
    """True when word boundaries look collapsed: long average tokens, or a
    large share of very long ones."""
    tokens = text.split()
    if len(tokens) < 4:
        return False
    if sum(len(t) for t in tokens) / len(tokens) > STUCK_WORD_AVG_LEN_THRESHOLD:
        return True
    long_n = sum(1 for t in tokens if len(t) > STUCK_WORD_LONG_LEN)
    return long_n / len(tokens) > STUCK_WORD_LONG_FRACTION


def embedded_ok(text: str) -> bool:
    """Is a short text-layer string (one box's worth) good enough to skip OCR?"""
    text = (text or "").strip()
    if len(text) < MIN_EMBEDDED_TEXT:
        return bool(_SHORT_LABEL_RE.match(text))
    return not is_garbled(text) and not looks_unspaced(text)


def needs_ocr(text: str, pages: int | None = None) -> bool:
    """Should this PDF be OCR'd, judging by the text its own text layer gave?

    Yes when the text is empty, when it is garbage (private-use glyphs,
    '(cid:N)' tokens, almost no letters, or words run together), or, when the
    page count is known, when there is too little of it per page to be more
    than a scan's running header."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    tokens = stripped.split()
    if tokens and len(_CID_RE.findall(stripped)) / len(tokens) > MAX_CID_FRACTION:
        return True
    if is_garbled(stripped) or looks_unspaced(stripped):
        return True
    if pages and pages > 0:
        # Count visible characters only: whitespace padding is not text.
        visible = len(re.sub(r"\s+", "", stripped))
        if visible / pages < MIN_CHARS_PER_PAGE:
            return True
    return False


# ---------------------------------------------------------------------------
# Words run together (RapidOCR misses narrow spaces in small type)
# ---------------------------------------------------------------------------

# Only tokens at least this long are candidates for splitting: shorter ones
# are real words far more often than run-together ones.
STUCK_WORD_MIN_LEN = 13
# A token longer than this is no English word ('neuroprognostication' is 20),
# so a line holding one has lost its spaces.
STUCK_LINE_TOKEN_LEN = 24

_WORDNINJA: Any = None


def _wordninja() -> Any:
    """wordninja, or False when it is not installed (splitting is then skipped)."""
    global _WORDNINJA
    if _WORDNINJA is None:
        try:
            import wordninja
            _WORDNINJA = wordninja
        except ImportError:
            _WORDNINJA = False
    return _WORDNINJA


def split_stuck_token(token: str, splitter: Any = None) -> list[str]:
    """'furthertechnicaladvantage' -> ['further', 'technical', 'advantage'],
    keeping the token's own capitals. Leaves alone anything short, anything
    not purely letters inside its punctuation, CamelCase that is short enough
    to be a name ('BrainVoyager'), and a split into stray letters.
    `splitter(str) -> list[str]` defaults to wordninja.split."""
    if len(token) < STUCK_WORD_MIN_LEN:
        return [token]
    if splitter is None:
        wn = _wordninja()
        if not wn:
            return [token]
        splitter = wn.split
    prefix, suffix, inner = "", "", token
    while inner and not inner[0].isalpha():
        prefix, inner = prefix + inner[0], inner[1:]
    while inner and not inner[-1].isalpha():
        suffix, inner = inner[-1] + suffix, inner[:-1]
    if len(inner) < STUCK_WORD_MIN_LEN or not inner.isalpha():
        return [token]
    if len(inner) <= STUCK_LINE_TOKEN_LEN and any(c.isupper() for c in inner[1:]):
        return [token]
    try:
        parts = list(splitter(inner.lower()))
    except Exception:
        return [token]
    # One-letter pieces other than the words 'a' and 'i' mean it guessed.
    if (len(parts) < 2 or "".join(parts) != inner.lower()
            or any(len(p) <= 1 and p not in ("a", "i") for p in parts)):
        return [token]
    # Cut the original by the parts' lengths, so its capitals survive.
    out, at = [], 0
    for p in parts:
        out.append(inner[at:at + len(p)])
        at += len(p)
    out[0], out[-1] = prefix + out[0], out[-1] + suffix
    return out


def line_looks_stuck(line: str) -> bool:
    """One OCR line that lost its spaces: a token longer than any real word,
    or long tokens on average."""
    tokens = line.split()
    if not tokens:
        return False
    if any(len(t) > STUCK_LINE_TOKEN_LEN for t in tokens):
        return True
    return sum(len(t) for t in tokens) / len(tokens) > STUCK_WORD_AVG_LEN_THRESHOLD


def split_stuck_words(text: str, splitter: Any = None) -> str:
    """Re-space the lines that look run together; other lines are untouched,
    so a real long word in good text is never cut."""
    out = []
    for line in text.split("\n"):
        if line_looks_stuck(line):
            words: list[str] = []
            for tok in line.split():
                words.extend(split_stuck_token(tok, splitter))
            line = " ".join(words)
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Reading order of OCR lines (pure)
# ---------------------------------------------------------------------------

def order_lines(lines: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    """Put a page's OCR lines into reading order.

    Each line is {'bbox': (x1, y1, x2, y2), 'text': str}. Sorting by y alone
    interleaves the two columns of a journal page line by line, so: walk the
    lines top to bottom; a line that crosses the page's middle (a title, a
    full-width figure caption) is a band of its own, and between two such
    bands the left column is read before the right one. A one-column page has
    every line crossing the middle and comes out in plain y order."""
    if not lines:
        return []
    mid = page_width / 2.0
    ordered: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []

    def flush() -> None:
        ordered.extend(sorted(left, key=lambda l: (l["bbox"][1], l["bbox"][0])))
        ordered.extend(sorted(right, key=lambda l: (l["bbox"][1], l["bbox"][0])))
        left.clear()
        right.clear()

    for line in sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0])):
        x1, _, x2, _ = line["bbox"]
        if x1 < mid < x2:
            flush()
            ordered.append(line)
        elif (x1 + x2) / 2.0 < mid:
            left.append(line)
        else:
            right.append(line)
    flush()
    return ordered


def polygon_to_bbox(polygon: Any) -> Optional[tuple[float, float, float, float]]:
    """A 4-point polygon [[x, y], ...] as an axis-aligned (x1, y1, x2, y2)."""
    try:
        xs = [float(pt[0]) for pt in polygon]
        ys = [float(pt[1]) for pt in polygon]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# RapidOCR (lazy, once per process)
# ---------------------------------------------------------------------------

_RAPID: Any = None


def get_rapid() -> Any:
    """The process's RapidOCR engine, built on first use. Raises ImportError
    when rapidocr is not installed."""
    global _RAPID
    if _RAPID is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR  # the newer package name
        # It logs every call at INFO; the worker only wants problems.
        for name in ("RapidOCR", "rapidocr", "rapidocr_onnxruntime"):
            logging.getLogger(name).setLevel(logging.WARNING)
        _RAPID = RapidOCR()
    return _RAPID


def rapid_available() -> bool:
    """True when a RapidOCR package is importable (without loading it)."""
    import importlib.util
    return any(
        importlib.util.find_spec(name) is not None
        for name in ("rapidocr_onnxruntime", "rapidocr")
    )


def ocr_image(image: Any) -> list[dict[str, Any]]:
    """RapidOCR on one PIL image: [{'bbox': (x1, y1, x2, y2), 'text': str}]
    in the image's pixel coordinates."""
    import numpy as np

    result, _elapsed = get_rapid()(np.array(image.convert("RGB")))
    out: list[dict[str, Any]] = []
    for item in result or []:
        if not item or len(item) < 2 or not item[1]:
            continue
        bbox = polygon_to_bbox(item[0])
        if bbox is not None:
            out.append({"bbox": bbox, "text": str(item[1])})
    return out


def ocr_text(image: Any) -> str:
    """The text of one PIL image in reading order, or '' for noise."""
    lines = order_lines(ocr_image(image), image.width)
    text = normalize_text("\n".join(l["text"] for l in lines))
    if len(text) < MIN_OCR_TEXT:
        return ""
    return split_stuck_words(text)


def text_layer(pdf_path: Path, max_pages: int = 200) -> tuple[str, int]:
    """The PDF's own text and its page count, as pdfium reads them; ('', 0)
    when it cannot be opened. needs_ocr says whether the text will do."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception:  # noqa: BLE001 -- a broken PDF: let OCR have its go and fail properly
        return "", 0
    try:
        pages = len(pdf)
        texts: list[str] = []
        for idx in range(min(pages, max_pages)):
            page = pdf[idx]
            try:
                textpage = page.get_textpage()
                try:
                    texts.append(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
        return normalize_text("\n\n".join(texts)), min(pages, max_pages)
    finally:
        pdf.close()


def ocr_pdf(pdf_path: Path, max_pages: int = 200) -> str:
    """OCR the first max_pages pages of a PDF at 300 DPI. Pages are joined
    with a blank line; a page with nothing readable contributes ''. Raises
    when the PDF cannot be opened or RapidOCR is not installed."""
    import pypdfium2 as pdfium

    get_rapid()  # fail before rendering anything if the engine is missing
    scale = OCR_DPI / 72.0  # 72 points to the inch
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        texts: list[str] = []
        for idx in range(min(len(pdf), max_pages)):
            page = pdf[idx]
            try:
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert("RGB")
                bitmap.close()
            finally:
                page.close()
            texts.append(ocr_text(image))
        return "\n\n".join(texts)
    finally:
        pdf.close()
