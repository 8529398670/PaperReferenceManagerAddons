"""Where each paper's derived content lives, and the queue that fills it.

  <app dir>/papers/content.db      one row per (paper, stage): its state, the
                                   signature of the input it was made from, a
                                   small summary for the badges, and the
                                   failure, if any. The queue is these rows.
  <app dir>/papers/<dir>/          the results, as plain JSON files: the
                                   OpenAlex record, its network, the methods
                                   split, the links found.

A stage is redone when the signature of what it reads changes (a new PDF, a
re-extracted text, an edited modality vocabulary) and never otherwise, so
there is nothing to rebuild and nothing to run by hand.

Derived data: not in the encrypted store (the queue needs SQL, and nothing
here is secret) and not under storage/, so backups leave it out. Losing it
costs refetching, never curation.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

# The stages, in the order a paper goes through them. OPENALEX is the
# network's lane (slow, remote); the rest read the paper's own text and run
# together in the local lane.
OPENALEX = "openalex"
METHODS = "methods"
CODE = "code"
DATASETS = "datasets"
MODALITIES = "modalities"
STAGES = (OPENALEX, METHODS, CODE, DATASETS, MODALITIES)
LOCAL = (METHODS, CODE, DATASETS, MODALITIES)
LANES = {"net": (OPENALEX,), "local": LOCAL}

# States. "not_found" is an answer (OpenAlex has no such work), so it is done
# as far as the queue goes, and only Retry asks again.
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
NOT_FOUND = "not_found"
STATES = (PENDING, RUNNING, DONE, FAILED, NOT_FOUND)
SETTLED = (DONE, NOT_FOUND)

# A failure waits this long before its next try, doubling, up to a day.
BACKOFF_FIRST = 60.0
BACKOFF_MAX = 24 * 3600.0


def backoff(attempts: int) -> float:
    return min(BACKOFF_FIRST * 2 ** max(attempts - 1, 0), BACKOFF_MAX)


def paper_dir_name(key: str) -> str:
    """A folder name for a key. A DOI has slashes and worse, so the readable
    part is cleaned and a hash keeps two cleaned-alike keys apart."""
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("._")[:100] or "paper"
    return f"{readable}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]}"


class ContentStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(root / "content.db", check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = NORMAL")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self._db.execute("DROP TABLE IF EXISTS tasks")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            " key TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL, sig TEXT NOT NULL DEFAULT '',"
            " priority REAL NOT NULL DEFAULT 0, added TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,"
            " error TEXT NOT NULL DEFAULT '', first_failed REAL, last_failed REAL, next_at REAL NOT NULL DEFAULT 0,"
            " done_at REAL, summary TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (key, stage))"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS tasks_due ON tasks (stage, state, priority DESC, added DESC)")
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        # A run the process died in is simply due again.
        self._db.execute("UPDATE tasks SET state = ? WHERE state = ?", (PENDING, RUNNING))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- files -------------------------------------------------------------------

    def dir(self, key: str) -> Path:
        return self.root / paper_dir_name(key)

    def write(self, key: str, name: str, data: Any) -> None:
        """One result file, written whole or not at all."""
        folder = self.dir(key)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = folder / name
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if name.endswith(".gz"):
            raw = gzip.compress(raw, compresslevel=6)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)

    def read(self, key: str, name: str) -> Any:
        path = self.dir(key) / name
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        try:
            if name.endswith(".gz"):
                raw = gzip.decompress(raw)
            return json.loads(raw)
        except (OSError, ValueError):
            return None

    def remove_files(self, key: str) -> None:
        folder = self.dir(key)
        if not folder.is_dir():
            return
        for path in folder.iterdir():
            try:
                path.unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass

    # -- the queue -----------------------------------------------------------------

    def rows(self) -> dict[tuple[str, str], tuple[str, str]]:
        """(key, stage) -> (state, sig) for every task: what reconcile diffs."""
        with self._lock:
            found = self._db.execute("SELECT key, stage, state, sig FROM tasks").fetchall()
        return {(key, stage): (state, sig) for key, stage, state, sig in found}

    def want(self, items: Iterable[tuple[str, str, str, str, float]]) -> int:
        """(key, stage, sig, added, priority): each task whose signature is not
        sig becomes pending with it. A task already on sig is left alone,
        whatever its state. -> how many changed."""
        changed = 0
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for key, stage, sig, added, priority in items:
                    cursor = self._db.execute(
                        "INSERT INTO tasks (key, stage, state, sig, added, priority) VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (key, stage) DO UPDATE SET state = excluded.state, sig = excluded.sig, "
                        "added = excluded.added, attempts = 0, error = '', next_at = 0, "
                        "priority = max(tasks.priority, excluded.priority) WHERE tasks.sig != excluded.sig",
                        (key, stage, PENDING, sig, added, priority),
                    )
                    changed += cursor.rowcount
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
        return changed

    def forget(self, keys: Iterable[str]) -> None:
        keys = list(keys)
        with self._lock:
            self._db.executemany("DELETE FROM tasks WHERE key = ?", [(k,) for k in keys])
        for key in keys:
            self.remove_files(key)

    def next_due(self, stages: tuple[str, ...], now: float) -> tuple[str, str] | None:
        """The task to run next in a lane: the highest priority, then the
        newest paper. A failure waits out its backoff."""
        marks = ",".join("?" * len(stages))
        with self._lock:
            row = self._db.execute(
                f"SELECT key, stage FROM tasks WHERE stage IN ({marks}) AND "
                f"(state = ? OR (state = ? AND next_at <= ?)) ORDER BY priority DESC, added DESC LIMIT 1",
                (*stages, PENDING, FAILED, now),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def pending_for(self, key: str, stages: tuple[str, ...], now: float) -> list[str]:
        marks = ",".join("?" * len(stages))
        with self._lock:
            found = self._db.execute(
                f"SELECT stage FROM tasks WHERE key = ? AND stage IN ({marks}) AND (state = ? OR (state = ? AND next_at <= ?))",
                (key, *stages, PENDING, FAILED, now),
            ).fetchall()
        return [row[0] for row in found]

    def start(self, key: str, stage: str) -> str:
        """Mark running. -> the signature it is being run for."""
        with self._lock:
            self._db.execute("UPDATE tasks SET state = ? WHERE key = ? AND stage = ?", (RUNNING, key, stage))
            row = self._db.execute("SELECT sig FROM tasks WHERE key = ? AND stage = ?", (key, stage)).fetchone()
        return row[0] if row else ""

    def finish(self, key: str, stage: str, sig: str, state: str, summary: dict[str, Any] | None = None, error: str = "") -> None:
        """Record a run's outcome -- unless the input changed while it ran (the
        signature moved on), in which case the task stays pending for the new
        input and this result is dropped."""
        now = time.time()
        with self._lock:
            row = self._db.execute("SELECT sig, attempts, first_failed FROM tasks WHERE key = ? AND stage = ?", (key, stage)).fetchone()
            if row is None or row[0] != sig:
                if row is not None:
                    self._db.execute("UPDATE tasks SET state = ? WHERE key = ? AND stage = ? AND state = ?", (PENDING, key, stage, RUNNING))
                return
            if state == FAILED:
                attempts = row[1] + 1
                self._db.execute(
                    "UPDATE tasks SET state = ?, attempts = ?, error = ?, first_failed = ?, last_failed = ?, next_at = ? "
                    "WHERE key = ? AND stage = ?",
                    (FAILED, attempts, error[:500], row[2] or now, now, now + backoff(attempts), key, stage),
                )
            else:
                self._db.execute(
                    "UPDATE tasks SET state = ?, attempts = 0, error = ?, done_at = ?, summary = ?, priority = 0, next_at = 0 "
                    "WHERE key = ? AND stage = ?",
                    (state, error[:500], now, json.dumps(summary or {}, separators=(",", ":")), key, stage),
                )

    def settle(self, key: str, stage: str, sig: str, state: str, summary: dict[str, Any], added: str = "") -> None:
        """Write a task as finished outright: what the legacy import does."""
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (key, stage, state, sig, added, summary, done_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (key, stage) DO UPDATE SET state = excluded.state, sig = excluded.sig, summary = excluded.summary, "
                "done_at = excluded.done_at, attempts = 0, error = '', next_at = 0",
                (key, stage, state, sig, added, json.dumps(summary, separators=(",", ":")), time.time()),
            )

    def hurry(self, key: str) -> int:
        """Someone opened this paper: its unfinished tasks go to the front, and
        a failure waiting out its backoff is due now."""
        with self._lock:
            cursor = self._db.execute(
                "UPDATE tasks SET priority = ?, next_at = 0 WHERE key = ? AND state IN (?, ?)", (time.time(), key, PENDING, FAILED)
            )
        return cursor.rowcount

    def retry(self, key: str = "", stage: str = "") -> int:
        """Ask again: failed and not-found tasks of a paper, of a stage, or one.
        A not-found OpenAlex lookup is only ever re-asked this way."""
        where, args = ["state IN (?, ?)"], [FAILED, NOT_FOUND]
        if key:
            where.append("key = ?")
            args.append(key)
        if stage:
            where.append("stage = ?")
            args.append(stage)
        with self._lock:
            cursor = self._db.execute(
                f"UPDATE tasks SET state = ?, attempts = 0, next_at = 0, priority = ? WHERE {' AND '.join(where)}",
                (PENDING, time.time() if key else 0, *args),
            )
        return cursor.rowcount

    # -- reading -----------------------------------------------------------------

    def of(self, key: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            found = self._db.execute(
                "SELECT stage, state, attempts, error, first_failed, last_failed, next_at, done_at, summary FROM tasks WHERE key = ?", (key,)
            ).fetchall()
        return {row[0]: _task(row) for row in found}

    def summaries(self, keys: Iterable[str] | None = None) -> dict[str, dict[str, tuple[str, dict[str, Any], str]]]:
        """key -> stage -> (state, summary, error), for the badges: every paper,
        or the ones named."""
        with self._lock:
            if keys is None:
                found = self._db.execute("SELECT key, stage, state, summary, error FROM tasks").fetchall()
            else:
                found = []
                wanted = list(dict.fromkeys(keys))
                for start in range(0, len(wanted), 500):
                    chunk = wanted[start : start + 500]
                    found += self._db.execute(
                        f"SELECT key, stage, state, summary, error FROM tasks WHERE key IN ({','.join('?' * len(chunk))})", chunk
                    ).fetchall()
        out: dict[str, dict[str, tuple[str, dict[str, Any], str]]] = {}
        for key, stage, state, summary, error in found:
            out.setdefault(key, {})[stage] = (state, json.loads(summary or "{}"), error)
        return out

    def counts(self) -> dict[str, dict[str, int]]:
        with self._lock:
            found = self._db.execute("SELECT stage, state, count(*) FROM tasks GROUP BY stage, state").fetchall()
        out = {stage: {state: 0 for state in STATES} for stage in STAGES}
        for stage, state, n in found:
            out.setdefault(stage, {s: 0 for s in STATES})[state] = n
        return out

    def listing(self, stage: str, states: tuple[str, ...]) -> list[dict[str, Any]]:
        """Every task of a stage in these states, for the Status and Errors screens."""
        marks = ",".join("?" * len(states))
        with self._lock:
            found = self._db.execute(
                "SELECT key, state, attempts, error, first_failed, last_failed, next_at, done_at, summary, priority, added "
                f"FROM tasks WHERE stage = ? AND state IN ({marks})",
                (stage, *states),
            ).fetchall()
        out = []
        for row in found:
            task = _task((stage,) + tuple(row[1:9]))
            task.update({"key": row[0], "priority": row[9], "added": row[10]})
            out.append(task)
        return out


def _task(row: tuple[Any, ...]) -> dict[str, Any]:
    _, state, attempts, error, first_failed, last_failed, next_at, done_at, summary = row
    task: dict[str, Any] = {"state": state, "attempts": attempts, "summary": json.loads(summary or "{}")}
    if error:
        task["error"] = error
    if first_failed:
        task["first_failed"] = first_failed
    if last_failed:
        task["last_failed"] = last_failed
    if state == FAILED and next_at:
        task["next_at"] = next_at
    if done_at:
        task["done_at"] = done_at
    return task
