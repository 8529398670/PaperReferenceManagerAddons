"""Which modalities (fMRI, EEG, MEG, ...) a paper USED, from its own text.

The vocabulary is config/modalities.yaml, written in natural casing:

    modalities:
      - label: fMRI
        phrases: ["functional MRI", "functional magnetic resonance"]
      - label: EEG
        phrases: [electroencephalogra]
      - MEG

  label    both the display label (casing kept exactly) and the term searched
           for -- matched as a WHOLE WORD, case-insensitively, so "fMRI" finds
           fMRI / FMRI / fmri but "PET" can't fire inside "dataset". There is
           no second column to keep in sync.
  phrases  optional spelled-out forms, matched as substrings -- so a STEM like
           "electroencephalogra" covers -phy / -m / -phic in one go. A list, a
           bare string for one, or left off entirely.

Labels match as whole words rather than by edit distance ON PURPOSE: "fMRI"
and "MRI" are one character apart and would score ~86% on a fuzzy scorer, so
every structural-MRI paper would come back tagged fMRI. Case-insensitive +
whole-word is the loose-but-safe line.

If the file is missing or unreadable we fall back to DEFAULT (the same
vocabulary, inlined below) and say so ONCE -- a typo in a config file must not
take tagging down. The vocabulary's signature changes with the file, so a
paper tagged under an older vocabulary is recognisably stale and re-tags.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.content import sections

# The shipped vocabulary, and the fallback when config/modalities.yaml is
# missing or broken -- keep it in step with that file.
DEFAULT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fMRI", ("functional MRI", "functional magnetic resonance")),
    ("sMRI", ("structural MRI",)),
    ("rsMRI", ("resting state MRI",)),
    ("EEG", ("electroencephalogra",)),
    ("ECoG", ("electrocorticogra",)),
    ("fNIRS", ("functional near-infrared", "functional near infrared", "near-infrared spectroscopy")),
    ("MEG", ("magnetoencephalogra",)),
    ("PET", ("positron emission",)),
    ("EMG", ("electromyography",)),
)

# tag()'s bar for an abstract-but-no-Methods paper: how often the body must
# name its dominant modality before that counts as used.
BODY_MIN = 8

_WARNED: set[str] = set()


@dataclass
class Vocab:
    """A loaded vocabulary. `entries` keep the phrases as written; matching
    lowercases both sides, so nothing in the config needs pre-lowercasing."""

    labels: list[str]
    entries: list[tuple[str, tuple[str, ...]]]
    signature: str
    _compiled: list[tuple[str, re.Pattern[str], tuple[str, ...]]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._compiled = [
            (
                label,
                # The label IS the needle: whole word, case-insensitive.
                re.compile(r"\b" + re.escape(label.lower()) + r"\b", re.IGNORECASE),
                tuple(p.lower() for p in phrases),
            )
            for label, phrases in self.entries
        ]


def _normalize(entries: Any) -> list[tuple[str, tuple[str, ...]]]:
    """Turn whatever the config declared into [(label, phrases)]. Raises
    ValueError on a shape we can't read, so load_vocab can fall back."""
    if not isinstance(entries, (list, tuple)):
        raise ValueError("modalities must be a list")
    out: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for e in entries:
        if isinstance(e, str):  # "- MEG": label only
            label, phrases = e, ()
        elif isinstance(e, dict):
            label, phrases = e.get("label"), e.get("phrases") or ()
        elif isinstance(e, (list, tuple)) and len(e) in (1, 2):
            label, phrases = e[0], (e[1] if len(e) == 2 else ())
        else:
            raise ValueError(f"entry {e!r} is not a label or {{label, phrases}}")
        label = str(label or "").strip()
        if not label:
            raise ValueError(f"entry {e!r} has an empty label")
        if isinstance(phrases, str):  # a bare string, not a list
            phrases = (phrases,)
        if label in seen:
            raise ValueError(f"duplicate label {label!r}")
        seen.add(label)
        out.append((label, tuple(str(p).strip() for p in phrases if str(p).strip())))
    if not out:
        raise ValueError("modalities is empty")
    return out


