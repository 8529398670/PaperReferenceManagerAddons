"""Seeding the content from the old prma's caches, once, so nothing slow is
fetched again: `manage import-legacy --openalex --from <old output dir>`.

  cache/openalex/<base64(doi)>.json      a paper's OpenAlex record, with its
                                         cited_by_works (the old top 200), or
                                         a "not_found" tombstone
  cache/openalex/references/<wid>.json   every referenced work, in full
  methods/<doi with / as _>.txt          the old OCR'd methods sections
  cache/github, cache/osf, cache/datasets  the GitHub / OSF enrichment caches
                                         (converted by app/content/enrich.py)

With --figures, the old figure crops instead (seed_figures):

  cache/papers/<doi_>.json               each paper's YOLO boxes, with the
                                         OCR text of its caption boxes
  images/ALL/<doi_>-figure-N.png         the crops, numbered as the picks are
  images/<doi_>-Figures.png              the montage
  cache/images-state.json,               the two figure reports' picks and
  cache/method-images-state.json         skipped papers

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


# -- figures ---------------------------------------------------------------------

OCR_ENGINES = ("rapid", "paddle", "surya", "tesseract")


@dataclass
class SeededFigures:
    papers: int = 0
    done: int = 0
    figures: int = 0
    already: int = 0
    absent: int = 0
    no_pdf: int = 0
    picks: dict[str, int] = field(default_factory=dict)


def _det_text(det: dict[str, Any]) -> str:
    ocr = det.get("ocr") or {}
    if not isinstance(ocr, dict):
        return str(ocr or "")
    for engine in OCR_ENGINES:
        if ocr.get(engine):
            return str(ocr[engine])
    return next((str(v) for v in ocr.values() if v), "")


def png_size(path: Path) -> tuple[int, int]:
    """A PNG's width and height from its header, without an image library."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
    except OSError:
        return 0, 0
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def seed_figures(content: ContentService, output: Path, progress: Callable[[str], None] = print) -> SeededFigures:
    """The old app's crops and montages linked in as each paper's figures
    stage, done, with the captions its OCR read, numbered exactly as the old
    reports numbered them (so the picks still point at the same figures)."""
    from app.content.figures import clean_caption
    from app.content.service import FIGURES_DIR, FIGURES_FILE, first_pdf, pdf_signature
    from app.worker import figures as wf

    images = output / "images"
    crops_dir = images / "ALL"
    records = output / "cache" / "papers"
    if not crops_dir.is_dir() or not records.is_dir():
        raise FileNotFoundError(f"no {crops_dir} or {records}: --from is the old prma's output/ folder")
    result = SeededFigures()
    rows = content.files.rows()
    papers = content.catalogue.all()
    result.papers = len(papers)
    for index, paper in enumerate(papers, start=1):
        if index % 250 == 0:
            progress(f"  {index}/{len(papers)} papers: {result.done} seeded ({result.figures} figures), {result.already} already here")
        key = paper.key
        pdf = first_pdf(paper.record)
        if not pdf:
            result.no_pdf += 1
            continue
        sig = "pdf:" + pdf_signature({"pdfs": [pdf]})
        if rows.get((key, st.FIGURES)) == (st.DONE, sig):
            result.already += 1
            continue
        prefix = key.replace("/", "_").replace("\\", "_")
        old = _read(records / f"{prefix}.json")
        yolo = (old or {}).get("yolo") if isinstance(old, dict) else None
        pages = (yolo or {}).get("pages") if isinstance(yolo, dict) else None
        if not pages:
            result.absent += 1
            continue
        dpi = ((yolo or {}).get("meta") or {}).get("dpi") or wf.DETECT_DPI
        scale = wf.CROP_DPI / dpi
        numbers = wf.number_figures(pages)
        folder = content.files.dir(key) / FIGURES_DIR
        found = []
        for page_idx, dets in enumerate(pages):
            dets = dets or []
            texts = {i: _det_text(d) for i, d in enumerate(dets) if isinstance(d, dict) and d.get("type") == wf.FIGURE_CAPTION}
            captions = wf.pair_captions(dets, scale, texts)
            for box in wf.page_crop_boxes(dets, scale, 10 ** 9, 10 ** 9):
                n = numbers.get((page_idx, box["det_idx"]))
                source = crops_dir / f"{prefix}-figure-{n}.png"
                if n is None or not source.is_file():
                    continue
                link_or_copy(source, folder / f"figure-{n}.png")
                w, h = png_size(source)
                found.append({
                    "n": n, "page": page_idx + 1, "bbox": list(box["bbox"]), "w": w, "h": h,
                    "caption": clean_caption(captions.get(box["det_idx"], "")), "dup": bool(box["dup"]), "file": f"figure-{n}.png",
                })
        montage = images / f"{prefix}-Figures.png"
        if montage.is_file() and found:
            link_or_copy(montage, folder / "montage.png")
        found.sort(key=lambda f: f["n"])
        content.files.write(key, FIGURES_FILE, {
            "version": 1, "source": "legacy", "dpi": wf.CROP_DPI, "pages": len(pages), "figures": found,
            "montage": "montage.png" if (folder / "montage.png").is_file() else None,
        })
        shown = sum(1 for f in found if not f["dup"])
        content.files.settle(key, st.FIGURES, sig, st.DONE, {"n": shown, "boxes": len(found), "legacy": True},
                             paper.record.get("date_added") or "", {"pdf": pdf})
        result.done += 1
        result.figures += len(found)
    return result


def import_figure_picks(figures: Any, output: Path) -> dict[str, int]:
    """The old /images and /method-images picks and skipped papers, merged
    with any made here (the old picks first, in their order)."""
    out = {}
    for view, name in (("all", "images-state.json"), ("method", "method-images-state.json")):
        data = _read(output / "cache" / name)
        if not isinstance(data, dict):
            continue
        old_selected = [str(i) for i in data.get("selected") or [] if "#figure-" in str(i)]
        old_skipped = [str(k) for k in data.get("skipped") or [] if k]
        state = figures.state(view)
        selected = old_selected + [i for i in state["selected"] if i not in set(old_selected)]
        skipped = sorted(set(old_skipped) | set(state["skipped"]))
        figures.replace(view, selected, skipped)
        out[view] = len(set(old_selected) - set(state["selected"]))
    return out
