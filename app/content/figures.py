"""The Figures screen's side of the server: what each paper's figures are, which
of them read as a method (model-design) figure, the picks and skipped papers,
and the thumbnails.

The crops are the worker's (app/worker/, `python -m app worker`) or the old
app's, linked in by `manage import-legacy --figures`; either way each paper has
papers/<dir>/figures.json (the manifest: n, page, caption, dup, w, h) and
figures/figure-N.png. A figure's id is "<paper key>#figure-N" -- the old app's,
so the old picks carry over.

Two views share everything but their picks:
  all      every figure (a box YOLO found twice is left out unless picked)
  method   only the figures whose caption matches config/method-images.txt
           (app/content/method_figures.py)
Each view keeps its own picks (in pick order) and its own skipped papers, in
the database (db.BUCKET_FIGURE_PICKS): curation, unlike the crops.
"""
from __future__ import annotations

import io
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.content import store as st
from app.core import db
from app.search import query as q

VIEWS = ("all", "method")
OTHER = {"all": "method", "method": "all"}
MANIFEST = "figures.json"
FOLDER = "figures"
THUMB_WIDTH = 640
THUMB_QUALITY = 80
SORTS = ("added", "published", "match", "count", "title")
CHIPS = ("all", "lead", "selected", "skipped", "other")
MAX_TERM_CHIPS = 12


# Page furniture an OCR'd caption box picks up (src/pdf/md.py in the old app):
# whole lines dropped before matching, so a footer never reads as a caption.
_JUNK_LINES = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"^\s*downloaded\s+from\b", r"^\s*©\s*\d{4}", r"^\s*copyright\s+©", r"^\s*all\s+rights\s+reserved\.?\s*$",
    r"^\s*reprinted\s+with\s+permission\b", r"^\s*see\s+(?:also\s+)?http", r"^\s*https?://\S+\s*$",
    r"^\s*www\.[a-z0-9.\-]+(?:/\S*)?\s*$", r"^\s*see\s+the\s+terms\s+and\s+conditions\b", r"^\s*terms\s+and\s+conditions\s+\(",
    r"^\s*on\s+wiley\s+online\s+library\b", r"^\s*oa\s+articles?\s+are\s+governed\b",
    r"^\s*(?:are\s+)?governed\s+by\s+the\s+applicable\s+creative\s+commons", r"^\s*creative\s+commons\s+(?:license|attribution)",
    r"^\s*this\s+article\s+is\s+(?:protected|licensed)\s+(?:by|under)\b", r"^\s*for\s+rules?\s+of\s+use\s*;?",
    r"^\s*(?:re)?printed\s+from\b",
))


def clean_caption(text: str) -> str:
    """A caption as the old app matched it: junk lines dropped, words split
    across a line break rejoined, whitespace collapsed to single spaces."""
    if not text:
        return ""
    kept = [line for line in text.split("\n") if not any(rx.match(line.strip()) for rx in _JUNK_LINES)]
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", "\n".join(kept))
    return re.sub(r"\s+", " ", text).strip()


def figure_id(key: str, n: int) -> str:
    return f"{key}#figure-{n}"


def split_id(fid: str) -> tuple[str, int] | None:
    key, _, rest = fid.rpartition("#figure-")
    if not key or not rest.isdigit():
        return None
    return key, int(rest)


