"""Method figures: which figure captions describe a model DESIGN.

Ported from the old app's `prma method-images` caption matcher. The target is
the "here is our architecture" figure -- the pipeline, the layer stack, the
block diagram -- not the figures that merely evaluate a model (ROC curves,
accuracy bars). Keywords come from config/method-images.txt in two tiers,
because a caption that NAMES a model is not the same as one that DESCRIBES it:

  [strong]  structural vocabulary (architecture, block diagram, pipeline,
            encoder-decoder) -> one hit qualifies the caption on its own.
  [weak]    component / model-family vocabulary (transformer, layer, LSTM,
            attention) -> only counts when `min_weak` pieces of DISTINCT
            evidence land in one caption (see _distinct_evidence: one concept
            can't vote twice). "accuracy of our transformer" is a results
            plot; "encoder" + "block" + "LSTM" together is a design.

Terms before any [section] header are strong, so a flat list still works.

Fuzzy matching (rapidfuzz): single-word keywords take the best ratio against
the caption's TOKENS ('CNN' still hits 'CNNs', 'layer' hits 'layers'), never
against the inside of a longer word ('decoder' must not match 'autoencoder').
Keywords with a space or hyphen can't be a token, so they use a local
alignment (partial_ratio_alignment) over the whole caption, which must start
on a word boundary.

Everything here is a pure function over strings. It runs over the whole
library's captions (~17k) in one go, so the normalised keyword forms are
computed once, in Keywords, and each caption's tokens are bucketed by their
opening chars so a keyword is only scored against tokens that could match.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

THRESHOLD = 85
MIN_WEAK = 3

# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[\s*(strong|weak)\s*\]$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_MULTIWORD_RE = re.compile(r"[^a-z0-9]")
_ALNUM2_RE = re.compile(r"[a-z0-9]{2}")

# A keyword only matches a caption word that AGREES ON ITS FIRST CHARS. Without
# this, rapidfuzz's LCS-based ratio scores `decoder` vs `encoder` at 85.7 (they
# share 'ecoder') -- so every "encoder" caption sprouted a bogus 'decoder' hit,
# and two opposite concepts read as two independent votes. The fuzz is here to
# absorb inflections + OCR garble (layer/layers, CNN/CNNs), all of which agree
# on their opening chars.
_PREFIX_CHARS = 2


@dataclass(frozen=True)
class _Term:
    """One keyword, normalised once (not once per caption)."""
    kw: str          # as written in the file -- what the UI shows
    norm: str        # lowercased, whitespace-collapsed -- what is matched
    multi: bool      # has a space / hyphen -> alignment over the whole caption
    prefix: str      # the opening chars a matching caption word must share
    alnum_prefix: bool  # prefix is plain [a-z0-9]{2} -> usable as a quick pre-check


def _term(kw: str) -> _Term:
    k = _norm(kw)
    n = min(_PREFIX_CHARS, len(k))
    return _Term(kw, k, bool(_MULTIWORD_RE.search(k)), k[:n], bool(_ALNUM2_RE.fullmatch(k[:2])))


@dataclass(frozen=True)
class Keywords:
    strong: tuple[str, ...] = ()
    weak: tuple[str, ...] = ()
    # Short hash of the keyword file's bytes: a cached match result is stale
    # once this changes. "" when there was no file.
    signature: str = ""
    _strong: tuple[_Term, ...] = field(default=(), init=False, repr=False, compare=False)
    _weak: tuple[_Term, ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_strong", tuple(_term(k) for k in self.strong if _norm(k)))
        object.__setattr__(self, "_weak", tuple(_term(k) for k in self.weak if _norm(k)))


def _dedupe(terms: list[str], seen: set[str]) -> list[str]:
    """Drop case-insensitive repeats (across BOTH tiers -- a term listed strong
    then weak stays strong), keeping order and the original casing."""
    out = []
    for k in terms:
        lk = _norm(k)
        if not lk or lk in seen:
            continue
        seen.add(lk)
        out.append(k)
    return out


def parse_keywords(text: str, signature: str = "") -> Keywords:
    """The keyword file's text -> Keywords. One term per line, '#' comments and
    blank lines ignored, `[strong]` / `[weak]` headers switch tier."""
    buckets: dict[str, list[str]] = {"strong": [], "weak": []}
    tier = "strong"
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _SECTION_RE.match(s)
        if m:
            tier = m.group(1).lower()
            continue
        buckets[tier].append(s)
    seen: set[str] = set()
    strong = _dedupe(buckets["strong"], seen)
    weak = _dedupe(buckets["weak"], seen)
    return Keywords(tuple(strong), tuple(weak), signature)


def load_keywords(path: Path | str) -> Keywords:
    """Read config/method-images.txt (or another file). A missing file is an
    empty Keywords, which matches nothing."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return Keywords()
    return parse_keywords(raw.decode("utf-8"), hashlib.sha1(raw).hexdigest()[:12])


