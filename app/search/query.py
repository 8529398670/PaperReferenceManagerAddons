"""Folding text and reading a query: the rules every search here shares.
Ported from the old prma src/dashboard/index.py, so a query that found a paper
there finds it here.

Folding: lowercase, accents stripped, every run of anything that is not a
letter or digit becomes one space. "MindAlign: Decoding", "EEG–fMRI" and a
pasted "10.1002/(SICI)..." all reduce to plain words, on both sides of the
comparison.

The query grammar: words are ANDed; OR (any case) starts an alternative and
binds loosest; NOT or a leading - excludes the next term; "a phrase" is always
literal, so "fight or flight" searches those three words.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Sequence

_LETTER_MAP = str.maketrans(
    {
        "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
        "ß": "ss", "đ": "d", "Đ": "d", "ð": "d", "Ð": "d", "ł": "l", "Ł": "l",
        "þ": "th", "Þ": "th", "ı": "i",
    }
)
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_COMBINING_RE = re.compile("[̀-ͯ҃-҉᪰-᫿᷀-᷿⃐-⃰︠-︯]")
_NONASCII_RE = re.compile(r"[^\x00-\x7f]+")
_QUERY_TOKEN_RE = re.compile(r'(-)?"([^"]*)"|(\S+)')


def _fold_run(match: re.Match[str]) -> str:
    run = unicodedata.normalize("NFKD", match.group(0).translate(_LETTER_MAP))
    return _COMBINING_RE.sub("", run)


def fold(text: object) -> str:
    """Lowercase alphanumeric words joined by single spaces."""
    if not text:
        return ""
    value = str(text)
    if not value.isascii():
        value = _NONASCII_RE.sub(_fold_run, value)
    return _NONALNUM_RE.sub(" ", value.lower()).strip()


@dataclass
class Clause:
    """One OR-alternative: every pos term present, no neg term present."""

    pos: list[str] = field(default_factory=list)
    neg: list[str] = field(default_factory=list)


def parse(query: str) -> list[Clause]:
    query = (query or "").strip()
    if not query:
        return []
    clauses = [Clause()]
    pending_not = False
    for match in _QUERY_TOKEN_RE.finditer(query):
        dash, phrase, word = match.group(1), match.group(2), match.group(3)
        if phrase is not None:
            literal, negative = fold(phrase), bool(dash)
        else:
            op = word.upper()
            if op in ("AND", "OR", "NOT"):
                if op == "OR":
                    clauses.append(Clause())
                    pending_not = False
                elif op == "NOT":
                    pending_not = True
                continue
            if word.startswith("-") and len(word) > 1:
                literal, negative = fold(word[1:]), True
            else:
                literal, negative = fold(word), False
        if not literal:
            continue
        negative = negative or pending_not
        pending_not = False
        (clauses[-1].neg if negative else clauses[-1].pos).append(literal)
    return [clause for clause in clauses if clause.pos or clause.neg]


def terms_of(clauses: Sequence[Clause]) -> list[str]:
    return sorted({term for clause in clauses for term in clause.pos})


# -- relevance ----------------------------------------------------------------
#
# Matching says whether a paper contains your words; this says how much it
# looks like the paper you asked for. The query as the title outranks the
# query buried on page 9 of a much-cited paper.


def relevance(title: str, head: str, in_body: bool, terms: Sequence[str], phrase: str) -> int:
    """title and head are folded (head: title + abstract); in_body says the
    whole phrase appears in the full text."""
    score = 0
    if phrase:
        if title == phrase:
            score += 400
        elif phrase in title:
            score += 300
        if phrase in head:
            score += 90
        elif in_body:
            score += 60
    if terms:
        in_title = sum(1 for term in terms if term in title)
        score += 45 * in_title
        if in_title == len(terms):
            score += 200
        score += 12 * sum(1 for term in terms if term in head)
    return score


# -- title lookup -------------------------------------------------------------
#
# What the boards search with: you are fetching one paper you half remember.
# Titles only, nothing has to match exactly, closest first; a pasted DOI or key
# jumps straight to its paper.

TITLE_WIDTH = 400
TITLE_FLOOR = 45
TITLE_SEED = 60
TITLE_KEEP = 200
FUZZY_CUTOFF = 76
FUZZY_LIMIT = 40


def _term_credit(term: str, words: set[str], title: str, ratio: Callable[[str, str], float] | None) -> float:
    if term in words:
        return 1.0
    if term in title:
        return 0.6
    if ratio and len(term) > 3:
        for word in words:
            if abs(len(word) - len(term)) <= 3 and ratio(term, word) >= 82:
                return 0.8
    return 0.0


def title_score(q: str, terms: Sequence[str], title: str, ratio: Callable[[str, str], float] | None = None) -> float:
    if not title:
        return 0.0
    score = 0.0
    if title == q:
        score += 400
    elif q in title:
        score += 250 + 70 * (len(q) / len(title))
        if title.startswith(q):
            score += 40
    if terms:
        words = set(title.split())
        got = weight = 0.0
        for term in terms:
            got += _term_credit(term, words, title, ratio) * len(term)
            weight += len(term)
        cover = (got / weight) if weight else 0.0
        score += 220 * cover
        if cover >= 0.95:
            score += 90
    return score


def title_lookup(q: str, titles: Sequence[str], idents: Sequence[str]) -> tuple[list[tuple[int, int]], bool]:
    """(index, score) best first for the titles nearest the folded query q,
    and whether these are only the closest few rather than real matches."""
    from rapidfuzz import fuzz, process

    terms = q.split()
    words = sorted([w for w in terms if len(w) > 3] or terms, key=len, reverse=True)
    seed = {i: t for i, t in enumerate(titles) if any(w in t for w in words)} if words else None
    pool = seed if (seed is not None and len(seed) >= TITLE_SEED) else {i: t for i, t in enumerate(titles)}
    # A library is a few thousand titles, so every candidate is scored rather
    # than only the WRatio top few hundred (the old app's cut, made for a pool
    # of 150,000): a long title with a typo'd word never ranks high on WRatio
    # alone, and it is exactly the one being looked for.
    width = None if len(pool) <= 5000 else TITLE_WIDTH
    found = process.extract(q, pool, scorer=fuzz.WRatio, processor=None, limit=width, score_cutoff=TITLE_FLOOR)
    scores: dict[int, float] = {}
    for _, ratio, index in found:
        scores[index] = title_score(q, terms, titles[index], fuzz.ratio) + 3.0 * ratio
    if len(q) > 5:
        for index, ident in enumerate(idents):
            if q in ident:
                scores[index] = scores.get(index, 0.0) + 900
    if not scores:
        return [], False
    best = max(scores.values())
    floor = max(TITLE_KEEP, 0.4 * best)
    keep = [i for i, s in scores.items() if s >= floor]
    fuzzy = not keep
    if fuzzy:
        keep = sorted(scores, key=lambda i: scores[i], reverse=True)[:8]
    ranked = sorted(((i, int(scores[i])) for i in keep), key=lambda pair: pair[1], reverse=True)
    return ranked, fuzzy


def near_titles(q: str, titles: Sequence[str]) -> list[tuple[int, int]]:
    """The closest titles for a text query that matched nothing -- likelier a
    typo than an empty library."""
    if len(q) < 4:
        return []
    from rapidfuzz import fuzz, process

    found = process.extract(q, list(titles), scorer=fuzz.partial_ratio, processor=None, score_cutoff=FUZZY_CUTOFF, limit=FUZZY_LIMIT)
    return [(index, int(score)) for _, score, index in found]