class Figures:
    def __init__(self, content: Any, store: db.Store, keywords_path: Path) -> None:
        self.content = content
        self.files: st.ContentStore = content.files
        self.store = store
        self.keywords_path = keywords_path
        self._lock = threading.Lock()
        # key -> (manifest mtime, figures); key -> (mtime, keywords sig, matches)
        self._manifests: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._matches: dict[str, tuple[float, str, dict[int, dict[str, Any]]]] = {}
        self._keywords: Any = None
        self._keywords_mtime = -1.0
        self._state: dict[str, dict[str, list[str]]] = {}

    # -- a paper's figures ---------------------------------------------------------

    def forget(self, key: str) -> None:
        """Its figures changed (the worker redid them)."""
        with self._lock:
            self._manifests.pop(key, None)
            self._matches.pop(key, None)

    def manifest(self, key: str) -> list[dict[str, Any]]:
        path = self.files.dir(key) / MANIFEST
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return []
        cached = self._manifests.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        data = self.files.read(key, MANIFEST) or {}
        figures = [
            {
                "n": int(f["n"]), "page": f.get("page"), "caption": (f.get("caption") or "").strip(), "dup": bool(f.get("dup")),
                "w": f.get("w"), "h": f.get("h"),
            }
            for f in data.get("figures") or [] if isinstance(f, dict) and str(f.get("n", "")).isdigit()
        ]
        with self._lock:
            self._manifests[key] = (mtime, figures)
        return figures

    def keywords(self) -> Any:
        from app.content import method_figures

        try:
            mtime = self.keywords_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._keywords is None or mtime != self._keywords_mtime:
            self._keywords = method_figures.load_keywords(self.keywords_path)
            self._keywords_mtime = mtime
        return self._keywords

    def matches(self, key: str) -> dict[int, dict[str, Any]]:
        """n -> the caption's match, for the figures that read as a method figure."""
        from app.content import method_figures

        figures = self.manifest(key)
        if not figures:
            return {}
        kw = self.keywords()
        mtime = self._manifests.get(key, (0.0,))[0]
        cached = self._matches.get(key)
        if cached and cached[0] == mtime and cached[1] == kw.signature:
            return cached[2]
        found = method_figures.match_paper(figures, kw)
        with self._lock:
            self._matches[key] = (mtime, kw.signature, found)
        return found

    def paths(self, key: str, n: int) -> Path:
        return self.files.dir(key) / FOLDER / f"figure-{n}.png"

    def thumb(self, key: str, n: int) -> Path | None:
        """A small copy of one crop for the grid, made the first time it is
        asked for and kept beside it (a crop is 400 DPI, often megabytes)."""
        source = self.paths(key, n)
        target = source.with_name(f"thumb-{n}.webp")
        try:
            source_mtime = source.stat().st_mtime
        except OSError:
            return None
        try:
            if target.stat().st_mtime >= source_mtime:
                return target
        except OSError:
            pass
        from PIL import Image

        with Image.open(source) as image:
            image.load()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            if image.width > THUMB_WIDTH:
                height = max(1, round(image.height * THUMB_WIDTH / image.width))
                image = image.resize((THUMB_WIDTH, height), Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "WEBP", quality=THUMB_QUALITY, method=4)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(buffer.getvalue())
        os.replace(tmp, target)
        return target

    # -- picks and skips ---------------------------------------------------------

    def state(self, view: str) -> dict[str, list[str]]:
        with self._lock:
            cached = self._state.get(view)
        if cached is None:
            record = self.store.get(db.BUCKET_FIGURE_PICKS, view) or {}
            cached = {"selected": list(record.get("selected") or []), "skipped": list(record.get("skipped") or [])}
            with self._lock:
                self._state[view] = cached
        return {"selected": list(cached["selected"]), "skipped": list(cached["skipped"])}

    def _change(self, view: str, change: Any) -> dict[str, list[str]]:
        """Read, change and write one view's record in one transaction, so two
        tabs picking at once both land."""
        with self.store.transaction() as tx:
            record = tx.get(db.BUCKET_FIGURE_PICKS, view) or {}
            current = {"selected": list(record.get("selected") or []), "skipped": list(record.get("skipped") or [])}
            change(current)
            current["selected"] = list(dict.fromkeys(current["selected"]))
            current["skipped"] = sorted(set(current["skipped"]))
            tx.put(db.BUCKET_FIGURE_PICKS, view, {**current, "updated_at": time.time()})
        with self._lock:
            self._state[view] = current
        return {"selected": list(current["selected"]), "skipped": list(current["skipped"])}

    def pick(self, view: str, ids: list[str], on: bool) -> dict[str, list[str]]:
        def change(current: dict[str, list[str]]) -> None:
            if on:
                current["selected"] += [i for i in ids if i not in current["selected"]]
            else:
                current["selected"] = [i for i in current["selected"] if i not in set(ids)]
        return self._change(view, change)

    def skip(self, view: str, keys: list[str], on: bool) -> dict[str, list[str]]:
        def change(current: dict[str, list[str]]) -> None:
            if on:
                current["skipped"] += keys
            else:
                current["skipped"] = [k for k in current["skipped"] if k not in set(keys)]
        return self._change(view, change)

    def replace(self, view: str, selected: list[str], skipped: list[str]) -> dict[str, list[str]]:
        """Clear (both empty) and its undo (the old state back)."""
        def change(current: dict[str, list[str]]) -> None:
            current["selected"] = list(selected)
            current["skipped"] = list(skipped)
        return self._change(view, change)

    def picks_per_paper(self) -> Counter[str]:
        """How many figures of each paper are picked, in either view: the Figs
        column of the Code and Datasets screens."""
        ids: set[str] = set()
        for view in VIEWS:
            ids.update(self.state(view)["selected"])
        out: Counter[str] = Counter()
        for fid in ids:
            parts = split_id(fid)
            if parts:
                out[parts[0]] += 1
        return out

    # -- the screen ---------------------------------------------------------------

    def listing(
        self, view: str, sort: str = "added", desc: bool = True, chip: str = "all", mod: str = "", term: str = "",
        text: str = "", offset: int = 0, limit: int = 40,
    ) -> dict[str, Any]:
        catalogue = self.content.catalogue
        state = self.state(view)
        other = self.state(OTHER[view])
        picked = set(state["selected"])
        picked_other = set(other["selected"])
        skipped = set(state["skipped"])
        summaries = self.files.summaries()
        needle = q.fold(text) if text.strip() else ""

        papers = []
        term_counts: Counter[str] = Counter()
        mod_counts: Counter[str] = Counter()
        counts = Counter()
        for key, stages in summaries.items():
            fstate, fsum, _ = stages.get(st.FIGURES, ("", {}, ""))
            if fstate != st.DONE or not fsum.get("boxes", fsum.get("n")):
                continue
            paper = catalogue.get(key)
            if paper is None:
                continue
            figures = self.manifest(key)
            if not figures:
                continue
            matches = self.matches(key) if view == "method" else {}
            shown = []
            for figure in figures:
                fid = figure_id(key, figure["n"])
                if view == "method":
                    if figure["n"] not in matches and fid not in picked:
                        continue
                elif figure["dup"] and fid not in picked:
                    continue
                item = dict(figure)
                item["id"] = fid
                item["picked"] = fid in picked
                item["picked_other"] = fid in picked_other
                if figure["n"] in matches:
                    item["match"] = matches[figure["n"]]
                shown.append(item)
            if not shown:
                continue
            record = paper.record
            mods = list((stages.get(st.MODALITIES, ("", {}, ""))[1] or {}).get("used") or [])
            terms = sorted({t for f in shown for t in (f.get("match") or {}).get("terms", [])})
            entry = {
                "key": key, "title": record.get("title", ""), "year": record.get("year"), "doi": record.get("doi", ""),
                "added": record.get("date_added", ""), "date": record.get("date", "") or str(record.get("year") or ""),
                "figures": shown, "skipped": key in skipped, "mods": mods, "terms": terms,
                "has_pick": any(f["picked"] for f in shown), "has_other": any(f["picked_other"] for f in shown),
                "lead": any((f.get("match") or {}).get("lead") for f in shown),
                "best": max([(f.get("match") or {}).get("score", 0) for f in shown] or [0]),
            }
            if needle and needle not in q.fold(" ".join([entry["title"], entry["doi"], " ".join(f["caption"] for f in shown)])):
                continue
            counts["all"] += 0 if entry["skipped"] else 1
            counts["skipped"] += 1 if entry["skipped"] else 0
            if not entry["skipped"]:
                counts["lead"] += 1 if entry["lead"] else 0
                counts["selected"] += 1 if entry["has_pick"] else 0
                counts["other"] += 1 if entry["has_other"] else 0
                for m in mods:
                    mod_counts[m] += 1
                for t in terms:
                    term_counts[t] += 1
            papers.append(entry)

        def keep(entry: dict[str, Any]) -> bool:
            if chip == "skipped":
                if not entry["skipped"]:
                    return False
            elif entry["skipped"]:
                return False
            if chip == "lead" and not entry["lead"]:
                return False
            if chip == "selected" and not entry["has_pick"]:
                return False
            if chip == "other" and not entry["has_other"]:
                return False
            if mod and mod not in entry["mods"]:
                return False
            if term and term not in entry["terms"]:
                return False
            return True

        chosen = [e for e in papers if keep(e)]
        orders = {
            "added": lambda e: e["added"] or "",
            "published": lambda e: e["date"] or "",
            "match": lambda e: (e["best"], e["added"] or ""),
            "count": lambda e: (len(e["figures"]), e["added"] or ""),
            "title": lambda e: (e["title"] or "").lower(),
        }
        chosen.sort(key=orders.get(sort, orders["added"]), reverse=desc)
        page = chosen[offset : offset + limit]
        end = offset + len(page)
        return {
            "papers": page,
            "total": len(chosen),
            "figures": sum(len(e["figures"]) for e in chosen),
            "next": end if end < len(chosen) else None,
            "counts": dict(counts),
            "mods": [{"name": m, "n": n} for m, n in mod_counts.most_common()],
            "terms": [{"name": t, "n": n} for t, n in term_counts.most_common()],
            "picks": len(state["selected"]),
            "skips": len(state["skipped"]),
            "workers": any(w["alive"] for w in self.files.workers()),
        }

    def export_rows(self, view: str) -> list[dict[str, Any]]:
        """Every pick of a view, in pick order, with its paper and caption."""
        catalogue = self.content.catalogue
        rows = []
        for order, fid in enumerate(self.state(view)["selected"], start=1):
            parts = split_id(fid)
            if not parts:
                continue
            key, n = parts
            paper = catalogue.get(key)
            record = paper.record if paper else {}
            caption = next((f["caption"] for f in self.manifest(key) if f["n"] == n), "")
            rows.append({
                "order": order, "id": fid, "key": key, "figure": n, "title": record.get("title", ""),
                "year": record.get("year") or "", "doi": record.get("doi", ""), "caption": caption,
            })
        return rows
