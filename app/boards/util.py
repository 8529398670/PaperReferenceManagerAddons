"""The two text helpers the ported board code calls utils.<name>: the same
DOI rules as the library (app/library/zotero.py), and the old app's title
normalisation, kept as it was so keys made there still match here."""
from __future__ import annotations

import re
import unicodedata

from app.library.zotero import normalize_doi

__all__ = ["normalize_doi", "normalize_title", "synth_key"]


def normalize_title(s: object) -> str:
    if not s:
        return ""
    value = unicodedata.normalize("NFKD", str(s)).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split()).strip()


def synth_key(s: object) -> str:
    """The key of a reference that is neither in the library nor carrying a
    DOI: stable, filename-safe, made from its title."""
    stem = re.sub(r"[^a-z0-9]+", "-", normalize_title(s or "")).strip("-")
    return "ref-" + (stem[:80] or "unknown")
