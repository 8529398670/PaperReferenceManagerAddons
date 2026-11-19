"""Every library the server reads: its own (config.yaml), and the ZoteroWebDAV
server any user connected on the Account screen (app/models/user_library.py).

A request is answered from its user's library (for_user): their own if they
set one, else the server's. Each user's library has a folder of its own,
<cache>/libraries/u<id>/, holding its index (search.db), the remote mirror and
the PDFs fetched so far; the server's library keeps the paths it always had.

What is worked out for a paper is not per library: app/content keeps one set
of results per paper key, for everyone. It reads every library at once through
Union, which looks like one Catalogue: each paper once, from one copy -- the
server's library first, then users' by id -- so two copies of a paper never
re-queue each other's work, and a paper leaves the results only when no
library holds it any more.

A user's library is loaded from its index when the server starts or when it
is first asked for, so its papers count for app/content from then on. Its
watcher (the look at the remote server) runs only while someone uses it:
started by a request, paused after IDLE_SECONDS without one and without an
open stream. At most library.max_user_libraries watch at once; past that the
longest idle one is paused. A user's library never holds a request open at
the server (RemoteLibrary.long_poll), so the threads they take stay bounded.
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.core.config import Config
from app.core.config_live import Holder
from app.core.db import Store
from app.library.catalogue import Catalogue, Paper, Status
from app.library.remote import Remote
from app.library.service import LibraryService, open_remote
from app.models import user_library, users
from app.models.users import User

LIBRARIES_DIR = "libraries"
IDLE_SECONDS = 30 * 60
REAP_SECONDS = 60
# How long a library that was removed (its user cleared it, changed it, or
# was deleted) still counts for app/content, so the results of its papers
# are not dropped at once -- the same grace as a paper gone from a library
# (catalogue.VANISHED_KEEP_SECONDS).
RETIRED_KEEP_SECONDS = 30 * 86400


def _fingerprint(source: user_library.Source) -> str:
    return hashlib.sha256(f"{source.url}\n{source.key}\n{source.name}".encode("utf-8")).hexdigest()


class _Entry:
    def __init__(self, service: LibraryService, fingerprint: str) -> None:
        self.service = service
        self.fingerprint = fingerprint
        self.used = time.monotonic()


class LibraryRegistry:
    def __init__(self, cfg: Config, settings: Holder, store: Store, server: LibraryService) -> None:
        self.cfg = cfg
        self.settings = settings
        self.store = store
        self.server = server
        self.root = cfg.library.index_path.parent / LIBRARIES_DIR
        self._entries: dict[int, _Entry] = {}
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reaper: asyncio.Task[None] | None = None
        # key -> when a removed library last held it (RETIRED_KEEP_SECONDS).
        self._retired: dict[str, float] = {}
        # Hooks main sets: what the server library's after_sync and
        # text_fallback do, for every user library too.
        self.after_sync: Callable[[], None] | None = None
        self.text_fallback: Callable[[str], str] | None = None
        self.union = Union(self)
        # Replaced in tests: the remote a user's source is read through.
        self.remote_factory: Callable[[user_library.Source], Remote] = lambda s: Remote(s.url, s.key, s.name)
        # Replaced in tests: whether an address may be used (public_host).
        self.host_ok: Callable[[str], bool] = user_library.public_host

    # -- which library -------------------------------------------------------

    def folder(self, user_id: int) -> Path:
        return self.root / f"u{int(user_id)}"

    def for_user(self, user: User | None, start: bool = True) -> LibraryService:
        """The library this user reads: their own, else the server's. A user
        whose own library cannot be opened (an address no longer allowed)
        reads the server's, and their status says why."""
        if user is None:
            return self.server
        source = user_library.source_of(user, self.cfg.secret_key)
        if source is None:
            self._drop(user.id)
            return self.server
        entry = self._entry(user, source)
        if entry is None:
            return self.server
        entry.used = time.monotonic()
        if start and not entry.service.running and self._loop is not None:
            self._start(entry)
        return entry.service

    def own(self, user: User) -> LibraryService | None:
        """The user's own library if one is open, without opening it."""
        with self._lock:
            entry = self._entries.get(user.id)
        return entry.service if entry is not None else None

    def _entry(self, user: User, source: user_library.Source) -> _Entry | None:
        fingerprint = _fingerprint(source)
        with self._lock:
            entry = self._entries.get(user.id)
            if entry is not None and entry.fingerprint == fingerprint:
                return entry
        # Everyone but the owner reads public servers only, checked at every
        # connection (an address can be pointed elsewhere after it was saved).
        if user.id != users.get_owner_id(self.store) and not self.host_ok(source.url):
            self._drop(user.id)
            return None
        with self._lock:
            entry = self._entries.get(user.id)
            if entry is not None and entry.fingerprint == fingerprint:
                return entry
            if entry is not None:
                # Another source: the old one's folder is not this one's.
                self._retire(entry)
                self._dispose(entry)
                shutil.rmtree(self.folder(user.id), ignore_errors=True)
            entry = _Entry(self._build(source), fingerprint)
            self._entries[user.id] = entry
            return entry

    def _build(self, source: user_library.Source) -> LibraryService:
        folder = self.folder(source.user_id)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        library = open_remote(source, folder, self.settings.get().library.remote_poll_seconds, remote=self.remote_factory(source))
        service = LibraryService(self.cfg, library=library, index_path=folder / "search.db", source_id=source.id)
        service.load()
        service.catalogue.text_fallback = self.text_fallback
        service.after_sync = self.after_sync
        return service

    def _drop(self, user_id: int) -> None:
        """The user's library is gone (cleared, or the account deleted):
        closed, its folder removed, its papers kept a while for app/content."""
        with self._lock:
            entry = self._entries.pop(user_id, None)
        if entry is not None:
            self._retire(entry)
            self._dispose(entry)
        if self.folder(user_id).exists():
            shutil.rmtree(self.folder(user_id), ignore_errors=True)
            if self.after_sync is not None:
                self.after_sync()

    def _dispose(self, entry: _Entry) -> None:
        """Stops and closes a library no longer used, on the event loop."""

        def dispose() -> None:
            entry.service.pause()
            entry.service.hub.close()
            entry.service.close()

        self._call(dispose)

    def forget_user(self, user_id: int) -> None:
        self._drop(user_id)

    def _retire(self, entry: _Entry) -> None:
        now = time.time()
        for paper in entry.service.catalogue.all():
            self._retired[paper.key] = now

    # -- running -------------------------------------------------------------

    def _start(self, entry: _Entry) -> None:
        limit = max(1, self.settings.get().library.max_user_libraries)
        with self._lock:
            running = sorted((e for e in self._entries.values() if e.service.running and e is not entry), key=lambda e: e.used)
        for older in running[: max(0, len(running) - limit + 1)]:
            self._call(older.service.pause)
        # Requests are answered in worker threads; the watcher belongs to the
        # server's event loop.
        try:
            in_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            in_loop = False
        if in_loop:
            entry.service.start(self.settings)
        elif self._loop is not None:
            self._loop.call_soon_threadsafe(entry.service.start, self.settings)

    def load_all(self) -> None:
        """Every user library is loaded (not watched), so app/content knows
        their papers from the start and never takes them for gone."""
        for user in users.list_users(self.store):
            if user.library_url:
                try:
                    self.for_user(user, start=False)
                except Exception as error:  # noqa: BLE001 -- one broken library must not stop the server
                    print(f"[library] user {user.id}'s library could not be opened: {type(error).__name__}", flush=True)

    def _call(self, fn: Callable[[], None]) -> None:
        """fn on the server's event loop, from any thread."""
        try:
            in_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            in_loop = False
        if in_loop or self._loop is None:
            fn()
        else:
            self._loop.call_soon_threadsafe(fn)

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.load_all()
        self._reaper = asyncio.create_task(self._reap())

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(REAP_SECONDS)
            now = time.monotonic()
            with self._lock:
                entries = list(self._entries.values())
            for entry in entries:
                if entry.service.running and now - entry.used > IDLE_SECONDS and not entry.service.hub.clients:
                    entry.service.pause()
            cutoff = time.time() - RETIRED_KEEP_SECONDS
            for key, when in list(self._retired.items()):
                if when < cutoff:
                    self._retired.pop(key, None)

    async def stop(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
        with self._lock:
            entries = list(self._entries.values())
        for entry in entries:
            await entry.service.stop()

    def close(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.service.close()

    # -- every library -------------------------------------------------------

    def services(self) -> list[LibraryService]:
        """The server's library first, then users' by id: the order a paper's
        copy is chosen in (Union)."""
        with self._lock:
            return [self.server] + [self._entries[uid].service for uid in sorted(self._entries)]

    def holding(self, key: str) -> list[LibraryService]:
        return [service for service in self.services() if service.catalogue.get(key) is not None]

    def publish(self, name: str, data: dict[str, Any]) -> None:
        """An event for every library's stream (a paper's results moved on:
        whoever has it open hears)."""
        for service in self.services():
            service.publish(name, data)

    def retired(self) -> set[str]:
        return set(self._retired)


class Union:
    """Every library as one catalogue, for app/content: the reading half of
    Catalogue that the content queue uses."""

    def __init__(self, registry: LibraryRegistry) -> None:
        self.registry = registry

    @property
    def library(self) -> Any:
        return self.registry.server.catalogue.library

    @property
    def status(self) -> Status:
        # Users' libraries are loaded from their index before they count, so
        # the server's library is the one to wait for.
        return self.registry.server.catalogue.status

    @property
    def synced(self) -> bool:
        return getattr(self.registry.server.catalogue, "synced", True)

    def all(self) -> list[Paper]:
        seen: dict[str, Paper] = {}
        for service in self.registry.services():
            for paper in service.catalogue.all():
                seen.setdefault(paper.key, paper)
        return list(seen.values())

    def get(self, key: str) -> Paper | None:
        for service in self.registry.services():
            paper = service.catalogue.get(key)
            if paper is not None:
                return paper
        return None

    def owner_of(self, key: str) -> LibraryService | None:
        """The library whose copy of the paper is the one used."""
        for service in self.registry.services():
            if service.catalogue.get(key) is not None:
                return service
        return None

    def vanished(self) -> set[str]:
        out = self.registry.retired()
        for service in self.registry.services():
            out |= service.catalogue.vanished()
        return out

    def put_text(self, key: str, text: str) -> None:
        for service in self.registry.holding(key):
            service.catalogue.put_text(key, text)

