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
from typing import Any, Callable, Iterable

# 2 added the heavy stages' columns (input, lease, owner, changed_at) and the
# workers table; a version-1 file is upgraded in place, never dropped.
SCHEMA_VERSION = 2

# The stages, in the order a paper goes through them. OPENALEX is the
# network's lane (slow, remote); the rest read the paper's own text and run
# together in the local lane.
OPENALEX = "openalex"
METHODS = "methods"
CODE = "code"
DATASETS = "datasets"
MODALITIES = "modalities"
# The review screener (app/review/): only papers on a list or with a picked
# figure, and redone when the screener's rules change.
REVIEW = "review"
# The heavy stages need ML packages the server does not have, so only the
# optional worker process (`python -m app worker`, app/worker/) runs them. If
# it never runs they stay pending, shown as "not available", and nothing else
# waits on them.
FIGURES = "figures"
OCR = "ocr"
STAGES = (OPENALEX, METHODS, CODE, DATASETS, MODALITIES, REVIEW, FIGURES, OCR)
LOCAL = (METHODS, CODE, DATASETS, MODALITIES, REVIEW)
HEAVY = (FIGURES, OCR)
LANES = {"net": (OPENALEX,), "local": LOCAL}

# How long a worker's claim on a heavy task lasts without being renewed; a
# worker that died is noticed this long after, and its task is due again.
LEASE_SECONDS = 15 * 60.0
# A worker that has not checked in for this long is shown as gone.
WORKER_STALE_SECONDS = 90.0

