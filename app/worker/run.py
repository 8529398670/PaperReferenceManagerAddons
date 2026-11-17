"""`python -m app worker`: the optional process that runs the heavy stages.

    figures   doclayout-yolo over the PDF's pages, each figure cropped with
              its caption at 400 DPI, a montage per paper (app/worker/figures.py)
    ocr       RapidOCR over a scanned PDF that has no usable text layer
              (app/worker/ocr.py)

It needs torch and friends, which have no Alpine wheels, so it is not part of
the server or its image: `scripts/run.sh worker` makes its own venv
(.venv-worker, from requirements-pipeline.txt) and starts it. The server never
waits for it. With no worker the two stages stay pending, the screens say
"not available", and everything else works the same.

It shares the server's queue (papers/content.db, SQLite in WAL mode): a task
is claimed with a lease, so two workers never take the same one, and one that
dies holding a task gives it back when the lease runs out. Results are plain
files in the paper's folder, which the server picks up by itself (it watches
the queue for heavy tasks that changed; ContentService.watch).

Only the standard library, PyYAML and the ML packages are imported here: the
worker's venv has none of the web stack.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from app.content import store as st

HEARTBEAT_SECONDS = 20.0
IDLE_SECONDS = 5.0
# Hugging Face's copy of the DocStructBench weights doclayout-yolo was trained as.
MODEL_REPO = "juliozhao/DocLayout-YOLO-DocStructBench"
OCR_FILE = "ocr.txt"
FIGURES_FILE = "figures.json"
FIGURES_DIR = "figures"

USAGE = """python -m app worker [--stages figures,ocr] [--model PATH] [--once]

  --stages   which heavy stages to run (default: both)
  --model    the doclayout-yolo weights (default: <app dir>/models/, fetched
             from Hugging Face the first time if missing)
  --once     run what is due, then stop (default: keep going)
