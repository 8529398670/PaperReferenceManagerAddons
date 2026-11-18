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
MAX_SLUG = 48
# A deleted list stays restorable this long; the purge job removes it after.
PURGE_DAYS = 30
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
    before: dict[str, Any] | None = None


def slug_for(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")[:MAX_SLUG].rstrip("-") or "list"


def clean_name(name: str) -> str:
    """One line, trimmed, at most MAX_NAME characters."""
    return re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]


# Words the routes use after /api/lists/, which no list may be called.
# "library" is the Lists picker's built-in Library entry (static/js/lists.js).
RESERVED = {"schema", "stream", "deleted", "library"}


def _free_slug(tx: db.Transaction, base: str) -> str:
    """base, or base-2, base-3 ... -- the first no list (deleted ones too) is
    using."""
    if base in RESERVED:
        base = f"{base}-list"
    candidate, n = base, 1
    while tx.get(db.BUCKET_BOARDS, candidate) is not None:
        n += 1
        tail = f"-{n}"
        candidate = base[: MAX_SLUG - len(tail)].rstrip("-") + tail
    return candidate


def _drop_alias(tx: db.Transaction, slug: str) -> None:
    """A list now living at `slug` wins over an old link that redirected there."""
    for key, record in tx.all(db.BUCKET_BOARDS):
        if slug in (record.get("aliases") or []):
            record["aliases"] = [a for a in record["aliases"] if a != slug]
            tx.put(db.BUCKET_BOARDS, key, record)


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
        "copied_from": record.get("copied_from") or "",
        "sync": ((doc.get("options") or {}).get("sync")) or "two-way",
        "sections": bool(doc.get("sections")),
        # The built-in Library (app/boards/service.py): read-only, never stored.
        **({"builtin": True} if record.get("builtin") else {}),
        **({"deleted_at": record.get("deleted_at"), "deleted_by": record.get("deleted_by") or ""} if record.get("deleted") else {}),
    }


def list_boards(store: db.Store) -> list[dict[str, Any]]:
    """Every list, the main one first, then oldest first."""
    rows = [summary(record) for _, record in store.all(db.BUCKET_BOARDS) if not record.get("deleted")]
    rows.sort(key=lambda row: (row["slug"] != MAIN, row.get("created_at") or ""))
    return rows


def deleted_boards(store: db.Store) -> list[dict[str, Any]]:
    """The lists in the trash, most recently deleted first."""
    rows = [summary(record) for _, record in store.all(db.BUCKET_BOARDS) if record.get("deleted")]
    rows.sort(key=lambda row: row.get("deleted_at") or "", reverse=True)
    return rows


def get_board(store: db.Store, slug: str) -> dict[str, Any] | None:
    record = store.get(db.BUCKET_BOARDS, slug)
    if record is None or record.get("deleted"):
        return None
    return record


def alias_target(store: db.Store, slug: str) -> str | None:
    """The slug a list renamed away from `slug` lives at now, or None."""
    for key, record in store.all(db.BUCKET_BOARDS):
        if slug in (record.get("aliases") or []) and not record.get("deleted"):
            return key
    return None


def find_board(store: db.Store, slug: str) -> dict[str, Any]:
    """The list at `slug`, following a rename. Raises BoardError: 410 for a
    deleted list, 404 for none."""
    record = store.get(db.BUCKET_BOARDS, slug)
    if record is not None and not record.get("deleted"):
        return record
    moved = alias_target(store, slug)
    if moved is not None:
        found = get_board(store, moved)
        if found is not None:
            return found
    if record is not None:
        raise BoardError(f"the list {slug!r} was deleted", 410)
    raise BoardError(f"no list {slug!r}", 404)


def copy_doc(doc: dict[str, Any], keys: list[str] | None = None) -> dict[str, Any]:
    """A list's document to start a new list from: all of it, or only the rows
    `keys` names (in this list's order, no shelf), keeping only the tags
    those rows use."""
    out = copy.deepcopy(doc)
    if keys is None:
        return out
    wanted = set(keys)
    out["items"] = [row for row in out.get("items") or [] if row.get("key") in wanted]
    out["staging"] = []
    used = {str(tag).lower() for row in out["items"] for tag in row.get("tags") or []}
    vocab = out.setdefault("vocab", {})
    vocab["tags"] = [tag for tag in vocab.get("tags") or [] if str(tag.get("name", "")).lower() in used]
    return out


