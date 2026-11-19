"""The review's Missing pool: the same three criteria, run over the papers you
do not have (the Missing screen's works), on their title and abstract alone.

There is no build. Each work keeps its own screen in search.db (pool.py's
rv_* columns) under the rules' signature; a new work, a work whose abstract
changed, or a change of rules leaves it unscreened, and the lane here screens
those a batch at a time in the background. The Review screen reads what is
there, with the progress, so it fills in as the lane goes.

What an abstract can show is little: thresholds for it live under
thresholds.abstract in the rules, and the page says what that costs with two
measured numbers (calibration): of the library candidates the full-text
screener judged, how many it included that the abstract screen also finds
(recall), and how many the abstract screen lets through that the full text
also included (precision). Both are re-measured when the rules or the
library's reviews move. The configured precision (missing.precision) is shown
only while there is nothing to measure against.

Old: src/review/missing.py, which screened the whole pool on `prma
review-missing` and wrote one document.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, Callable

from app.content import pool as P
from app.review import screen

BATCH = 400  # works screened per step
PAUSE_SECONDS = 0.05  # between batches while there is work
IDLE_SECONDS = 5.0
EVENT_SECONDS = 3.0
MAX_INCLUDED = 4000  # rows the screen sends (nearest your library first)
CALIBRATION_SECONDS = 60.0


def summary_of(rules: Any, title: str, abstract: str, verdict: dict[str, Any]) -> dict[str, Any]:
    """What a work's row shows, kept beside it."""
    out: dict[str, Any] = {"reason": verdict.get("reason_code", ""), "task": verdict.get("task_category", ""),
                           "priority": verdict.get("priority")}
    if verdict.get("include"):
        text = (title or "") + "\n" + (abstract or "")
        out["model_name"] = screen.model_name(title, abstract)
        out["datasets"] = screen.detect_datasets(rules, text, rules.cons("min_hits_abstract"))
        out["attention_role"] = verdict.get("attention_role", "")
    if verdict.get("near_miss"):
        out["near_miss"] = verdict["near_miss"]
    return out


def screen_work(rules: Any, title: str, abstract: str) -> tuple[int, str, str]:
    """(state, reason code, summary JSON) of one work."""
    if not (abstract or "").strip():
        return P.RV_NO_TEXT, "", ""
    verdict = screen.classify_abstract(rules, title, abstract)
    verdict["near_miss"] = screen.near_miss(verdict)
    state = P.RV_IN if verdict["include"] else P.RV_NEAR if verdict["near_miss"] else P.RV_OUT
    summary = summary_of(rules, title, abstract, verdict)
    return state, verdict.get("reason_code", ""), json.dumps(summary, separators=(",", ":"))