def _signature(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def default_vocab() -> Vocab:
    """The built-in vocabulary, signed by its own canonical form."""
    entries = _normalize(DEFAULT)
    sig = _signature(json.dumps(entries, ensure_ascii=False).encode("utf-8"))
    return Vocab([label for label, _ in entries], entries, sig)


def load_vocab(path: Path) -> Vocab:
    """The vocabulary in `path` (config/modalities.yaml), or DEFAULT -- with
    one printed warning per path -- when the file is missing or unreadable.
    The signature is a short sha256 of the file's bytes, so any edit to the
    file (even a reorder) makes earlier tags stale."""
    path = Path(path)
    try:
        data = path.read_bytes()
        doc = yaml.safe_load(data) or {}
        entries = _normalize(doc.get("modalities") if isinstance(doc, dict) else None)
        return Vocab([label for label, _ in entries], entries, _signature(data))
    except Exception as e:
        key = str(path)
        if key not in _WARNED:
            _WARNED.add(key)
            print(f"modalities: could not read {path} ({e}); using the built-in vocabulary")
        return default_vocab()


def scan(vocab: Vocab, text: str) -> list[str]:
    """Labels whose whole-word label or any phrase appears in `text`, in vocab
    order. Lowercases `text` itself -- pass raw prose."""
    if not text:
        return []
    hay = text.lower()
    return [label for label, rx, phrases in vocab._compiled if rx.search(hay) or any(p in hay for p in phrases)]


def count(vocab: Vocab, text: str) -> dict[str, int]:
    """{label: occurrences}: scan() with a tally of the whole-word label plus
    every phrase hit. For callers that must weigh HOW MUCH a text talks about
    a modality, not just whether it ever does (a long body names everything
    it cites at least once)."""
    if not text:
        return {}
    hay = text.lower()
    out = {}
    for label, rx, phrases in vocab._compiled:
        n = len(rx.findall(hay)) + sum(hay.count(p) for p in phrases)
        if n:
            out[label] = n
    return out


def order(vocab: Vocab, found: Any) -> list[str]:
    """Matched labels in the vocabulary's order, so "fMRI, EEG" always reads
    the same regardless of which matched first."""
    found = set(found)
    return [label for label in vocab.labels if label in found]


def inferred(vocab: Vocab, abstract: str, methods: str, body: str) -> list[str]:
    """Last-resort modalities for a paper we are BLIND about: the title,
    abstract and Methods section named nothing. Reads the body with the
    bibliography cut (so it doesn't false-positive on every modality the paper
    merely cites). Evidence here is weaker -- callers mark it inferred.

    Returns [] when we DO have a Methods section: if it named no modality,
    that is an answer, not a gap, and the body would only add what the
    intro / discussion CITES. (Measured on the old library: inferring for such
    papers tagged a BCI ethics paper with all five modalities and a
    behavioural aphasia study with fMRI + PET.)

    One exception, for papers with an abstract but NO Methods section (often a
    preprint with nonstandard headings): an abstract that says "brain
    responses" and never "fMRI" is silence, not an answer. Those read the body
    too, but keep only the DOMINANT modality, and only when it is named at
    least BODY_MIN times -- a review that cites fMRI in passing doesn't
    qualify, and an EEG paper discussing fMRI loses to its own EEG count.
    (Measured 2026-10: 14 real fMRI papers recovered against 4 fMRI-heavy
    reviews.) With no abstract either, anything the body names counts."""
    if methods and methods.strip():
        return []
    hay = sections.cut_bibliography(body or "")
    if not hay:
        return []
    if abstract and abstract.strip():
        counts = count(vocab, hay)
        top = max(counts.values(), default=0)
        return order(vocab, {m for m, n in counts.items() if n >= BODY_MIN and n >= top})
    return order(vocab, scan(vocab, hay))


def tag(vocab: Vocab, title: str, abstract: str, methods: str, body: str) -> tuple[list[str], bool]:
    """(used, inferred) for one paper.

    First the title + abstract + isolated Methods section -- deliberately NOT
    the full text, whose reference list names every modality the paper merely
    cites. So a label here means the study itself used it, and reviews /
    theory papers correctly come back empty. The title is authoritative about
    the study and costs nothing ("... using fMRI"); it tags papers with no
    abstract. Only when that finds nothing does inferred() get a look.
    `used == []` is an answer, not a gap: plenty of papers use no modality."""
    found = set(scan(vocab, f"{abstract or ''} {methods or ''}")) | set(scan(vocab, title or ""))
    if found:
        return order(vocab, found), False
    used = inferred(vocab, abstract, methods, body)
    return used, bool(used)


def record_haystack(rec: dict) -> str:
    """Free-text blob for tagging a code / data record rather than a paper:
    a GitHub repo (full_name / description / topics / language / homepage /
    README) or an OSF node (title / description / tags / category / wiki)."""
    parts = [
        rec.get("full_name") or rec.get("title") or f"{rec.get('owner', '')}/{rec.get('repo', '')}",
        rec.get("description") or "",
        " ".join(rec.get("topics") or rec.get("tags") or []),
        rec.get("language") or "",
        rec.get("category") or "",
        rec.get("homepage") or "",
        rec.get("readme") or rec.get("wiki") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def record_modalities(vocab: Vocab, rec: dict | None) -> list[str]:
    """Modalities named by a fetched repo / node record; [] for a missing,
    errored or empty one."""
    if not rec or rec.get("status") != "ok":
        return []
    return scan(vocab, record_haystack(rec))