# States. "not_found" is an answer (OpenAlex has no such work), so it is done
# as far as the queue goes, and only Retry asks again.
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
NOT_FOUND = "not_found"
# Wanted, but only once someone opens the paper: with library.source remote,
# work that needs the PDF waits here so the whole library is never fetched.
HELD = "held"
STATES = (PENDING, RUNNING, DONE, FAILED, NOT_FOUND, HELD)
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
        if version not in (0, 1, SCHEMA_VERSION):
            self._db.execute("DROP TABLE IF EXISTS tasks")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            " key TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL, sig TEXT NOT NULL DEFAULT '',"
            " priority REAL NOT NULL DEFAULT 0, added TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,"
            " error TEXT NOT NULL DEFAULT '', first_failed REAL, last_failed REAL, next_at REAL NOT NULL DEFAULT 0,"
            " done_at REAL, summary TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (key, stage))"
        )
        # Version 1 had none of these; adding them keeps every task (and so
        # every OpenAlex answer already fetched).
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(tasks)")}
        for name, kind in (("input", "TEXT NOT NULL DEFAULT ''"), ("owner", "TEXT NOT NULL DEFAULT ''"),
                           ("lease_until", "REAL NOT NULL DEFAULT 0"), ("changed_at", "REAL NOT NULL DEFAULT 0")):
            if name not in columns:
                self._db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {kind}")
        self._db.execute("CREATE INDEX IF NOT EXISTS tasks_due ON tasks (stage, state, priority DESC, added DESC)")
        self._db.execute("CREATE INDEX IF NOT EXISTS tasks_changed ON tasks (changed_at)")
        # The workers that run the heavy stages check in here (a heartbeat), so
        # the server can say whether one is running and what it is doing.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, host TEXT NOT NULL DEFAULT '', pid INTEGER NOT NULL DEFAULT 0,"
            " started REAL NOT NULL DEFAULT 0, beat REAL NOT NULL DEFAULT 0, doing TEXT NOT NULL DEFAULT '',"
            " stages TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '')"
        )
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        # A run the process died in is simply due again. A heavy task belongs to
        # a worker, which may well be running on, so it is only due again once
        # its lease has run out (see claim).
        marks = ",".join("?" * len(HEAVY))
        self._db.execute(f"UPDATE tasks SET state = ? WHERE state = ? AND stage NOT IN ({marks})", (PENDING, RUNNING, *HEAVY))

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

    def want(self, items: Iterable[tuple[Any, ...]]) -> int:
        """(key, stage, sig, added, priority[, input]): each task whose
        signature is not sig becomes pending with it. A task already on sig is
        left alone, whatever its state. input is what a worker needs to run
        it (a heavy stage's PDF path), as JSON; it is kept current even when
        the signature has not moved. -> how many changed."""
        changed = 0
        now = time.time()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    key, stage, sig, added, priority = item[:5]
                    given = json.dumps(item[5], separators=(",", ":")) if len(item) > 5 else ""
                    cursor = self._db.execute(
                        "INSERT INTO tasks (key, stage, state, sig, added, priority, input, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (key, stage) DO UPDATE SET state = excluded.state, sig = excluded.sig, "
                        "added = excluded.added, attempts = 0, error = '', next_at = 0, input = excluded.input, "
                        "changed_at = excluded.changed_at, priority = max(tasks.priority, excluded.priority) WHERE tasks.sig != excluded.sig",
                        (key, stage, PENDING, sig, added, priority, given, now),
                    )
                    changed += cursor.rowcount
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
        return changed

    def drop(self, key: str, stage: str, name: str = "") -> None:
        """One stage of one paper is no longer wanted: its task goes, and its
        result file if named."""
        with self._lock:
            self._db.execute("DELETE FROM tasks WHERE key = ? AND stage = ?", (key, stage))
        if name:
            try:
                (self.dir(key) / name).unlink()
            except OSError:
                pass

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
                    self._db.execute(
                        "UPDATE tasks SET state = ?, owner = '', lease_until = 0 WHERE key = ? AND stage = ? AND state = ?",
                        (PENDING, key, stage, RUNNING),
                    )
                return
            if state == FAILED:
                attempts = row[1] + 1
                self._db.execute(
                    "UPDATE tasks SET state = ?, attempts = ?, error = ?, first_failed = ?, last_failed = ?, next_at = ?, "
                    "owner = '', lease_until = 0, changed_at = ? WHERE key = ? AND stage = ?",
                    (FAILED, attempts, error[:500], row[2] or now, now, now + backoff(attempts), now, key, stage),
                )
            else:
                self._db.execute(
                    "UPDATE tasks SET state = ?, attempts = 0, error = ?, done_at = ?, summary = ?, priority = 0, next_at = 0, "
                    "owner = '', lease_until = 0, changed_at = ? WHERE key = ? AND stage = ?",
                    (state, error[:500], now, json.dumps(summary or {}, separators=(",", ":")), now, key, stage),
                )

    def settle(self, key: str, stage: str, sig: str, state: str, summary: dict[str, Any], added: str = "",
               given: dict[str, Any] | None = None) -> None:
        """Write a task as finished outright: what the legacy import does.
        given is the input a worker would need to redo it (Retry)."""
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (key, stage, state, sig, added, summary, done_at, changed_at, input) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (key, stage) DO UPDATE SET state = excluded.state, sig = excluded.sig, summary = excluded.summary, "
                "done_at = excluded.done_at, changed_at = excluded.changed_at, attempts = 0, error = '', next_at = 0, "
                "input = CASE WHEN excluded.input != '' THEN excluded.input ELSE tasks.input END",
                (key, stage, state, sig, added, json.dumps(summary, separators=(",", ":")), now, now,
                 json.dumps(given, separators=(",", ":")) if given else ""),
            )

    def hurry(self, key: str) -> int:
        """Someone opened this paper: its unfinished tasks go to the front, and
        a failure waiting out its backoff is due now."""
        with self._lock:
            cursor = self._db.execute(
                "UPDATE tasks SET priority = ?, next_at = 0 WHERE key = ? AND state IN (?, ?)", (time.time(), key, PENDING, FAILED)
            )
        return cursor.rowcount

    def hold(self, stages: tuple[str, ...], keep: set[str]) -> int:
        """Pending tasks of these stages wait (held) unless their paper is in
        keep: what a remote library does only on demand. -> how many."""
        marks = ",".join("?" * len(stages))
        with self._lock:
            found = self._db.execute(
                f"SELECT key, stage FROM tasks WHERE state = ? AND stage IN ({marks})", (PENDING, *stages)
            ).fetchall()
            held = [(HELD, key, stage) for key, stage in found if key not in keep]
            if held:
                self._db.executemany("UPDATE tasks SET state = ? WHERE key = ? AND stage = ? AND state = 'pending'", held)
        return len(held)

    def unhold(self, key: str = "", stage: str = "", keep: set[str] | frozenset[str] = frozenset()) -> int:
        """Held tasks are due again: one task, first in line (its paper was
        opened), or all but keep's (the library is local again; keep is the
        papers gone from it)."""
        with self._lock:
            if key:
                cursor = self._db.execute(
                    "UPDATE tasks SET state = ?, priority = ?, changed_at = ? WHERE key = ? AND stage = ? AND state = ?",
                    (PENDING, time.time(), time.time(), key, stage, HELD),
                )
                return cursor.rowcount
            if not keep:
                return self._db.execute("UPDATE tasks SET state = ? WHERE state = ?", (PENDING, HELD)).rowcount
            found = self._db.execute("SELECT key, stage FROM tasks WHERE state = ?", (HELD,)).fetchall()
            due = [(PENDING, k, s) for k, s in found if k not in keep]
            if due:
                self._db.executemany("UPDATE tasks SET state = ? WHERE key = ? AND stage = ? AND state = 'held'", due)
        return len(due)

    def hold_keys(self, keys: set[str]) -> int:
        """Every task of these papers that would run waits instead: papers
        gone from the library, kept a while in case they come back."""
        if not keys:
            return 0
        with self._lock:
            found = self._db.execute(
                "SELECT key, stage FROM tasks WHERE state IN (?, ?)", (PENDING, FAILED)
            ).fetchall()
            held = [(HELD, k, s) for k, s in found if k in keys]
            if held:
                self._db.executemany("UPDATE tasks SET state = ? WHERE key = ? AND stage = ?", held)
        return len(held)

    def recheck_not_found(self, stage: str, now: float, wait: Callable[[str], float], skip: Iterable[str] = ()) -> int:
        """Not-found tasks of a stage asked again once wait(added) seconds
        have passed since the last answer: a paper OpenAlex had not indexed
        may be there now. Queued behind everything else. -> how many."""
        skip = set(skip)
        with self._lock:
            found = self._db.execute(
                "SELECT key, added, done_at FROM tasks WHERE stage = ? AND state = ?", (stage, NOT_FOUND)
            ).fetchall()
            due = [(key,) for key, added, done_at in found if key not in skip and (done_at or 0) + wait(added or "") <= now]
            if due:
                self._db.executemany(
                    f"UPDATE tasks SET state = '{PENDING}', attempts = 0, next_at = 0, priority = 0 "
                    f"WHERE key = ? AND stage = '{stage}' AND state = '{NOT_FOUND}'",
                    due,
                )
        return len(due)

    def retry(self, key: str = "", stage: str = "") -> int:
        """Ask again: failed and not-found tasks of a paper, of a stage, or one.
        Not-found OpenAlex lookups are also asked again by themselves, now
        and then (recheck_not_found)."""
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

    # -- the worker's side ------------------------------------------------------------

    def claim(self, stages: tuple[str, ...], owner: str, now: float | None = None, lease: float = LEASE_SECONDS) -> dict[str, Any] | None:
        """Take the next due task of these stages for one worker, atomically
        across processes: two workers never get the same task. A running task
        whose lease ran out (its worker died) is due again.
        -> {key, stage, sig, input} or None."""
        now = time.time() if now is None else now
        marks = ",".join("?" * len(stages))
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    f"SELECT key, stage, sig, input FROM tasks WHERE stage IN ({marks}) AND "
                    f"(state = ? OR (state = ? AND next_at <= ?) OR (state = ? AND lease_until < ?)) "
                    f"ORDER BY priority DESC, added DESC LIMIT 1",
                    (*stages, PENDING, FAILED, now, RUNNING, now),
                ).fetchone()
                if row is not None:
                    self._db.execute(
                        "UPDATE tasks SET state = ?, owner = ?, lease_until = ? WHERE key = ? AND stage = ?",
                        (RUNNING, owner, now + lease, row[0], row[1]),
                    )
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
        if row is None:
            return None
        try:
            given = json.loads(row[3]) if row[3] else {}
        except ValueError:
            given = {}
        return {"key": row[0], "stage": row[1], "sig": row[2], "input": given}

    def renew(self, key: str, stage: str, owner: str, lease: float = LEASE_SECONDS) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE tasks SET lease_until = ? WHERE key = ? AND stage = ? AND owner = ? AND state = ?",
                (time.time() + lease, key, stage, owner, RUNNING),
            )

    def release(self, owner: str) -> None:
        """A worker stopping cleanly: what it held is due again at once."""
        with self._lock:
            self._db.execute("UPDATE tasks SET state = ?, owner = '', lease_until = 0 WHERE owner = ? AND state = ?", (PENDING, owner, RUNNING))

    def beat(self, worker: dict[str, Any]) -> None:
        """A worker checking in: {id, host, pid, started, doing, stages, note}."""
        with self._lock:
            self._db.execute(
                "INSERT INTO workers (id, host, pid, started, beat, doing, stages, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET beat = excluded.beat, doing = excluded.doing, stages = excluded.stages, note = excluded.note",
                (worker["id"], worker.get("host", ""), worker.get("pid", 0), worker.get("started", time.time()), time.time(),
                 worker.get("doing", ""), ",".join(worker.get("stages") or ()), worker.get("note", "")),
            )

    def gone(self, worker_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))

    def workers(self, now: float | None = None) -> list[dict[str, Any]]:
        """The workers that checked in lately (older entries are dropped)."""
        now = time.time() if now is None else now
        with self._lock:
            self._db.execute("DELETE FROM workers WHERE beat < ?", (now - 24 * 3600,))
            found = self._db.execute("SELECT id, host, pid, started, beat, doing, stages, note FROM workers ORDER BY started").fetchall()
        out = []
        for wid, host, pid, started, beat, doing, stages, note in found:
            out.append({
                "id": wid, "host": host, "pid": pid, "started": started, "beat": beat, "doing": doing,
                "stages": [s for s in stages.split(",") if s], "note": note, "alive": now - beat <= WORKER_STALE_SECONDS,
            })
        return out

    def changed_since(self, since: float, stages: tuple[str, ...]) -> list[tuple[str, str, str, float]]:
        """(key, stage, state, changed_at) of the tasks of these stages that
        changed after since: how the server hears what a worker finished."""
        marks = ",".join("?" * len(stages))
        with self._lock:
            return self._db.execute(
                f"SELECT key, stage, state, changed_at FROM tasks WHERE changed_at > ? AND stage IN ({marks}) ORDER BY changed_at",
                (since, *stages),
            ).fetchall()

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
