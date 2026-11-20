"""The running library: the catalogue, the watcher that keeps it in step with
Zotero, and the live stream that tells open pages when it moved.

The watcher is a loop of its own rather than a job (app/core/jobs.py) because
jobs tick every 30 seconds and a paper saved in Zotero should show up in two;
config_watch in main.py is the same kind of loop. A job is still registered
("library-sync") so the owner's Jobs screen shows how the last full check went
and can start one by hand.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from app.core import graceful, sse
from app.core.config import Config
from app.core.config_live import Holder
from app.library.catalogue import Catalogue
from app.library.remote import Remote, RemoteLibrary
from app.library.zotero import Library
from app.models.user_library import Source, server_source
from app.search.index import Index


NO_LIBRARY_ERROR = "connect your own ZoteroWebDAV server on the Account screen to see papers"


class NoLibrary:
    """No papers, and a word on what to do: the server's library with
    library.source none, and the library of a user who may not read the
    server's and has not connected their own (app/library/registry.py)."""

    error = NO_LIBRARY_ERROR
    read_fell_back = False
    sqlite_path = ""

    def stamp(self) -> None:
        return None

    def read(self) -> dict[str, Any]:
        return {}

    def ensure_pdf(self, path: Any) -> None:
        return None


def open_remote(source: Source, folder: Path, poll_seconds: int, remote: Remote | None = None) -> RemoteLibrary:
    """The one way a ZoteroWebDAV library is opened, the server's or a user's
    (app/library/registry.py), its mirror and PDFs in folder. Only the
    server's holds a request open at the remote (RemoteLibrary.long_poll): a
    user's polls, so the threads users' libraries take stay bounded."""
    library = RemoteLibrary(remote or Remote(source.url, source.key, source.name), folder, poll_seconds)
    library.long_poll = source.user_id == 0
    return library


def make_library(cfg: Config) -> Library | RemoteLibrary:
    """library.source picks where the server's papers come from: none (the
    default) has the server read no library of its own."""
    library = cfg.library
    if library.source == "none":
        return NoLibrary()  # type: ignore[return-value]
    if library.source == "remote":
        return open_remote(server_source(cfg), library.index_path.parent, library.remote_poll_seconds)
    return Library(library.zotero_dir, library.index_path.parent)


class LibraryService:
    """One library and what is built on it. The server's library (config.yaml)
    is made from cfg alone; a user's own one (app/library/registry.py) is
    handed its library and index path, in a folder of its own."""

    def __init__(self, cfg: Config, library: Library | RemoteLibrary | None = None, index_path: Path | None = None,
                 source_id: str = "server") -> None:
        library = library if library is not None else make_library(cfg)
        self.library = library
        self.source_id = source_id
        self.index = Index(index_path or cfg.library.index_path)
        self.catalogue = Catalogue(library, self.index)
        self.hub = sse.Hub(max_clients=32)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._loaded = False
        self.catalogue.on_event = self._publish
        # Hears that a look at Zotero found something (or was the first):
        # the content queue works out what to do about it. See app/content/.
        self.after_sync: Callable[[], None] | None = None

    def _publish(self, name: str, data: dict[str, Any]) -> None:
        if self._loop is not None:
            sse.publish_from_thread(self._loop, self.hub, sse.event(name, json.dumps(data)))

    def publish(self, name: str, data: dict[str, Any]) -> None:
        """An event for the library's stream from any thread."""
        self._publish(name, data)

    def _load_and_sync(self, force: bool = False) -> Any:
        first = not self._loaded
        if first:
            self.catalogue.load()
            self._loaded = True
        result = self.catalogue.sync(force=force)
        if isinstance(self.library, NoLibrary):
            # Nothing to wait for: an empty library is ready at once.
            self.catalogue.status.ready = True
        if self.after_sync is not None and (first or (result is not None and result.any())):
            self.after_sync()
        return result

    async def _watch(self, settings: Holder) -> None:
        while True:
            try:
                await graceful.run_abandonable(self._load_and_sync)
            except Exception as error:  # noqa: BLE001 -- one bad read must never stop the watching
                self.catalogue.status.error = str(error)
                print(f"[library] sync failed: {error!r}", flush=True)
            current = settings.get().library
            if isinstance(self.library, RemoteLibrary):
                # The loop still turns every watch_seconds (a forced look
                # from the Jobs screen should not wait); the library itself
                # asks the server only every remote_poll_seconds.
                self.library.poll_seconds = current.remote_poll_seconds
            await asyncio.sleep(current.watch_seconds)

    @property
    def running(self) -> bool:
        return self._task is not None

    def load(self) -> None:
        """What the index holds, without asking the library: a user's library
        is known (its papers kept, app/content) before its watcher starts."""
        if not self._loaded:
            self.catalogue.load()
            self._loaded = True

    def start(self, settings: Holder) -> None:
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._watch(settings))

    def pause(self) -> None:
        """Stops the watcher and keeps everything else: a user's library that
        nobody has looked at for a while (registry.py)."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def stop(self) -> None:
        self.pause()
        self.hub.close()

    def close(self) -> None:
        self.index.close()

    def sync_job(self) -> tuple[str, str]:
        """The library-sync job: a full look, whether or not Zotero committed."""
        if isinstance(self.library, RemoteLibrary):
            self.library.poll_now()
        result = self._load_and_sync(force=True)
        if isinstance(self.library, NoLibrary):
            return "no server library (library.source none)", ""
        if result is None:
            return "already running" if not self.catalogue.status.error else "", self.catalogue.status.error
        return result.note(), ""
