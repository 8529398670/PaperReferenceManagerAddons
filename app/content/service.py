"""Each paper's derived content, filled in by itself: the replacement for the
old snapshot -> stages -> reindex pipeline.

Nothing is run by hand. After every look at Zotero, reconcile() works out for
each paper the signature of what each stage reads, and a stage whose
signature moved is queued:

  openalex    the paper's DOI (or, with none, its title)
  methods,    Zotero's extracted text (size and mtime of .zotero-ft-cache)
  code,       plus each PDF's path|mtime|size, so a published version swapped
  datasets    in for the preprint is redone, with no `reprocess`
  modalities  that, the abstract, and the modality vocabulary's hash, so
              editing config/modalities.yaml re-tags every paper
  review      that, the abstract, and the screener rules' hash, so saving
              the Screener rules re-screens every candidate (only papers on
              a list or with a picked figure are candidates)

Two lanes work the queue, one task at a time each: "net" asks OpenAlex
(slow, remote, rate limited), "local" reads the paper's own text
(milliseconds). A burst of new papers never blocks anything else, a failure
waits out a backoff and never holds up the papers behind it, and opening a
paper moves its unfinished tasks to the front.

Two more stages are heavy (figure crops, OCR of a scanned PDF): they need ML
packages the server does not have, so the optional worker process runs them
(app/worker/, `python -m app worker`), taking tasks from the same queue. The
server only queues them and listens for what the worker finishes (watch()).
With no worker they stay pending and nothing else waits on them.

Every finished stage is published as a "paper" event on the library's
stream, so an open screen fills in place.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.content import links, modalities, openalex, sections
from app.content import store as st
from app.content.pool import Pool
from app.core import db, graceful
from app.library.catalogue import Catalogue, Paper
from app.review import screen as review_screen
from app.search import query as q

IDLE_SECONDS = {"net": 3.0, "local": 1.0}
# A pause between OpenAlex tasks: a polite pace even with nothing to wait for.
NET_PAUSE_SECONDS = 0.2
QUEUE_EVENT_SECONDS = 1.0
# How often the server looks for what a worker finished.
WATCH_SECONDS = 2.0
OCR_FILE = "ocr.txt"
FIGURES_FILE = "figures.json"
FIGURES_DIR = "figures"
MAX_TEXT_BYTES = 2 * 1024 * 1024
MODALITIES_FILE = "modalities.yaml"
# A review result kept per rules signature: review@<sig>.json beside review.json.
REVIEW_KEPT = "review@"
REVIEW_KEPT_MAX = 8


def read_text(files: list[str]) -> str:
    """The paper's full text as Zotero extracted it (zotero.Item.read_fulltext)."""
    chunks: list[str] = []
    budget = MAX_TEXT_BYTES
    for name in files or []:
        try:
            with open(name, "rb") as handle:
                raw = handle.read(budget)
        except OSError:
            continue
        budget -= len(raw)
        chunks.append(raw.decode("utf-8", errors="replace"))
        if budget <= 0:
            break
    return "\n".join(chunks)


def pdf_signature(record: dict[str, Any]) -> str:
    parts = []
    for name in record.get("pdfs") or []:
        try:
            stat = os.stat(name)
            parts.append(f"{name}|{int(stat.st_mtime)}|{stat.st_size}")
        except OSError:
            parts.append(f"{name}|-")
    return ";".join(parts)


def first_pdf(record: dict[str, Any]) -> str:
    """The PDF the heavy stages read: the first one Zotero has."""
    for name in record.get("pdfs") or []:
        if name:
            return name
    return ""


def text_usable(body: str) -> bool:
    """Whether Zotero's text of a PDF is worth reading, or the PDF needs OCR
    (a scan with no text layer, or garbage where the text should be)."""
    try:
        from app.worker.ocr import needs_ocr
    except ImportError:
        return bool(body.strip())
    return not needs_ocr(body)


def _short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