def create_board(
    store: db.Store, name: str, user_name: str, doc: dict[str, Any] | None = None, slug: str | None = None, copied_from: str = "",
) -> dict[str, Any]:
    name = clean_name(name)
    if not name:
        raise BoardError("a list needs a name")
    base = slug or slug_for(name)
    now = to_iso(utc_now())
    with store.transaction() as tx:
        candidate = _free_slug(tx, base)
        _drop_alias(tx, candidate)
        record = {
            "slug": candidate,
            "name": name,
            "rev": 1,
            "locked": False,
            "created_at": now,
            "created_by": user_name,
            "updated_at": now,
            "updated_by": user_name,
            "copied_from": copied_from,
            "aliases": [],
            "doc": board.normalize(doc if doc is not None else board.default_doc()),
        }
        tx.put(db.BUCKET_BOARDS, candidate, record)
    return record


def rename_board(store: db.Store, slug: str, name: str, user_name: str) -> dict[str, Any]:
    """A new name, and the slug it makes: the list (and its kept versions)
    moves there, and the old slug becomes an alias so a link sent before still
    lands. The main list keeps its slug (its name can change)."""
    name = clean_name(name)
    if not name or not _SLUG_RE.sub("", name.lower()):
        raise BoardError("a list needs a name with at least one letter or digit in it")
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None or record.get("deleted"):
            raise BoardError(f"no list {slug!r}", 404)
        record["name"] = name
        base = slug_for(name)
        if slug == MAIN or base == slug:
            tx.put(db.BUCKET_BOARDS, slug, record)
            return record
        new = _free_slug(tx, base)
        _drop_alias(tx, new)
        record["slug"] = new
        record["aliases"] = [a for a in (record.get("aliases") or []) + [slug] if a != new][-20:]
        tx.put(db.BUCKET_BOARDS, new, record)
        tx.delete(db.BUCKET_BOARDS, slug)
        rev = int(record.get("rev", 0))
        for older in range(rev - 1, max(0, rev - 1 - KEEP_VERSIONS), -1):
            kept = tx.get(db.BUCKET_BOARD_VERSIONS, _version_key(slug, older))
            if kept is not None:
                kept["slug"] = new
                tx.put(db.BUCKET_BOARD_VERSIONS, _version_key(new, older), kept)
                tx.delete(db.BUCKET_BOARD_VERSIONS, _version_key(slug, older))
        return record


def delete_board(store: db.Store, slug: str, user_name: str) -> dict[str, Any]:
    """Into the trash: gone from the picker and its link, versions kept,
    restorable for PURGE_DAYS. The main list cannot be deleted."""
    if slug == MAIN:
        raise BoardError("the main list cannot be deleted")
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None or record.get("deleted"):
            raise BoardError(f"no list {slug!r}", 404)
        record["deleted"] = True
        record["deleted_at"] = to_iso(utc_now())
        record["deleted_by"] = user_name
        tx.put(db.BUCKET_BOARDS, slug, record)
        return record


def undelete_board(store: db.Store, slug: str, user_name: str) -> dict[str, Any]:
    """Out of the trash, at the slug it had."""
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None or not record.get("deleted"):
            raise BoardError(f"no deleted list {slug!r}", 404)
        record.pop("deleted", None)
        record.pop("deleted_at", None)
        record.pop("deleted_by", None)
        tx.put(db.BUCKET_BOARDS, slug, record)
        _drop_alias(tx, slug)
        return record


def purge_deleted(store: db.Store, days: int = PURGE_DAYS) -> int:
    """Remove lists deleted more than `days` ago, with their versions."""
    from datetime import timedelta

    cutoff = to_iso(utc_now() - timedelta(days=days))
    doomed = [key for key, record in store.all(db.BUCKET_BOARDS) if record.get("deleted") and (record.get("deleted_at") or "") < cutoff]
    if not doomed:
        return 0
    prefixes = tuple(slug + ":" for slug in doomed)
    with store.transaction() as tx:
        for slug in doomed:
            tx.delete(db.BUCKET_BOARDS, slug)
        tx.delete_where(db.BUCKET_BOARD_VERSIONS, lambda key, _record: str(key).startswith(prefixes))
    return len(doomed)


def apply_ops(
    store: db.Store,
    slug: str,
    batch: Any,
    ctx: ops.Ctx,
    user_name: str,
    if_rev: int | None = None,
    dry_run: bool = False,
    set_options: dict[str, Any] | None = None,
) -> Applied:
    """Run a batch of ops against a list, atomically. Raises BoardError.
    set_options: options the server sets itself (auto_add_since), written in
    the same rev as the ops."""
    if not isinstance(batch, list):
        raise BoardError("`ops` must be a list")
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None:
            raise BoardError(f"no list {slug!r}", 404)
        if record.get("deleted"):
            raise BoardError(f"the list {slug!r} was deleted", 410)
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
        if set_options:
            doc.setdefault("options", {}).update(set_options)
        doc = board.normalize(doc)
        changed = doc != before
        if dry_run or not changed:
            return Applied(rev=rev, results=results, doc=doc, changed=False)
        now = to_iso(utc_now())
        keep_version(tx, record)
        record["doc"] = doc
        record["rev"] = rev + 1
        record["updated_at"] = now
        record["updated_by"] = user_name
        tx.put(db.BUCKET_BOARDS, slug, record)
        return Applied(rev=rev + 1, results=results, doc=doc, changed=True, before=before)


