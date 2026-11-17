"""Seeding the content from the old prma's caches, once, so nothing slow is
fetched again: `manage import-legacy --openalex --from <old output dir>`.

  cache/openalex/<base64(doi)>.json      a paper's OpenAlex record, with its
                                         cited_by_works (the old top 200), or
                                         a "not_found" tombstone
  cache/openalex/references/<wid>.json   every referenced work, in full
  methods/<doi with / as _>.txt          the old OCR'd methods sections
  cache/github, cache/osf, cache/datasets  enrichment caches, kept for later

Each library paper found there gets its OpenAlex stage written as done (or
not found), in the new shape, with its network put in the missing pool in the
same pass: one pass, never a reindex that comes back. A paper already done
here is skipped, so a cut-short run picks up where it stopped, and it is safe
with the server up (both use SQLite in WAL mode).

The old cited_by lists stop at 200; such a paper is marked "cut", and Retry
on its OpenAlex stage fetches every page.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.content import openalex
from app.content import store as st
from app.content.service import ContentService

ENRICHMENT = ("github", "osf", "datasets")


@dataclass
class Seeded:
    papers: int = 0
    done: int = 0
    not_found: int = 0
    already: int = 0
    absent: int = 0
    methods: int = 0
    skips: int = 0
    enrichment: dict[str, int] = field(default_factory=dict)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def link_or_copy(source: Path, target: Path) -> None:
    """A hard link where the disk allows (no space used), else a copy."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def seed(content: ContentService, output: Path, progress: Callable[[str], None] = print) -> Seeded:
    cache = output / "cache" / "openalex"
    if not cache.is_dir():
        raise FileNotFoundError(f"no {cache}: --from is the old prma's output/ folder")
    refs_dir = cache / "references"
    result = Seeded()
    rows = content.files.rows()
    compacts: dict[str, dict[str, Any] | None] = {}

    def reference(wid: str) -> dict[str, Any] | None:
        if wid not in compacts:
            data = _read(refs_dir / f"{wid}.json")
            compacts[wid] = openalex.compact(data) if data and data.get("id") else None
            # The old reference files are 34 KB each; the compact ones are a
            # few hundred bytes, and most are cited by more than one paper.
            if len(compacts) > 200_000:
                compacts.clear()
        return compacts[wid]

    papers = content.catalogue.all()
    result.papers = len(papers)
    started = time.monotonic()
    for index, paper in enumerate(papers, start=1):
        if index % 100 == 0:
            rate = index / max(time.monotonic() - started, 0.001)
            progress(f"  {index}/{len(papers)} papers ({rate:.0f}/s): {result.done} done, {result.not_found} not found, {result.already} already here")
        record = paper.record
        doi = (record.get("doi") or "").strip()
        if not doi:
            result.absent += 1
            continue
        sig = "doi:" + doi.lower()
        if rows.get((paper.key, st.OPENALEX), ("", ""))[1] == sig and rows[(paper.key, st.OPENALEX)][0] in st.SETTLED:
            result.already += 1
            continue
        data = _read(cache / (base64.b64encode(doi.encode("utf-8")).decode("ascii") + ".json"))
        if not isinstance(data, dict) or not data:
            result.absent += 1
            continue
        added = record.get("date_added") or ""
        if data.get("_openalex_status") == "not_found":
            content.files.settle(paper.key, st.OPENALEX, sig, st.NOT_FOUND, {}, added)
            result.not_found += 1
            continue
        if not data.get("id"):
            result.absent += 1
            continue
        citers = [openalex.compact(w) for w in data.get("cited_by_works") or [] if isinstance(w, dict)]
        refs = [r for r in (reference(openalex.wid_of(w)) for w in data.get("referenced_works") or []) if r]
        cut = (data.get("cited_by_count") or 0) > len(citers)
        content.save_openalex(paper.key, sig, data, refs, citers, cut=cut, settle=True, added=added)
        result.done += 1

    # The old methods text: the Paper screen and the modality tags use it
    # when the new split finds no methods section.
    methods_dir = output / "methods"
    if methods_dir.is_dir():
        for paper in papers:
            doi = paper.record.get("doi") or ""
            if not doi:
                continue
            source = methods_dir / (doi.replace("/", "_").replace("\\", "_") + ".txt")
            if source.is_file():
                link_or_copy(source, content.files.dir(paper.key) / "methods_legacy.txt")
                result.methods += 1

    # Kept as they are, for the GitHub / OSF / dataset enrichment to come.
    for name in ENRICHMENT:
        source = output / "cache" / name
        if not source.is_dir():
            continue
        count = 0
        for path in source.rglob("*"):
            if path.is_file():
                link_or_copy(path, content.files.root / "legacy" / name / path.relative_to(source))
                count += 1
        result.enrichment[name] = count
    return result


def import_skips(content: ContentService, output: Path) -> int:
    """The old Missing screen's skips (cache/skipped.json)."""
    data = _read(output / "cache" / "skipped.json")
    keys = [str(k) for k in ((data or {}).get("keys") or []) if str(k).startswith("W")]
    return content.skip(keys, True, "import-legacy") if keys else 0
