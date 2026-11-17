"""The Review screen's Library pool: every candidate paper (on a list or with a
picked figure) with its verdict, as the screener left it in the content
queue.

The list carries what a row and its filters need -- the verdict, task and
priority, model name, the value of every extracted field with where it came
from -- and leaves the quotes out: a card that is opened asks for its paper
(paper()), which brings every value's evidence and the alternatives.

Nothing here screens: a paper not screened yet is "waiting", and the page
updates as the queue's "paper" events for the review stage arrive.
"""
from __future__ import annotations

import threading
from typing import Any

import msgspec

from app.content import store as st
from app.content.screens import memberships
from app.review.service import RESULT_FILE, ReviewService

WAITING = "waiting"
FAILED = "failed"
INCLUDED = "included"
BORDERLINE = "borderline"
EXCLUDED = "excluded"


class ReviewView:
    def __init__(self, review: ReviewService, content: Any, figures: Any, store: Any) -> None:
        self.review = review
        self.content = content
        self.files: st.ContentStore = content.files
        self.figures = figures
        self.store = store
        self._lock = threading.Lock()
        # key -> (mtime, value): review.json and openalex.json's date, read
        # again only when the file changed.
        self._results: dict[str, tuple[float, dict[str, Any] | None]] = {}
        self._dates: dict[str, tuple[float, str]] = {}

    def _mtime(self, key: str, name: str) -> float:
        try:
            return (self.files.dir(key) / name).stat().st_mtime
        except OSError:
            return 0.0

    def stored(self, key: str) -> dict[str, Any] | None:
        mtime = self._mtime(key, RESULT_FILE)
        with self._lock:
            cached = self._results.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        found = self.files.read(key, RESULT_FILE) if mtime else None
        with self._lock:
            self._results[key] = (mtime, found)
        return found

    def pubdate(self, key: str) -> str:
        mtime = self._mtime(key, "openalex.json")
        if not mtime:
            return ""
        with self._lock:
            cached = self._dates.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        work = self.files.read(key, "openalex.json") or {}
        date = str(work.get("publication_date") or "")
        with self._lock:
            self._dates[key] = (mtime, date)
        return date

    @staticmethod
    def state_of(verdict: dict[str, Any]) -> str:
        if verdict.get("include"):
            return INCLUDED
        return BORDERLINE if verdict.get("borderline") else EXCLUDED

    def library(self) -> dict[str, Any]:
        """Every candidate as a row, the counts, and the dataset consensus."""
        review = self.review
        wanted = review.candidates()
        member = memberships(self.store)
        figs = self.figures.picks_per_paper()
        consensus = review.consensus()
        overrides = review.overrides()
        rules = review.rules
        summaries = self.files.summaries(list(wanted))
        rows = []
        counts = {INCLUDED: 0, BORDERLINE: 0, EXCLUDED: 0, WAITING: 0, FAILED: 0, "stale": 0}
        for key in wanted:
            paper = self.content.catalogue.get(key)
            if paper is None:
                continue
            record = paper.record
            stages = summaries.get(key) or {}
            oa_state, oa, _ = stages.get(st.OPENALEX, ("", {}, ""))
            code_state, code, _ = stages.get(st.CODE, ("", {}, ""))
            m = member.get(key) or {}
            row: dict[str, Any] = {
                "key": key, "title": record.get("title", ""), "year": record.get("year"), "doi": record.get("doi", ""),
                "journal": record.get("journal", ""), "added": record.get("date_added", ""), "has_pdf": bool(record.get("pdfs")),
                "authors": list(record.get("authors") or [])[:3], "n_authors": len(record.get("authors") or []),
                "cites": (oa or {}).get("cited_by_count") if oa_state == st.DONE else None,
                "pubdate": self.pubdate(key) if oa_state == st.DONE else "",
                "lists": m.get("lists", []), "tiers": m.get("tiers", []), "figs": figs.get(key, 0),
                "code_n": int((code or {}).get("n") or 0) if code_state == st.DONE else 0,
                "figures_n": int((stages.get(st.FIGURES, ("", {}, ""))[1] or {}).get("n") or 0) if stages.get(st.FIGURES, ("",))[0] == st.DONE else 0,
            }
            state = stages.get(st.REVIEW, ("", {}, ""))[0]
            stored = self.stored(key) if state == st.DONE else None
            if stored is None:
                row["state"] = FAILED if state == st.FAILED else WAITING
                counts[row["state"]] += 1
                rows.append(row)
                continue
            doi = (record.get("doi") or "").lower()
            override = overrides.get(key) or (overrides.get(doi) if doi else None) or {}
            shown = review.present(stored, override, consensus, rules)
            verdict = shown["verdict"]
            row.update({
                "state": self.state_of(verdict), "current": shown["current"],
                "reason_code": verdict.get("reason_code", ""), "reason": verdict.get("reason", ""),
                "task": verdict.get("task_category", ""), "priority": verdict.get("priority"),
                "attention_role": verdict.get("attention_role", ""), "model_name": shown["model_name"],
                "curated": shown["curated"], "datasets": shown["datasets"], "notes": shown["notes"],
            })
            if row["state"] == EXCLUDED:
                # The excluded table says which tests failed, without the
                # words each one matched (get_review has those).
                row["why"] = [{k: t.get(k) for k in ("test", "pass", "detail")} for t in verdict.get("why") or [] if not t.get("pass")]
            else:
                # Only what the paper states (or a dataset fills): a field
                # left out reads "not stated".
                row["fields"] = {
                    name: {k: v for k, v in (("value", f["value"]), ("source", f["source"]), ("alts", max(0, len(f["values"]) - 1)),
                                             ("from_dataset", f.get("from_dataset")), ("dataset_papers", f.get("dataset_papers")),
                                             ("note", f.get("note"))) if v not in (None, "", 0)}
                    for name, f in shown["fields"].items() if f["value"] or f.get("note")
                }
            counts[row["state"]] += 1
            if not shown["current"]:
                counts["stale"] += 1
            rows.append(row)
        return {
            "papers": rows, "counts": counts, "consensus": consensus,
            "fields": [{"name": f.name, "group": f.group} for f in rules.fields],
            "criteria": list(rules.doc.criteria_text.full), "criteria_abstract": list(rules.doc.criteria_text.abstract),
            "tasks": sorted(({"name": name, "priority": prio} for name, prio, _p, _a in rules.tasks), key=lambda t: (t["priority"], t["name"])),
            "unclassified_priority": rules.doc.unclassified_priority,
            "reasons": msgspec.structs.asdict(rules.doc.reasons),
            "setup": review.active, "signature": review.signature, "problem": review.problem,
        }

    def paper(self, key: str) -> dict[str, Any] | None:
        """One candidate's review in full: every field's values and quotes."""
        paper = self.content.catalogue.get(key)
        if paper is None:
            return None
        return self.review.result(key, (paper.record.get("doi") or "").lower())