# ---------------------------------------------------------------------------
# Fuzzy caption matching
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return _SPACE_RE.sub(" ", (s or "").lower()).strip()


def _norm_with_map(caption: str) -> tuple[str, list[int]]:
    """_norm(caption) plus, for each char of it, the index in `caption` it came
    from -- so spans found in the normalised text can be handed back for
    highlighting the caption the user actually sees. Only built for captions
    that matched."""
    low = caption.lower()
    src: list[int] | None = None
    if len(low) != len(caption):
        # lower() never shortens a char, so equal lengths mean one char each and
        # the map is the identity. Otherwise some char grew ('İ' -> 'i̇'):
        # rebuild char by char, each piece mapping back to its source.
        chars: list[str] = []
        src = []
        for i, c in enumerate(caption):
            for lc in c.lower():
                chars.append(lc)
                src.append(i)
        low = "".join(chars)
    out: list[str] = []
    idx: list[int] = []
    for m in re.finditer(r"\S+", low):
        a, b = m.span()
        if out:
            out.append(" ")
            idx.append(a - 1 if src is None else src[a - 1])
        out.append(m.group(0))
        idx.extend(range(a, b) if src is None else src[a:b])
    return "".join(out), idx


def _prefix_ok(prefix: str, s: str) -> bool:
    return s[:len(prefix)] == prefix


def _tokens(cap: str) -> dict[str, list[str]]:
    """The caption's distinct words, bucketed by their opening 2 chars. A
    keyword only scores against words sharing its prefix (_prefix_ok), so its
    bucket is the whole candidate set. Words keep first-seen order, because the
    old scan kept the first of equally scoring words. Positions are looked up
    afterwards (_first_at), only for the words that actually hit."""
    buckets: dict[str, list[str]] = {}
    for tok in dict.fromkeys(_WORD_RE.findall(cap)):
        buckets.setdefault(tok[:2], []).append(tok)
    return buckets


def _first_at(cap: str, tok: str) -> tuple[int, int]:
    """Where `tok` first stands as a whole word in `cap`."""
    m = re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", cap)
    assert m is not None
    return m.start(), m.end()


def _score_terms(cap: str, buckets: dict[str, list[str]], terms: tuple[_Term, ...],
                 threshold: int, tier: str) -> list[dict[str, Any]]:
    """Fuzzy-match `terms` against one normalised caption. Returns
    {kw, score, tok, span, tier} for each term scoring >= threshold; `span` is
    where in `cap` it matched, which _distinct_evidence uses to tell
    independent evidence from the same word counted twice."""
    hits = []
    for t in terms:
        best, best_span = 0.0, None
        if not t.multi:
            # Only words agreeing on the prefix: the term's 2-char bucket (a
            # word shorter than the prefix can't agree). A 1-char term has no
            # bucket of its own, so it walks every bucket.
            if len(t.prefix) == _PREFIX_CHARS:
                cands = buckets.get(t.prefix, ())
            else:
                cands = [w for ws in buckets.values() for w in ws if w.startswith(t.prefix)]
            best_tok = ""
            for tok in cands:
                r = fuzz.ratio(t.norm, tok, score_cutoff=threshold)
                if r > best:
                    best, best_tok = r, tok
            if best_tok:
                best_span = _first_at(cap, best_tok)
        else:
            # The alignment must start on a word boundary with the term's
            # opening chars; a plain-alnum prefix that no caption word starts
            # with can't satisfy that, so skip the (costlier) alignment.
            if t.alnum_prefix and t.prefix not in buckets:
                continue
            al = fuzz.partial_ratio_alignment(t.norm, cap, score_cutoff=threshold)
            if al:
                ds = al.dest_start
                at_boundary = ds == 0 or not cap[ds - 1].isalnum()
                if at_boundary and _prefix_ok(t.prefix, cap[ds:ds + _PREFIX_CHARS]):
                    best, best_span = al.score, (ds, al.dest_end)
        if best >= threshold and best_span:
            hits.append({"kw": t.kw, "score": best, "tok": cap[best_span[0]:best_span[1]], "span": best_span, "tier": tier})
    return hits