"""


def parse(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app worker", description="Run the heavy content stages (figures, OCR).")
    parser.add_argument("--stages", default=",".join(st.HEAVY), help="comma-separated: figures, ocr")
    parser.add_argument("--model", default="", help="path to the doclayout-yolo weights (.pt)")
    parser.add_argument("--once", action="store_true", help="stop when nothing is due")
    args = parser.parse_args(arguments)
    stages = tuple(s.strip() for s in args.stages.split(",") if s.strip())
    bad = [s for s in stages if s not in st.HEAVY]
    if bad or not stages:
        parser.error(f"--stages takes {', '.join(st.HEAVY)}")
    args.stages = stages
    return args


def find_model(given: str, app_dir: Path) -> Path | None:
    """The weights: --model, else <app dir>/models/<file>, fetched there from
    Hugging Face the first time. None when there are none to be had."""
    from app.worker import figures

    if given:
        path = Path(given).expanduser()
        return path if path.is_file() else None
    path = app_dir / "models" / figures.MODEL_FILENAME
    if path.is_file():
        return path
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None
    try:
        print(f"[worker] fetching {figures.MODEL_FILENAME} from {MODEL_REPO}", flush=True)
        fetched = Path(hf_hub_download(repo_id=MODEL_REPO, filename=figures.MODEL_FILENAME))
    except Exception as error:  # noqa: BLE001 -- offline, renamed upstream: say so and run without figures
        print(f"[worker] could not fetch the model: {error}", flush=True)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fetched, path)
    return path


class Worker:
    def __init__(self, files: st.ContentStore, stages: tuple[str, ...], model: Path | None) -> None:
        self.files = files
        self.stages = stages
        self.model = model
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.started = time.time()
        self.doing: dict[str, str] | None = None
        self.note = ""
        self.stop = threading.Event()
        self._beat = threading.Thread(target=self._heartbeat, name="worker-heartbeat", daemon=True)

    # -- checking in -----------------------------------------------------------

    def beat(self) -> None:
        doing = f"{self.doing['stage']} {self.doing['key']}" if self.doing else ""
        self.files.beat({
            "id": self.id, "host": socket.gethostname(), "pid": os.getpid(), "started": self.started,
            "doing": doing, "stages": self.stages, "note": self.note,
        })
        if self.doing:
            self.files.renew(self.doing["key"], self.doing["stage"], self.id)

    def _heartbeat(self) -> None:
        while not self.stop.wait(HEARTBEAT_SECONDS):
            try:
                self.beat()
            except Exception as error:  # noqa: BLE001 -- a busy database: try again next beat
                print(f"[worker] heartbeat: {error!r}", flush=True)

    # -- the loop --------------------------------------------------------------

    def run(self, once: bool = False) -> int:
        self.beat()
        self._beat.start()
        done = 0
        try:
            while not self.stop.is_set():
                task = self.files.claim(self.stages, self.id)
                if task is None:
                    if once:
                        break
                    self.stop.wait(IDLE_SECONDS)
                    continue
                self.doing = task
                self.beat()
                try:
                    self.run_task(task)
                finally:
                    self.doing = None
                done += 1
        finally:
            self.stop.set()
            self.files.release(self.id)
            self.files.gone(self.id)
        return done

    def run_task(self, task: dict[str, Any]) -> None:
        key, stage, sig = task["key"], task["stage"], task["sig"]
        pdf = Path(str((task.get("input") or {}).get("pdf") or ""))
        started = time.monotonic()
        try:
            if not pdf.name or not pdf.is_file():
                raise FileNotFoundError(f"the PDF is not there: {pdf}")
            summary = self.figures(key, pdf) if stage == st.FIGURES else self.ocr(key, pdf)
        except Exception as error:  # noqa: BLE001 -- a bad PDF fails its own stage, nothing else
            print(f"[worker] {stage} {key}: {type(error).__name__}: {error}", flush=True)
            if os.environ.get("PRMA_WORKER_DEBUG"):
                traceback.print_exc()
            self.files.finish(key, stage, sig, st.FAILED, error=f"{type(error).__name__}: {error}")
            return
        summary["seconds"] = round(time.monotonic() - started, 1)
        self.files.finish(key, stage, sig, st.DONE, summary)
        print(f"[worker] {stage} {key}: done in {summary['seconds']}s", flush=True)

    def figures(self, key: str, pdf: Path) -> dict[str, Any]:
        from app.worker import figures

        if self.model is None:
            raise RuntimeError("no doclayout-yolo model (see --model)")
        folder = self.files.dir(key)
        manifest = figures.extract(pdf, folder / FIGURES_DIR, self.model)
        self.files.write(key, FIGURES_FILE, manifest)
        shown = [f for f in manifest.get("figures") or [] if not f.get("dup")]
        return {"n": len(shown), "boxes": len(manifest.get("figures") or []), "pages": manifest.get("pages", 0)}

    def ocr(self, key: str, pdf: Path) -> dict[str, Any]:
        from app.worker import ocr

        text = ocr.ocr_pdf(pdf)
        folder = self.files.dir(key)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = folder / (OCR_FILE + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, folder / OCR_FILE)
        return {"chars": len(text)}


def main(arguments: list[str]) -> None:
    from app.core import config

    args = parse(arguments)
    cfg = config.load()
    content_dir = cfg.library.content_dir
    files = st.ContentStore(content_dir)
    stages = args.stages
    model = None
    if st.FIGURES in stages:
        model = find_model(args.model, content_dir.parent)
        if model is None:
            print("[worker] no doclayout-yolo model: running OCR only (see --model)", flush=True)
            stages = tuple(s for s in stages if s != st.FIGURES)
    if not stages:
        raise SystemExit("nothing to run")
    worker = Worker(files, stages, model)
    if model is None and st.FIGURES in args.stages:
        worker.note = "no model: figures off"

    def stop(signum: int, frame: Any) -> None:
        if worker.stop.is_set():
            # Asked twice: drop the task in hand (it is released, due again).
            raise KeyboardInterrupt
        print("[worker] stopping after the task in hand (again to stop now)", flush=True)
        worker.stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"[worker] {worker.id}: {', '.join(stages)} from {content_dir}", flush=True)
    try:
        done = worker.run(once=args.once)
    finally:
        files.close()
    print(f"[worker] stopped after {done} task(s)", flush=True)