def keep_version(tx: db.Transaction, record: dict[str, Any]) -> None:
    """Keep the document `record` holds now as the version at its rev, about
    to be replaced, and let the oldest one go."""
    slug, rev = record["slug"], int(record.get("rev", 0))
    tx.put(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev), {"slug": slug, "rev": rev, "at": record.get("updated_at"), "by": record.get("updated_by"), "doc": record["doc"]})
    _drop_old_version(tx, slug, rev)


def _drop_old_version(tx: db.Transaction, slug: str, rev: int) -> None:
    # Each change keeps exactly one version, the one at `rev`, so dropping the
    # one KEEP_VERSIONS before it keeps the newest KEEP_VERSIONS without
    # reading any of them.
    if rev - KEEP_VERSIONS > 0:
        tx.delete(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev - KEEP_VERSIONS))


def replace_doc(store: db.Store, slug: str, doc: dict[str, Any], user_name: str) -> int:
    """Put a whole document in place (an import), keeping the old one as a
    version like any other change. Answers the new rev."""
    return replace_doc_full(store, slug, doc, user_name)[0]


def replace_doc_full(store: db.Store, slug: str, doc: dict[str, Any], user_name: str) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """replace_doc, answering (new rev, the document before, after)."""
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None:
            raise BoardError(f"no list {slug!r}", 404)
        rev = int(record.get("rev", 0))
        before = record["doc"]
        keep_version(tx, record)
        record["doc"] = board.normalize(doc)
        record["rev"] = rev + 1
        record["updated_at"] = to_iso(utc_now())
        record["updated_by"] = user_name
        tx.put(db.BUCKET_BOARDS, slug, record)
        return rev + 1, before, record["doc"]


def _version_summary(version: dict[str, Any]) -> dict[str, Any]:
    doc = version.get("doc") or {}
    return {
        "rev": version["rev"],
        "at": version.get("at"),
        "by": version.get("by") or "",
        "rows": len(doc.get("items") or []),
        "shelf": len(doc.get("staging") or []),
    }


def history(store: db.Store, slug: str) -> list[dict[str, Any]]:
    """The kept versions of a list, newest first: {rev, at, by, rows, shelf}.
    Version N is the document as it stood at rev N, before the change that
    made rev N+1. Read by key, newest down, so it never scans the bucket."""
    record = find_board(store, slug)
    slug = record["slug"]
    rev = int(record.get("rev", 0))
    out = []
    for older in range(rev - 1, max(0, rev - 1 - KEEP_VERSIONS), -1):
        version = store.get(db.BUCKET_BOARD_VERSIONS, _version_key(slug, older))
        if version is not None:
            out.append(_version_summary(version))
    return out


def version(store: db.Store, slug: str, rev: int) -> dict[str, Any]:
    """One kept version in full: its summary plus doc."""
    slug = find_board(store, slug)["slug"]
    found = store.get(db.BUCKET_BOARD_VERSIONS, _version_key(slug, rev))
    if found is None:
        raise BoardError(f"version {rev} of {slug!r} is not kept", 404)
    return {**_version_summary(found), "doc": found.get("doc") or {}}


def restore(store: db.Store, slug: str, rev: int, user_name: str) -> int:
    """Put a kept version back as one NEW version (the current one is kept
    first, so a restore is itself undoable). Refused while the list is
    view-only. Answers the new rev."""
    return restore_full(store, slug, rev, user_name)[0]


def restore_full(store: db.Store, slug: str, rev: int, user_name: str) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """restore, answering (new rev, the document before, after)."""
    record = find_board(store, slug)
    slug = record["slug"]
    if record.get("locked"):
        raise BoardError("this list is view-only -- unlock it to change it", 403)
    old = version(store, slug, rev)
    return replace_doc_full(store, slug, old["doc"], user_name)


def set_locked(store: db.Store, slug: str, locked: bool, user_name: str) -> dict[str, Any]:
    """Make a list view-only for everyone, or editable again. Not a change to
    its document, so its rev stays put and no version is kept."""
    with store.transaction() as tx:
        record = tx.get(db.BUCKET_BOARDS, slug)
        if record is None or record.get("deleted"):
            raise BoardError(f"no list {slug!r}", 404)
        record["locked"] = bool(locked)
        record["locked_by"] = user_name
        record["locked_at"] = to_iso(utc_now())
        tx.put(db.BUCKET_BOARDS, slug, record)
        return record
