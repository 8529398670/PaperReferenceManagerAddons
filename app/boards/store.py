"""Lists, stored: one record per list in the boards bucket, its past versions
in board_versions.

A list's record is {slug, name, rev, locked, created_at, created_by,
updated_at, updated_by, doc}, where doc is the board document app/boards/board.py
describes. Every change is a batch of ops (app/boards/ops.py) applied inside one
write transaction: the batch either all lands, as one new rev, or none of it
does. The version it replaced is kept (the newest KEEP_VERSIONS per list),
which is what restoring an old version and undoing a bulk change read from.

There is no whole-document save, so there is nothing to merge: two tabs, an
agent and a script all send ops against the current document, and if_rev is
there for a caller that wants "only if nothing changed since I looked".
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from app.boards import board, ops
from app.core import db
from app.models import to_iso, utc_now

MAIN = "main"
KEEP_VERSIONS = 40
MAX_NAME = 80
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class BoardError(Exception):
    """A request about a list that cannot be done, worded for the caller.
    status is the HTTP status it answers with."""

    def __init__(self, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.extra = extra


@dataclass
class Applied:
    rev: int
    results: list[dict[str, Any]]
    doc: dict[str, Any]
    changed: bool


def slug_for(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")[:48] or "list"


def _version_key(slug: str, rev: int) -> str:
    return f"{slug}:{rev:012d}"


def summary(record: dict[str, Any]) -> dict[str, Any]:
    doc = record.get("doc") or {}
    return {
        "slug": record["slug"],
        "name": record.get("name", record["slug"]),
        "rev": record.get("rev", 0),
        "locked": bool(record.get("locked")),
        "count": len(doc.get("items") or []),
        "shelf": len(doc.get("staging") or []),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def list_boards(store: db.Store) -> list[dict[str, Any]]:
    """Every list, the main one first, then oldest first."""
    rows = [summary(record) for _, record in store.all(db.BUCKET_BOARDS) if not record.get("deleted")]
    rows.sort(key=lambda row: (row["slug"] != MAIN, row.get("created_at") or ""))
    return rows


def get_board(store: db.Store, slug: str) -> dict[str, Any] | None:
    record = store.get(db.BUCKET_BOARDS, slug)
    if record is None or record.get("deleted"):
        return None
    return record


def create_board(store: db.Store, name: str, user_name: str, doc: dict[str, Any] | None = None, slug: str | None = None) -> dict[str, Any]:
    name = (name or "").strip()[:MAX_NAME]
    if not name:
        raise BoardError("a list needs a name")
    base = slug or slug_for(name)
    now = to_iso(utc_now())
    with store.transaction() as tx:
        candidate, n = base, 1
        while tx.get(db.BUCKET_BOARDS, candidate) is not None:
            n += 1
            candidate = f"{base}-{n}"
        record = {
            "slug": candidate,
            "name": name,
            "rev": 1,
            "locked": False,
            "created_at": now,
            "created_by": user_name,
            "updated_at": now,
            "updated_by": user_name,
            "doc": board.normalize(doc if doc is not None else board.default_doc()),
        }
        tx.put(db.BUCKET_BOARDS, candidate, record)
    return record


def apply_ops(
    store: db.Store,
    slug: str,
    batch: Any,
    ctx: ops.Ctx,
    user_name: str,
    if_rev: int | None = None,
    dry_run: bool = False,
) -> Applied:
    """Run a batch of ops against a list, atomically. Raises BoardError."""
    if not isinstance(batch, list):
        raise BoardError("`ops` must be a list")
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None or record.get("deleted"):
            raise BoardError(f"no list {slug!r}", 404)
        if record.get("locked") and not dry_run:
            raise BoardError("this list is view-only -- unlock it to change it", 403)
        rev = int(record.get("rev", 0))
        if if_rev is not None and if_rev != rev:
            raise BoardError("the list changed since you read it", 409, rev=rev)
        before = record["doc"]
        doc = copy.deepcopy(before)
        try:
            results = ops.apply_ops(doc, ctx, batch)
        except ops.OpFailure as failure:
            raise BoardError(failure.msg, 400, index=failure.index, op=failure.op) from None
        doc = board.normalize(doc)
        changed = doc != before
        if dry_run or not changed:
            return Applied(rev=rev, results=results, doc=doc, changed=False)
        now = to_iso(utc_now())
        tx.put(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev), {"slug": slug, "rev": rev, "at": record.get("updated_at"), "by": record.get("updated_by"), "doc": before})
        record["doc"] = doc
        record["rev"] = rev + 1
        record["updated_at"] = now
        record["updated_by"] = user_name
        tx.put(db.BUCKET_BOARDS, slug, record)
        _drop_old_version(tx, slug, rev)
        return Applied(rev=rev + 1, results=results, doc=doc, changed=True)


def _drop_old_version(tx: db.Transaction, slug: str, rev: int) -> None:
    # Each change keeps exactly one version, the one at `rev`, so dropping the
    # one KEEP_VERSIONS before it keeps the newest KEEP_VERSIONS without
    # reading any of them.
    if rev - KEEP_VERSIONS > 0:
        tx.delete(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev - KEEP_VERSIONS))


def replace_doc(store: db.Store, slug: str, doc: dict[str, Any], user_name: str) -> int:
    """Put a whole document in place (an import), keeping the old one as a
    version like any other change. Answers the new rev."""
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None:
            raise BoardError(f"no list {slug!r}", 404)
        rev = int(record.get("rev", 0))
        tx.put(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev), {"slug": slug, "rev": rev, "at": record.get("updated_at"), "by": record.get("updated_by"), "doc": record["doc"]})
        record["doc"] = board.normalize(doc)
        record["rev"] = rev + 1
        record["updated_at"] = to_iso(utc_now())
        record["updated_by"] = user_name
        tx.put(db.BUCKET_BOARDS, slug, record)
        _drop_old_version(tx, slug, rev)
        return rev + 1
