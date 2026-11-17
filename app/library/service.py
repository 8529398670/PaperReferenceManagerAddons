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
from typing import Any, Callable

from app.core import graceful, sse
from app.core.config import Config
from app.core.config_live import Holder
from app.library.catalogue import Catalogue
from app.library.zotero import Library
from app.search.index import Index


class LibraryService:
    def __init__(self, cfg: Config) -> None:
        library = Library(cfg.library.zotero_dir, cfg.library.index_path.parent)
        self.index = Index(cfg.library.index_path)
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
            await asyncio.sleep(settings.get().library.watch_seconds)

    def start(self, settings: Holder) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._watch(settings))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.hub.close()

    def close(self) -> None:
        self.index.close()

    def sync_job(self) -> tuple[str, str]:
        """The library-sync job: a full look, whether or not Zotero committed."""
        result = self._load_and_sync(force=True)
        if result is None:
            return "already running" if not self.catalogue.status.error else "", self.catalogue.status.error
        return result.note(), ""