def _stem(s: str) -> str:
    """Crude plural strip, enough to see 'blocks' and 'block' as one word."""
    out = []
    for w in (s or "").split():
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return " ".join(out)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _distinct_evidence(hits: list[dict[str, Any]]) -> int:
    """How many INDEPENDENT things in the caption did these hits find?

    Two hits are the SAME evidence when they either land on overlapping text
    ('attention' + 'self-attention' + 'attention mechanism' all firing on "self
    attention mechanism") or name the same word ('block' + 'blocks', even when
    the caption says each in a different sentence). Without both rules a single
    concept votes two or three times and trivially clears min_weak -- which is
    how "Results for vowel production task" got in on [block, blocks]."""
    units: list[dict[str, Any]] = []
    for h in hits:
        stem, span = _stem(h["tok"]), h["span"]
        home = None
        for u in units:
            if u.get("dead"):
                continue
            if stem in u["stems"] or any(_overlaps(span, s) for s in u["spans"]):
                if home is None:
                    u["spans"].append(span)
                    u["stems"].add(stem)
                    home = u
                else:
                    # This hit bridges two existing units -> fold them together.
                    home["spans"].extend(u["spans"])
                    home["stems"] |= u["stems"]
                    u["dead"] = True
        if home is None:
            units.append({"spans": [span], "stems": {stem}})
    return sum(1 for u in units if not u.get("dead"))


# "Figure 3 |" / "Fig. 2." / "Supplementary Figure 4:" -- stripped before we
# measure WHERE in a caption a term appeared, so the label doesn't count.
_FIG_LABEL_RE = re.compile(
    r"^\s*(?:supplementary\s+|extended\s+data\s+)?"
    r"(?:e?fig(?:ure)?s?\.?\s*[a-z]?\d+\s*[.:|)]?\s*)", re.IGNORECASE,
)

# A structural term this far into the caption body still describes the figure
# ("Schematic of the proposed GCN workflow..."). Later than this it's usually
# an aside in a results caption ("...the same architecture but only
# pre-trained") -- measured on the old library, a late strong term was ~54%
# results-plot language vs ~28% for an early one. This RANKS (the `lead` flag)
# rather than filters, so a design figure that buries the word still matches.
_LEAD_CHARS = 90


def _leads_with_structure(cap: str, hits: list[dict[str, Any]]) -> bool:
    """True when a strong (structural) term appears in the caption's opening --
    the figure IS the architecture / pipeline, rather than mentioning one on its
    way to reporting a score. `cap` is the normalised caption."""
    starts = [h["span"][0] for h in hits if h["tier"] == "strong"]
    if not starts:
        return False
    label_len = len(cap) - len(_FIG_LABEL_RE.sub("", cap))
    return (min(starts) - label_len) <= _LEAD_CHARS


def match(caption: str, kw: Keywords, threshold: int = THRESHOLD, min_weak: int = MIN_WEAK) -> dict[str, Any] | None:
    """Decide whether one caption describes a model DESIGN, and why.

    It qualifies on ANY strong term, or on at least `min_weak` pieces of
    distinct weak evidence. Returns None when it doesn't; otherwise
      score   the best single hit's score
      terms   every matched keyword (strong first, so the reason leads)
      strong  whether a strong term matched
      lead    a strong term sits in the caption's opening (an overview figure)
      spans   merged [start, end] ranges into `caption` itself, for highlighting
    """
    cap = _norm(caption)
    if not cap:
        return None
    buckets = _tokens(cap)
    s_hits = _score_terms(cap, buckets, kw._strong, threshold, "strong")
    # Weak terms only decide a caption with no strong hit, but are still
    # reported (and highlighted) alongside a strong one.
    w_hits = _score_terms(cap, buckets, kw._weak, threshold, "weak")
    if not s_hits and _distinct_evidence(w_hits) < max(1, min_weak):
        return None
    hits = s_hits + w_hits
    return {
        "score": round(max(h["score"] for h in hits), 1),
        "terms": [h["kw"] for h in hits],
        "strong": bool(s_hits),
        "lead": _leads_with_structure(cap, hits),
        "spans": _original_spans(caption, cap, [h["span"] for h in hits]),
    }


def _original_spans(caption: str, cap: str, spans: list[tuple[int, int]]) -> list[list[int]]:
    """Spans in the normalised caption -> merged spans in the original one."""
    # Per-char lower() can differ from whole-string lower() only on a Greek
    # final sigma, which keeps the length, so the map lines up with `cap`.
    _, idx = _norm_with_map(caption)
    out: list[list[int]] = []
    for s, e in sorted(spans):
        a, b = idx[s], idx[e - 1] + 1
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def match_paper(figures: list[dict[str, Any]], kw: Keywords, threshold: int = THRESHOLD,
                min_weak: int = MIN_WEAK) -> dict[int, dict[str, Any]]:
    """{figure n: match} for the paper's figures whose caption qualifies."""
    out: dict[int, dict[str, Any]] = {}
    for f in figures:
        m = match(f.get("caption") or "", kw, threshold, min_weak)
        if m is not None:
            out[f["n"]] = m
    return out
