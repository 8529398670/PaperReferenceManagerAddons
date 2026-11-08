"""Bringing the old prma's lists in, once: `manage import-legacy --from
<old output dir>`.

It reads <dir>/cache/sort.json (the main list, imported as "main") and every
<dir>/cache/sort-lists/<slug>/ (sort.json, meta.json, lock.json), and writes
each as a list here, with its rows, order, tags and colours, columns and
staging shelf exactly as they were: the documents have the same shape, so
they go through the same normalize() the old app used. Nothing in the old
folder is changed.

A list already here is left alone unless replace is set; then its document is
replaced, and the one it had is kept as a past version like any other change.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.boards import board, store as boards
from app.core import db

MAIN_NAME = "Main"


@dataclass
class Imported:
    slug: str
    name: str
    rows: int
    shelf: int
    action: str  # "created", "replaced", "skipped"


class LegacyError(Exception):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise LegacyError(f"could not read {path}: {error}") from None


def sources(output_dir: Path) -> list[tuple[str, str, Path, Path]]:
    """(slug, name, sort.json, lock.json) for every old list, main first."""
    cache = output_dir / "cache"
    if not cache.is_dir():
        raise LegacyError(f"{output_dir} has no cache/ folder -- point --from at the old prma's output/ folder")
    found = []
    if (cache / "sort.json").is_file():
        found.append((boards.MAIN, MAIN_NAME, cache / "sort.json", cache / "sort-lock.json"))
    lists_dir = cache / "sort-lists"
    if lists_dir.is_dir():
        for folder in sorted(lists_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith(".") or not (folder / "sort.json").is_file():
                continue
            meta = _read_json(folder / "meta.json") or {}
            name = str(meta.get("name") or folder.name)[: boards.MAX_NAME]
            found.append((folder.name, name, folder / "sort.json", folder / "lock.json"))
    return found


def import_lists(store: db.Store, output_dir: Path, replace: bool = False) -> list[Imported]:
    done = []
    for slug, name, doc_path, lock_path in sources(output_dir):
        doc = board.normalize(_read_json(doc_path))
        locked = bool((_read_json(lock_path) or {}).get("locked"))
        rows, shelf = len(doc["items"]), len(doc["staging"])
        existing = store.get(db.BUCKET_BOARDS, slug)
        if existing is not None and not existing.get("deleted"):
            if not replace:
                done.append(Imported(slug, name, rows, shelf, "skipped"))
                continue
            boards.replace_doc(store, slug, doc, "import")
            action = "replaced"
        else:
            boards.create_board(store, name, "import", doc=doc, slug=slug)
            action = "created"
        if locked:
            store.update_value(db.BUCKET_BOARDS, slug, lambda record: record.update(locked=True))
        done.append(Imported(slug, name, rows, shelf, action))
    return done
