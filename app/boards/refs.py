"""Somebody else's bibliography, resolved against the library: the half of
the old server's _refs_payload that needs the catalogue. refparse.py does the
reading; this matches each reference so a row reaching a list carries the
key the rest of the app uses for that paper.

A DOI settles a match on its own; a title is matched only without one,
exactly or at rapidfuzz token_sort_ratio >= 96 (Catalogue.match). A
reference that matches nothing still comes back (in_library false, key
"ref-<title>" or its DOI), because the staging shelf is where a row you fix
by hand belongs. The missing pool joins the lookup in phase 4.
"""
from __future__ import annotations

from typing import Any

from app.boards import refparse, util
from app.library.catalogue import Catalogue


def resolve(catalogue: Catalogue, text: str) -> list[dict[str, Any]]:
    out = []
    for ref in refparse.parse(text):
        doi = util.normalize_doi(ref.get("doi") or "") or ""
        paper, how = catalogue.match(doi, ref.get("title") or "")
        record = paper.record if paper is not None else {}
        entry = {
            "n": ref.get("n"),
            "raw": ref.get("raw"),
            "authors": ref.get("authors") or "",
            # The library's spelling when matched: seeing it is how you check
            # a fuzzy match was right.
            "title": record.get("title") or ref.get("title") or "",
            "doi": doi or record.get("doi") or "",
            "year": ref.get("year") or record.get("year"),
            "journal": ref.get("journal") or record.get("journal") or "",
            "url": ref.get("url") or "",
            "wid": "",
            "pdf": "",
            "in_library": paper is not None,
            "matched": how,
        }
        entry["key"] = record.get("key") or entry["doi"] or util.synth_key(entry["title"] or entry["raw"])
        out.append(entry)
    return out