class ContentService:
    def __init__(
        self,
        content_dir: Path,
        index_path: Path,
        catalogue: Catalogue,
        store: db.Store,
        vocab_path: Path,
        settings: Callable[[], Any],
    ) -> None:
        self.files = st.ContentStore(content_dir)
        self.pool = Pool(index_path)
        self.catalogue = catalogue
        self.store = store
        self.vocab_path = vocab_path
        self.vocab = modalities.load_vocab(vocab_path)
        self._vocab_mtime = self._mtime(vocab_path)
        # The running library section of config.yaml (openalex on/off, key).
        self.settings = settings
        self.client_factory: Callable[[str], openalex.Client] = lambda key: openalex.Client(key)
        self._client: openalex.Client | None = None
        self._client_key: str | None = None
        # Hears ("paper", {...}) and ("queue", {}); main points it at the
        # library's stream.
        self.publish: Callable[[str, dict[str, Any]], None] = lambda name, data: None
        self.dirty = True
        self._wids: dict[str, str] = {}
        self._skips: set[str] | None = None
        self._skips_lock = threading.Lock()
        self._last_queue_event = 0.0
        self.running: dict[str, str] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._backfill_after = 0.0
        self.on_meta: Callable[[list[str]], None] | None = None
        # Papers whose Zotero text is unusable (methods summary usable=False):
        # they are the ones OCR is queued for. Loaded on the first reconcile.
        self._unusable: set[str] | None = None
        # The last change to a heavy task the server has passed on (watch()).
        self._heard = time.time()
        self._workers_seen: tuple[Any, ...] = ()
        # Told when a paper's figures changed (the Figures screen's cache).
        self.on_figures: Callable[[str], None] | None = None
        # The review screener (app/review/service.py); main sets it. None
        # leaves the review stage out entirely.
        self.review: Any = None

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def close(self) -> None:
        self.files.close()
        self.pool.close()

    # -- what each paper needs -----------------------------------------------------

    def signatures(self, paper: Paper, rows: dict[tuple[str, str], tuple[str, str]]) -> dict[str, str] | None:
        """The input signature of each stage, None while the text pass has not
        reached this paper yet (it would only be redone a moment later)."""
        record = paper.record
        doi = (record.get("doi") or "").lower()
        out = {st.OPENALEX: ("doi:" + doi) if doi else ("title:" + _short(q.fold(record.get("title"))))}
        if not paper.text_sig:
            return out
        text = paper.text_sig + "#" + pdf_signature(record)
        state, ocr_sig = rows.get((paper.key, st.OCR), ("", ""))
        if state == st.DONE:
            # The worker's OCR is in: the text stages read it now.
            text += "#ocr:" + _short(ocr_sig)
        abstract = record.get("abstract") or ""
        out[st.METHODS] = text
        out[st.CODE] = text + "#" + _short(abstract)
        out[st.DATASETS] = text + "#" + _short(abstract)
        oa_state = rows.get((paper.key, st.OPENALEX), ("", ""))[0]
        # With no Zotero abstract, OpenAlex's is used, so its arrival re-tags.
        abstract_part = _short(abstract) if abstract else "oa:" + ("1" if oa_state == st.DONE else "0")
        out[st.MODALITIES] = self.vocab.signature + "#" + text + "#" + abstract_part
        if self.review is not None and paper.key in self.review.candidates():
            out[st.REVIEW] = "rules:" + self.review.signature + "#" + text + "#" + abstract_part
        return out

    def heavy(self, paper: Paper) -> list[tuple[str, str, dict[str, Any]]]:
        """(stage, sig, input) of the heavy stages a paper needs: figures for
        any paper with a PDF; OCR only once the text pass found its text
        missing or unusable."""
        pdf = first_pdf(paper.record)
        if not pdf:
            return []
        sig = "pdf:" + pdf_signature({"pdfs": [pdf]})
        out = [(st.FIGURES, sig, {"pdf": pdf})]
        unusable = self._unusable or set()
        if paper.text_sig and (not paper.has_text or paper.key in unusable):
            out.append((st.OCR, sig, {"pdf": pdf}))
        return out

    def _load_unusable(self) -> set[str]:
        if self._unusable is None:
            self._unusable = {
                key for key, stages in self.files.summaries().items()
                if stages.get(st.METHODS, ("", {}, ""))[1].get("usable") is False
            }
        return self._unusable

    def reconcile(self) -> int:
        """Queue what changed since the last look. Cheap: a stat per PDF and a
        compare per stage; nothing is read unless it changed."""
        self.dirty = False
        mtime = self._mtime(self.vocab_path)
        if mtime != self._vocab_mtime:
            self._vocab_mtime = mtime
            self.vocab = modalities.load_vocab(self.vocab_path)
        if self.review is not None:
            self.review.refresh()
        papers = self.catalogue.all()
        if not self.catalogue.status.ready or not papers:
            return 0
        rows = self.files.rows()
        self._load_unusable()
        wants: list[tuple[Any, ...]] = []
        settled = 0
        for paper in papers:
            sigs = self.signatures(paper, rows)
            if sigs is None:
                continue
            added = paper.record.get("date_added") or ""
            for stage, sig in sigs.items():
                row = rows.get((paper.key, stage), ("", None))
                if row[1] != sig:
                    if stage == st.REVIEW and self._review_kept(paper.key, row, sig, added):
                        settled += 1
                        continue
                    wants.append((paper.key, stage, sig, added, 0.0))
            for stage, sig, given in self.heavy(paper):
                if rows.get((paper.key, stage), ("", None))[1] != sig:
                    wants.append((paper.key, stage, sig, added, 0.0, given))
        changed = (self.files.want(wants) if wants else 0) + settled
        if self.review is not None:
            # Off a list and with no figure picked: no longer screened.
            wanted = self.review.candidates()
            for key, stage in list(rows):
                if stage == st.REVIEW and key not in wanted:
                    self.files.drop(key, st.REVIEW, "review.json")
                    self._prune_reviews(key, keep=set())
                    self.review.dropped(key)
                    changed += 1
        here = {paper.key for paper in papers}
        gone = {key for key, _ in rows if key not in here}
        if gone:
            self.files.forget(gone)
            self.pool.drop_paper(gone)
            for key in gone:
                self._wids.pop(key, None)
        self._refresh_library(papers)
        if changed or gone:
            self._queue_event(force=True)
        return changed

    def _refresh_library(self, papers: list[Paper]) -> None:
        if not self._wids:
            for key, stages in self.files.summaries().items():
                state, summary, _ = stages.get(st.OPENALEX, ("", {}, ""))
                if state == st.DONE and summary.get("wid"):
                    self._wids[key] = summary["wid"]
        dois = {(p.record.get("doi") or "").lower() for p in papers} - {""}
        titles = {p.title_f for p in papers} - {""}
        self.pool.set_library(set(self._wids.values()), dois, titles)

    # -- the lanes -------------------------------------------------------------------

    def start(self) -> None:
        for lane in ("net", "local"):
            self._tasks.append(asyncio.create_task(self._lane(lane)))
        self._tasks.append(asyncio.create_task(self._watch()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks = []

    async def _lane(self, lane: str) -> None:
        while True:
            try:
                worked = await graceful.run_abandonable(self.step, lane)
            except Exception as error:  # noqa: BLE001 -- one bad task must never stop the lane
                print(f"[content] {lane} lane: {error!r}", flush=True)
                worked = False
            await asyncio.sleep(NET_PAUSE_SECONDS if worked and lane == "net" else 0 if worked else IDLE_SECONDS[lane])

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(WATCH_SECONDS)
            try:
                await asyncio.to_thread(self.watch)
            except Exception as error:  # noqa: BLE001 -- keep listening
                print(f"[content] watch: {error!r}", flush=True)

    def watch(self) -> int:
        """Pass on what a worker finished since the last look: a "paper"
        event per task, OCR text into the search index (and the text stages
        queued again to read it), and the Figures screen told."""
        rows = self.files.changed_since(self._heard, st.HEAVY)
        for key, stage, state, at in rows:
            self._heard = max(self._heard, at)
            if state == st.DONE and stage == st.OCR:
                text = self.ocr_text(key)
                if text:
                    self.catalogue.put_text(key, text)
                self.dirty = True
            if stage == st.FIGURES and self.on_figures is not None:
                self.on_figures(key)
            self.publish("paper", {"key": key, "stage": stage, "state": state})
        # A worker starting, stopping or taking the next task: the Status
        # screen's worker line follows it (it listens for "queue").
        workers = tuple((w["id"], w["alive"], w["doing"]) for w in self.files.workers())
        if workers != self._workers_seen:
            self._workers_seen = workers
            self._queue_event(force=True)
        elif rows:
            self._queue_event()
        return len(rows)

    def ocr_text(self, key: str) -> str:
        try:
            return (self.files.dir(key) / OCR_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def step(self, lane: str) -> bool:
        """Run the next task of a lane. -> whether there was one."""
        now = time.time()
        # Not before the catalogue has loaded: until then every paper looks
        # gone, and a task would be dropped with its results.
        if not self.catalogue.status.ready or not self.catalogue.all():
            return False
        if lane == "local":
            if self.dirty:
                self.reconcile()
            due = self.files.next_due(st.LOCAL, now)
            if due is None:
                return False
            self.run_local(due[0])
            return True
        library = self.settings()
        if not library.openalex_enabled:
            return self.backfill_one()
        due = self.files.next_due((st.OPENALEX,), now)
        if due is None:
            return self.backfill_one()
        self.run_openalex(due[0], library.openalex_api_key)
        return True

    def _finished(self, key: str, stage: str) -> None:
        state = self.files.of(key).get(stage, {}).get("state", "")
        self.publish("paper", {"key": key, "stage": stage, "state": state})
        self._queue_event()

    def _queue_event(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_queue_event >= QUEUE_EVENT_SECONDS:
            self._last_queue_event = now
            self.publish("queue", {})

    # -- the local stages -------------------------------------------------------------

    def run_local(self, key: str) -> None:
        """Every due local stage of one paper, in one read of its text."""
        paper = self.catalogue.get(key)
        if paper is None:
            # Gone from Zotero: reconcile drops it with everything else gone.
            self.reconcile()
            return
        due = self.files.pending_for(key, st.LOCAL, time.time())
        record = paper.record
        self.running["local"] = key
        try:
            body = read_text(record.get("fulltext_files") or [])
            usable = text_usable(body)
            if not usable:
                # A scanned PDF: the worker's OCR, once it has run.
                ocr = self.ocr_text(key)
                if ocr.strip():
                    body = ocr
            parts = sections.split(body) if body else []
            methods = sections.methods_text(parts) if parts else ""
            if not methods:
                # The old app's OCR'd methods section, when the import brought
                # one and Zotero's text gave none (app/content/legacy.py).
                try:
                    methods = (self.files.dir(key) / "methods_legacy.txt").read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    methods = ""
                if methods:
                    parts = parts + [{"key": "methods", "heading": "Methods (from the old app)", "text": methods}]
            found: dict[str, Any] | None = None
            for stage in st.LOCAL:
                if stage not in due:
                    continue
                sig = self.files.start(key, stage)
                try:
                    if stage == st.METHODS:
                        self.files.write(key, "sections.json", {"sections": parts})
                        summary = {
                            "sections": len(parts), "methods_chars": len(methods), "has_text": bool(body.strip()), "usable": usable,
                        }
                        unusable = self._load_unusable()
                        if usable:
                            unusable.discard(key)
                        elif key not in unusable:
                            unusable.add(key)
                            self.dirty = True
                    elif stage in (st.CODE, st.DATASETS):
                        if found is None:
                            found = links.scan_paper(record.get("title") or "", record.get("abstract") or "", body)
                            self.files.write(key, "links.json", found)
                        if stage == st.CODE:
                            summary = {"n": len(found.get("code") or [])}
                        else:
                            summary = {"n": len(found.get("data") or []), "names": len(found.get("names") or [])}
                    elif stage == st.REVIEW:
                        abstract = record.get("abstract") or self._oa_abstract(key) or next(
                            (p["text"] for p in parts if p.get("key") == "abstract"), "")
                        kept = []
                        for part in parts:
                            if part.get("key") == "references":
                                break
                            kept.append(part)
                        result = self.review.screen(record.get("title") or "", abstract, methods, sections.render(kept))
                        self.files.write(key, "review.json", result)
                        self.review.screened(key, result)
                        summary = review_screen.summary(result)
                        self._keep_review(key, sig, result, summary)
                    else:
                        abstract = record.get("abstract") or self._oa_abstract(key)
                        used, inferred = modalities.tag(self.vocab, record.get("title") or "", abstract, methods, body)
                        self.files.write(key, "modalities.json", {"used": used, "inferred": inferred, "vocab": self.vocab.signature})
                        summary = {"used": used, "inferred": inferred}
                except Exception as error:  # noqa: BLE001 -- a bad paper fails its stage, nothing else
                    self.files.finish(key, stage, sig, st.FAILED, error=f"{type(error).__name__}: {error}")
                else:
                    self.files.finish(key, stage, sig, st.DONE, summary)
                self._finished(key, stage)
        finally:
            self.running.pop("local", None)
        if self.on_meta is not None:
            self.on_meta([key])

    # -- review results kept per setup ----------------------------------------------------

    def _keep_review(self, key: str, sig: str, result: dict[str, Any], summary: dict[str, Any]) -> None:
        """Keep a review result under its rules' signature (review@<sig>.json),
        so using that setup again takes it instead of screening again."""
        rules_sig, _, given = sig.removeprefix("rules:").partition("#")
        if not rules_sig or not sig.startswith("rules:"):
            return
        self.files.write(key, f"{REVIEW_KEPT}{rules_sig}.json", {"input": given, "result": result, "summary": summary})
        self._prune_reviews(key, self.review.signatures())

    def _review_kept(self, key: str, row: tuple[str, Any], sig: str, added: str) -> bool:
        """A review whose rules changed: keep the result it has, then take a
        kept one for the new rules if the paper's text is the same. -> whether
        it was taken (nothing to queue)."""
        state, old = row
        if state == st.DONE and isinstance(old, str) and old.startswith("rules:"):
            old_rules = old.removeprefix("rules:").partition("#")[0]
            if not (self.files.dir(key) / f"{REVIEW_KEPT}{old_rules}.json").is_file():
                current = self.files.read(key, "review.json")
                if isinstance(current, dict) and current.get("rules") == old_rules:
                    self._keep_review(key, old, current, review_screen.summary(current))
        rules_sig, _, given = sig.removeprefix("rules:").partition("#")
        kept = self.files.read(key, f"{REVIEW_KEPT}{rules_sig}.json")
        if not isinstance(kept, dict) or kept.get("input") != given or not isinstance(kept.get("result"), dict):
            return False
        result = kept["result"]
        self.files.write(key, "review.json", result)
        self.files.settle(key, st.REVIEW, sig, st.DONE, kept.get("summary") or review_screen.summary(result), added)
        self.review.screened(key, result)
        return True

    def _prune_reviews(self, key: str, keep: set[str]) -> None:
        """Drop kept results no setup holds, and all but the newest few."""
        folder = self.files.dir(key)
        try:
            found = [p for p in folder.glob(REVIEW_KEPT + "*.json")]
        except OSError:
            return
        held = []
        for path in found:
            if path.name[len(REVIEW_KEPT):-len(".json")] in keep:
                held.append(path)
            else:
                path.unlink(missing_ok=True)
        if len(held) > REVIEW_KEPT_MAX:
            held.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for path in held[REVIEW_KEPT_MAX:]:
                path.unlink(missing_ok=True)

    def oa_abstract(self, key: str) -> str:
        """A library paper's abstract as OpenAlex has it, or ""."""
        return self._oa_abstract(key)

    def _oa_abstract(self, key: str) -> str:
        work = self.files.read(key, "openalex.json") or {}
        return links.abstract_from_inverted(work.get("abstract_inverted_index"))

    # -- OpenAlex ------------------------------------------------------------------

    def client(self, api_key: str) -> openalex.Client:
        if self._client is None or self._client_key != api_key:
            self._client = self.client_factory(api_key)
            self._client_key = api_key
        return self._client

    def run_openalex(self, key: str, api_key: str = "") -> None:
        paper = self.catalogue.get(key)
        if paper is None:
            self.reconcile()
            return
        record = paper.record
        sig = self.files.start(key, st.OPENALEX)
        self.running["net"] = key
        try:
            fetched = self.client(api_key).fetch(record.get("doi") or "", record.get("title") or "")
        except openalex.NotFound:
            self.files.finish(key, st.OPENALEX, sig, st.NOT_FOUND, {}, error="OpenAlex has no such work")
            self.pool.drop_paper([key])
            self._wids.pop(key, None)
        except openalex.Unavailable as error:
            self.files.finish(key, st.OPENALEX, sig, st.FAILED, error=str(error))
        except Exception as error:  # noqa: BLE001
            self.files.finish(key, st.OPENALEX, sig, st.FAILED, error=f"{type(error).__name__}: {error}")
        else:
            self.save_openalex(key, sig, fetched.work, fetched.references, fetched.cited_by, fetched.cited_by_cut, fetched.via_title)
        finally:
            self.running.pop("net", None)
        self._finished(key, st.OPENALEX)
        self.dirty = True

    def save_openalex(
        self, key: str, sig: str, work: dict[str, Any], refs: list[dict[str, Any]], citers: list[dict[str, Any]],
        cut: bool = False, via_title: bool = False, settle: bool = False, added: str = "",
    ) -> dict[str, Any]:
        """Store one paper's OpenAlex result and put its network in the pool.
        settle: written as done outright (the legacy import) rather than as
        the end of a run."""
        work = {k: v for k, v in work.items() if k != "cited_by_works"}
        self.files.write(key, "openalex.json", work)
        self.files.write(key, "network.json.gz", {"refs": refs, "cited_by": citers, "cut": cut, "at": time.time()})
        wid = openalex.wid_of(work.get("id"))
        summary = {
            "wid": wid, "cited_by_count": work.get("cited_by_count") or 0, "refs": len(refs), "citers": len(citers),
            "cut": cut, "via_title": via_title, "oa_doi": openalex.normalize_doi(work.get("doi")) or "",
        }
        if settle:
            self.files.settle(key, st.OPENALEX, sig, st.DONE, summary, added)
        else:
            self.files.finish(key, st.OPENALEX, sig, st.DONE, summary)
        if wid:
            self._wids[key] = wid
        self.pool.put_paper(key, sig, refs, citers)
        return summary

    def backfill_one(self) -> bool:
        """A paper whose OpenAlex result is on disk but not in the pool (the
        index file was deleted, or the legacy import wrote it): put it in."""
        now = time.monotonic()
        if now < self._backfill_after:
            return False
        filled = self.pool.filled()
        for (key, stage), (state, sig) in self.files.rows().items():
            if stage != st.OPENALEX or state != st.DONE or filled.get(key) == sig:
                continue
            network = self.files.read(key, "network.json.gz")
            if network is None:
                continue
            self.pool.put_paper(key, sig, network.get("refs") or [], network.get("cited_by") or [])
            self._queue_event()
            return True
        # Nothing to do: look again in a minute (a `manage import-legacy`
        # running beside the server writes results this one did not make).
        self._backfill_after = now + 60
        return False

    # -- reading -------------------------------------------------------------------

    def open(self, key: str) -> None:
        """Someone is looking at this paper: what it is waiting on goes first."""
        if self.files.hurry(key):
            self._queue_event(force=True)

    def badges(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        out = {}
        for key, stages in self.files.summaries(keys).items():
            out[key] = badge(stages)
        return out

    def paper(self, key: str) -> dict[str, Any]:
        """Everything derived about one paper, for the Paper screen."""
        tasks = self.files.of(key)
        found = self.files.read(key, "links.json") or {}
        mods = self.files.read(key, "modalities.json") or {}
        parts = (self.files.read(key, "sections.json") or {}).get("sections") or []
        work = self.files.read(key, "openalex.json") or {}
        network = {}
        oa = tasks.get(st.OPENALEX) or {}
        if oa.get("state") == st.DONE:
            network = dict(oa.get("summary") or {})
            network.update(self.pool.network_counts(key))
        return {
            "stages": {stage: tasks.get(stage) or {"state": "none"} for stage in st.STAGES},
            "sections": parts,
            "code": found.get("code") or [],
            "data": found.get("data") or [],
            "names": found.get("names") or [],
            "modalities": mods.get("used") or [],
            "modalities_inferred": bool(mods.get("inferred")),
            "network": network,
            "openalex_abstract": links.abstract_from_inverted(work.get("abstract_inverted_index")) if work else "",
            "openalex_url": work.get("id") or "",
            "figures": self.figures_of(key) if (tasks.get(st.FIGURES) or {}).get("state") == st.DONE else [],
            "worker": any(w["alive"] for w in self.files.workers()),
        }

    def figures_of(self, key: str) -> list[dict[str, Any]]:
        """A paper's figure crops: {n, page, caption, dup, w, h} each."""
        manifest = self.files.read(key, FIGURES_FILE) or {}
        return [
            {k: figure.get(k) for k in ("n", "page", "caption", "dup", "w", "h")}
            for figure in manifest.get("figures") or [] if isinstance(figure, dict) and figure.get("n")
        ]

    def meta(self, keys: list[str], want_links: bool) -> dict[str, dict[str, Any]]:
        """What the list ops ask (ctx.meta): modality tags, Code/Datasets."""
        out: dict[str, dict[str, Any]] = {}
        summaries = self.files.summaries(keys)
        for key in keys:
            stages = summaries.get(key) or {}
            entry: dict[str, Any] = {}
            state, summary, _ = stages.get(st.MODALITIES, ("", {}, ""))
            if state == st.DONE:
                entry["mods"] = list(summary.get("used") or [])
            state, summary, _ = stages.get(st.METHODS, ("", {}, ""))
            entry["has_md"] = state == st.DONE and bool(summary.get("methods_chars"))
            if want_links and stages.get(st.CODE, ("",))[0] == st.DONE:
                found = self.files.read(key, "links.json") or {}
                entry["code"] = found.get("code") or []
                entry["data"] = found.get("data") or []
                entry["names"] = [{"name": n.get("name", ""), "url": n.get("url", "")} for n in found.get("names") or []]
            out[key] = entry
        return out

    def keys_with(self, what: str) -> set[str]:
        """The library's filter chips: code, data, no_openalex."""
        found = set()
        for key, stages in self.files.summaries().items():
            if what == "code":
                state, summary, _ = stages.get(st.CODE, ("", {}, ""))
                if state == st.DONE and summary.get("n"):
                    found.add(key)
            elif what == "data":
                state, summary, _ = stages.get(st.DATASETS, ("", {}, ""))
                if state == st.DONE and (summary.get("n") or summary.get("names")):
                    found.add(key)
            elif what == "no_openalex":
                if stages.get(st.OPENALEX, ("",))[0] in (st.NOT_FOUND, st.FAILED):
                    found.add(key)
        return found

    def status(self) -> dict[str, Any]:
        library = self.settings()
        return {
            "stages": self.files.counts(),
            "pool": self.pool.totals(),
            "running": dict(self.running),
            "workers": self.files.workers(),
            "openalex_enabled": library.openalex_enabled,
            "openalex_key": bool(library.openalex_api_key),
        }

    def wid_of(self, key: str) -> str:
        """A library paper's OpenAlex id, once its OpenAlex stage is done."""
        return self._wids.get(key, "")

    # -- skips -------------------------------------------------------------------

    def skipped(self) -> set[str]:
        with self._skips_lock:
            if self._skips is None:
                self._skips = {str(key) for key, _ in self.store.all(db.BUCKET_SKIPS)}
            return set(self._skips)

    def skip(self, wids: list[str], skip: bool, by: str) -> int:
        changed = 0
        have = self.skipped()
        with self.store.transaction() as tx:
            for wid in wids:
                if skip and wid not in have:
                    work = self.pool.work(wid) or {}
                    tx.put(db.BUCKET_SKIPS, wid, {"at": time.time(), "by": by, "title": work.get("title", "")})
                    changed += 1
                elif not skip and wid in have:
                    tx.delete(db.BUCKET_SKIPS, wid)
                    changed += 1
        with self._skips_lock:
            self._skips = None
        return changed


def badge(stages: dict[str, tuple[str, dict[str, Any], str]]) -> dict[str, Any]:
    """A paper's content, as the badges show it."""
    states = {stage: stages.get(stage, ("none", {}, ""))[0] for stage in st.STAGES}
    out: dict[str, Any] = {"states": states}
    errors = {stage: value[2] for stage, value in stages.items() if value[0] in (st.FAILED, st.NOT_FOUND) and value[2]}
    if errors:
        out["errors"] = errors
    state, summary, _ = stages.get(st.CODE, ("", {}, ""))
    if state == st.DONE:
        out["code"] = summary.get("n", 0)
    state, summary, _ = stages.get(st.DATASETS, ("", {}, ""))
    if state == st.DONE:
        out["data"] = summary.get("n", 0) + summary.get("names", 0)
    state, summary, _ = stages.get(st.METHODS, ("", {}, ""))
    if state == st.DONE:
        out["methods"] = bool(summary.get("methods_chars"))
        out["has_text"] = bool(summary.get("has_text"))
    state, summary, _ = stages.get(st.MODALITIES, ("", {}, ""))
    if state == st.DONE:
        out["mods"] = summary.get("used") or []
    state, summary, _ = stages.get(st.FIGURES, ("", {}, ""))
    if state == st.DONE:
        out["figures"] = summary.get("n", 0)
    state, summary, _ = stages.get(st.OPENALEX, ("", {}, ""))
    if state == st.DONE:
        out["citers"] = summary.get("citers", 0)
        out["refs"] = summary.get("refs", 0)
    return out