class MissingReview:
    def __init__(self, review: Any, pool: P.Pool) -> None:
        self.review = review
        self.pool = pool
        self.publish: Callable[[str, dict[str, Any]], None] = lambda name, data: None
        self._task: asyncio.Task[None] | None = None
        self._last_event = 0.0
        self._lock = threading.Lock()
        self._calibration: tuple[str, int, float, dict[str, Any]] | None = None

    # -- the lane --------------------------------------------------------------------

    def step(self) -> int:
        """Screen the next batch. -> how many works it screened."""
        rules = self.review.rules
        sig = rules.signature
        due = self.pool.review_due(sig, BATCH)
        if not due:
            return 0
        results = []
        for work_id, title, abstract in due:
            try:
                state, reason, rv = screen_work(rules, title, abstract)
            except Exception as error:  # noqa: BLE001 -- one odd abstract must never stop the pool
                state, reason, rv = P.RV_OUT, "error", json.dumps({"reason": "error", "error": str(error)[:200]})
            results.append((work_id, state, reason, rv))
        if self.review.rules.signature == sig:
            self.pool.review_store(sig, results)
        now = time.monotonic()
        if now - self._last_event >= EVENT_SECONDS:
            self._last_event = now
            tally = self.pool.review_tally(sig)
            self.publish("review_pool", {"screened": tally["screened"], "total": tally["total"]})
        return len(results)

    def start(self) -> None:
        self._task = asyncio.create_task(self._lane())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _lane(self) -> None:
        await asyncio.sleep(5)
        busy = False
        while True:
            try:
                did = await asyncio.to_thread(self.step)
            except Exception as error:  # noqa: BLE001
                print(f"[review] missing pool: {error!r}", flush=True)
                did = 0
            if busy and not did:
                # Finished a run: the page shows the final numbers.
                tally = self.pool.review_tally(self.review.signature)
                self.publish("review_pool", {"screened": tally["screened"], "total": tally["total"], "done": True})
            busy = bool(did)
            await asyncio.sleep(PAUSE_SECONDS if did else IDLE_SECONDS)

    # -- reading ---------------------------------------------------------------------------

    def snapshot(self, skipped: set[str] | None = None, scope: P.Scope | None = None) -> dict[str, Any]:
        """The pool's review as the screen loads it: of the works the reader's
        library lacks (scope; None for the only library)."""
        rules = self.review.rules
        sig = rules.signature
        skipped = skipped or set()
        tally = self.pool.review_tally(sig, scope)
        included, n_in = self.pool.review_rows(sig, P.RV_IN, MAX_INCLUDED, scope)
        near_cap = int(rules.doc.missing.max_nearmiss.value)
        near, n_near = self.pool.review_rows(sig, P.RV_NEAR, near_cap + len(skipped), scope)
        labels = dict(rules.doc.missing.miss_labels or {})
        for row in near:
            row["miss_label"] = labels.get(row.get("near_miss", ""), row.get("near_miss", ""))
        by_state = tally["by_state"]
        return {
            "signature": sig,
            "progress": {"screened": tally["screened"], "total": tally["total"]},
            "counts": {
                "included": by_state.get(P.RV_IN, 0), "near_misses": by_state.get(P.RV_NEAR, 0),
                "excluded": by_state.get(P.RV_OUT, 0) + by_state.get(P.RV_NEAR, 0), "no_abstract": by_state.get(P.RV_NO_TEXT, 0),
            },
            "reasons": tally["reasons"],
            "papers": [r for r in included if r["wid"] not in skipped],
            "papers_cut": max(0, n_in - len(included)),
            "near_misses": [r for r in near if r["wid"] not in skipped][:near_cap],
            "skipped": len(skipped),
        }

    def work(self, wid: str, consensus: list[dict[str, Any]]) -> dict[str, Any] | None:
        """One work's full abstract screen: verdict with its why, every field
        the abstract states with its quote, acquisition filled from the
        dataset consensus."""
        found = self.pool.work_text(wid)
        if found is None:
            return None
        title, abstract = found
        rules = self.review.rules
        stored = screen.screen_abstract(rules, title, abstract)
        result = self.review.present(stored, {}, consensus, rules)
        result["abstract"] = abstract
        return result

    # -- calibration ---------------------------------------------------------------------------

    def calibration(self, judged: Callable[[], list[tuple[str, str, bool]]], rev: int) -> dict[str, Any]:
        """Recall and precision of the abstract screen, measured against the
        full-text verdicts of the library's candidates: judged() gives
        (title, abstract, included by the full text) for each one screened
        with an abstract. Cached until the rules or rev move, and for a minute."""
        rules = self.review.rules
        now = time.monotonic()
        with self._lock:
            cached = self._calibration
        if cached and cached[0] == rules.signature and cached[1] == rev and now - cached[2] < CALIBRATION_SECONDS:
            return cached[3]
        pairs = judged()
        found = total = passed = agreed = 0
        for title, abstract, full in pairs:
            got = screen.classify_abstract(rules, title, abstract)["include"]
            if full:
                total += 1
                found += 1 if got else 0
            if got:
                passed += 1
                agreed += 1 if full else 0
        configured = rules.doc.missing.precision
        out = {
            "measured_over": len(pairs),
            "recall": round(found / total, 3) if total else None, "recall_found": found, "recall_total": total,
            "precision": round(agreed / passed, 3) if passed else None, "precision_agreed": agreed, "precision_passed": passed,
            "configured_precision": configured.value, "configured_precision_why": configured.why,
            "caveat": rules.doc.missing.caveat,
        }
        with self._lock:
            self._calibration = (rules.signature, rev, now, out)
        return out
