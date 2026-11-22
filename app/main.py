"""The web server. This module only wires things together -- load config,
resolve assets, open the database, build the app, start and stop cleanly.
Every decision of substance lives in a module under app/core/, app/models/,
or app/routes/. If you find yourself adding business logic here, it belongs
in a route module or a new core module instead.

Started by `python -m app` (see app/__main__.py), never by pointing uvicorn
at it from the command line: host, port, and every other setting come from
config.yaml, and a second place to pass them would be a second source of
truth.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.core import assets, bootstrap, config, config_live, db, graceful, housekeeping, jobs, language, live_reload, logs, server_lock
from app.core import sse
from app.core.maintenance import Maintenance
from app.core.middleware import EXCEPTION_HANDLERS, AppVersion, NoStore, RateLimit, SecurityHeaders
from app.core.request_id import RequestID
from app.core.request_log import RequestLog
from app.core.security import LoadActor, ViewOnly
from app.core.static_files import StaticServer
from app.boards.service import BoardService
from app.boards.sheetsync import SheetSync
from app.content.enrich import Enricher
from app.content.figures import Figures
from app.content.screens import Screens, memberships
from app.content.service import ContentService
from app.extras.crawl import Crawler
from app.extras.searches import SavedSearches
from app.extras.summaries import Summaries
from app.library.service import LibraryService
from app.library.registry import LibraryRegistry
from app.review.missing import MissingReview
from app.review.service import ReviewService
from app.review.view import ReviewView
from app.core.skill_origin import skill_origin
from app.routes import build_routes

# How often config.yaml is checked for edits made outside the Settings screen.
CONFIG_POLL_SECONDS = 2


async def config_watch(settings: config_live.Holder) -> None:
    """Apply edits to config.yaml made by hand, or by `config set`, while the
    server runs. See config_live.Holder.poll."""
    while True:
        await asyncio.sleep(CONFIG_POLL_SECONDS)
        try:
            await run_in_threadpool(settings.poll)
        except Exception as error:  # noqa: BLE001 -- a bad poll must never take the server down
            print(f"[config] check failed: {error}", flush=True)


def build_app(
    settings: config_live.Holder,
    store: db.Store,
    lang: language.Language,
    static_server: StaticServer,
    version: str = "dev",
    reload_watcher: live_reload.Watcher | None = None,
) -> Starlette:
    # The configuration the server started with: what is set up once (the
    # body limit, the log's routes and directory). Everything read per
    # request comes from settings, which follows edits to config.yaml.
    cfg = settings.boot()
    # The activity log writes from its own thread; closing it, last, lets the
    # final requests make it to disk.
    logger = logs.Logger(cfg.logs, cfg.secret_key, cfg.encrypt_at_rest)

    # A change to config.yaml reaches the activity log's own settings, and is
    # reported on stdout and in the log itself.
    settings.on_change(lambda old, new: logger.apply(new.logs))

    def report(level: str, message: str, detail: dict) -> None:
        print(f"[config] {message}", flush=True)
        logger.system(level, message, detail)

    settings.report = report

    registry = jobs.Registry(store, logger)
    housekeeping.register(registry, store, settings, logger)
    log_hub = sse.Hub()
    # The Zotero library and the lists built from it. See app/library/ and
    # app/boards/.
    library = LibraryService(cfg)
    registry.register("library-sync", housekeeping.HOUR_SECONDS, library.sync_job)
    # And every user's own library (the Account screen): a request reads its
    # user's. The content queue reads them all at once (libraries.union).
    libraries = LibraryRegistry(cfg, settings, store, library)
    boards = BoardService(store, library.catalogue)
    registry.register("lists-purge", housekeeping.HOUR_SECONDS, boards.purge_job)
    # Each paper's derived content, queued and filled one paper at a time.
    # See app/content/.
    content = ContentService(
        cfg.library.content_dir, cfg.library.index_path, libraries.union, store,
        cfg.config_file.parent / "modalities.yaml", lambda: settings.get().library,
    )
    def after_sync() -> None:
        content.dirty = True
        boards.library_stale()
        # Papers just saved to Zotero join the lists that asked for them.
        try:
            boards.auto_add()
        except Exception as error:  # noqa: BLE001 -- the sync itself already landed
            print(f"[lists] auto-add failed: {error!r}", flush=True)

    library.after_sync = after_sync
    libraries.after_sync = lambda: setattr(content, "dirty", True)
    # Papers just saved to a user's own library join the lists that asked for
    # them too (the Zotero plugin sends to the sender's own library).
    def user_synced(service: LibraryService) -> None:
        boards.library_stale()
        boards.auto_add(service.catalogue)

    libraries.on_user_sync = user_synced
    boards.content = content
    # The scanned PDFs' text, from the worker's OCR, searched like Zotero's.
    library.catalogue.text_fallback = content.ocr_text
    libraries.text_fallback = content.ocr_text
    # The Figures screen (picks, matches, thumbnails) and the Code / Datasets
    # screens with the GitHub / OSF / archive enrichment behind them.
    figures = Figures(content, store, cfg.config_file.parent / "method-images.txt")
    content.on_figures = figures.forget
    enricher = Enricher(cfg.library.content_dir / "_enrich", lambda: (settings.get().enrich.github_token, settings.get().enrich.osf_token))
    screens = Screens(content, figures, enricher, store)
    # The review screener: papers on a list or with a picked figure, screened
    # as the content queue reaches them. See app/review/.
    review = ReviewService(store, cfg.config_file.parent / "review.yaml", content.files)
    review.candidates_fn = lambda: set(memberships(store)) | set(figures.picks_per_paper())
    content.review = review
    # The Review screen: the candidates as rows, and the missing pool screened
    # on its abstracts in a lane of its own.
    review_view = ReviewView(review, content, figures, store)
    review_missing = MissingReview(review, content.pool)

    def candidates_changed() -> None:
        review.candidates_changed()
        content.dirty = True

    boards.on_changed = candidates_changed
    figures.on_picks = candidates_changed
    screens.publish = libraries.publish
    review_missing.publish = libraries.publish

    def publish(name: str, data: dict) -> None:
        libraries.publish(name, data)
        screens.heard(name, data)
        # A paper's content moved on: the Library list shows its Code, Datasets and badges.
        boards.library_stale()

    content.publish = publish
    # Phase 7: saved searches, the citation-graph crawl, LLM summaries and the
    # Google Sheets mirror. See app/extras/ and app/boards/sheetsync.py.
    searches = SavedSearches(store, library.catalogue, lambda: content.pool, content.skipped)
    crawler = Crawler(cfg.library.content_dir / "_crawl", content, library.catalogue, searches,
                      lambda: settings.get().library.openalex_api_key, library.publish)
    summaries = Summaries(store, library.catalogue, content, cfg.config_file.parent / "llm-prompts",
                          cfg.config_file.parent / "rollup-extra-columns.yaml", lambda: settings.get().llm, library.publish)
    sheets = SheetSync(boards, lambda: settings.get().google_sheets)
    boards.listeners.append(sheets.heard)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        logger.on_flushed = lambda: sse.publish_from_thread(loop, log_hub, sse.CHANGED)
        logger.start()
        logger.system(logs.LEVEL_INFO, "server started", {"version": version})
        if cfg.secret_migrated:
            logger.system(logs.LEVEL_WARN, "secret key moved to secret.key", {"config": str(cfg.config_file), "secret": str(cfg.secret_file)})
        watcher = asyncio.create_task(config_watch(settings))
        library.start(settings)
        libraries.start()
        content.start()
        screens.start()
        review_missing.start()
        boards.start()
        summaries.start()
        sheets.start()
        registry.start()
        try:
            yield
        finally:
            # By now requests have finished and streams have ended (serve's
            # on_stop). Jobs next, since they write to the log; the log last.
            watcher.cancel()
            await library.stop()
            await libraries.stop()
            await content.stop()
            await screens.stop()
            await review_missing.stop()
            boards.stop()
            crawler.stop()
            await run_in_threadpool(summaries.stop)
            await run_in_threadpool(sheets.stop)
            await registry.stop()
            log_hub.close()
            await run_in_threadpool(library.close)
            await run_in_threadpool(libraries.close)
            await run_in_threadpool(content.close)
            logger.on_flushed = None
            logger.system(logs.LEVEL_INFO, "server stopped")
            await run_in_threadpool(logger.close)

    app = Starlette(
        routes=build_routes(static_server, reload_watcher),
        # Outermost first. Every request gets its reference and is counted,
        # whatever becomes of it; headers go on everything; the body limit is
        # here rather than Starlette's max_body_size= because that one sits
        # outside all of this, and its 413 would have neither; the rate limit
        # runs before anything touches the database, so a flood is cheap to
        # refuse; then the caller is resolved once for every route behind it;
        # then each request is written to the activity log, knowing who made
        # it; and only then can maintenance mode refuse it, knowing who asked.
        middleware=[
            Middleware(RequestID),
            Middleware(NoStore),
            Middleware(AppVersion, version=version),
            Middleware(SecurityHeaders, settings=settings),
            Middleware(RequestBodyLimitMiddleware, max_body_size=cfg.body_limit_bytes),
            Middleware(RateLimit, settings=settings, logger=logger),
            Middleware(LoadActor, store=store, settings=settings),
            Middleware(RequestLog, settings=settings, logger=logger),
            Middleware(ViewOnly),
            Middleware(Maintenance, store=store, settings=settings),
        ],
        exception_handlers=EXCEPTION_HANDLERS,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.logs = logger
    app.state.jobs = registry
    app.state.log_hub = log_hub
    app.state.library = library
    app.state.libraries = libraries
    app.state.boards = boards
    app.state.content = content
    app.state.figures = figures
    app.state.screens = screens
    app.state.review = review
    app.state.review_view = review_view
    app.state.review_missing = review_missing
    app.state.searches = searches
    app.state.crawler = crawler
    app.state.summaries = summaries
    app.state.sheets = sheets
    app.state.language = lang
    # Reported to MCP clients as serverInfo.version.
    app.state.version = version
    # Reported by /api/me, so ProjectPortal can tell an app behind its template.
    app.state.skill, app.state.skill_commit = skill_origin()
    app.state.live_reload = reload_watcher
    return app


def close_streams(app: Starlette) -> None:
    """End every open stream, so none uses up the graceful timeout."""
    app.state.log_hub.close()
    app.state.library.hub.close()
    app.state.boards.hub.close()


def serve(version: str) -> None:
    cfg = config.load()
    if cfg.rotation_pending:
        raise RuntimeError(config.ROTATION_PENDING_MESSAGE)
    if cfg.rotation_finished:
        print(f"[secret] finished a key rotation that had been cut short; the new key is in {cfg.secret_file}", flush=True)
    # Held until the process ends. See app/core/server_lock.py.
    lock = server_lock.acquire(cfg.app_dir / config.SERVER_LOCK_NAME, timeout_seconds=5)
    if lock is None:
        raise RuntimeError(f"another server is already running on {cfg.app_dir}")
    # Everything in static_dir is public, so it may not be, hold, or sit
    # inside the config or state directory. See app/core/assets.py.
    assets.check_static_dir(cfg.static_dir, cfg.config_file.parent, cfg.app_dir, cfg.secret_file, cfg.database_path)
    bundle = assets.resolve(cfg.static_dir, cfg.language_file)
    store = db.open_store(cfg.database_path, cfg.secret_key, cfg.encrypt_at_rest)
    lang = language.parse(bundle.language_yaml)
    static_server = StaticServer(bundle.static_dir)

    bootstrap.ensure_first_admin(store, cfg, "Admin")

    # Tell open pages about a change to the frontend (server.live_reload).
    # See app/core/live_reload.py.
    reload_watcher = live_reload.Watcher(bundle.static_dir) if cfg.live_reloads(version) else None
    app = build_app(config_live.Holder(cfg), store, lang, static_server, version, reload_watcher)

    print(f"[start] {cfg.project_name} {version} listening on {cfg.listen_address} (secure cookies: {cfg.secure_cookies})")
    print(f"[url]    {cfg.url}  (from {cfg.url_source})")
    if cfg.config_created:
        print(f"[config] {cfg.config_file} (created; edits apply while the server runs)")
    else:
        print(f"[config] {cfg.config_file} (edits apply while the server runs)")
    if cfg.secret_migrated:
        print(f"[secret] {cfg.secret_file}")
        print("[secret] ================================================================")
        print(f"[secret] MOVED server.secret_key out of {cfg.config_file}")
        print(f"[secret] into {cfg.secret_file} (mode 0600). config.yaml holds no secret now.")
        print("[secret] Back secret.key up with the database: nothing else can read it.")
        print("[secret] ================================================================")
    elif cfg.secret_created:
        print(f"[secret] {cfg.secret_file} (created, with a new key -- back it up)")
    else:
        print(f"[secret] {cfg.secret_file}")
    if cfg.config_warning:
        print(f"[config] warning: {cfg.config_warning}")
    print(f"[state]  {cfg.app_dir}")
    if cfg.logs.enabled:
        print(f"[logs]   {cfg.logs.dir} (keeping {cfg.logs.retention_days} days, up to {cfg.logs.max_total_bytes // 1024 // 1024} MB)")
    print(f"[assets] {bundle.source}", flush=True)

    def stop_waiting() -> None:
        """Before uvicorn waits for connections: it would otherwise wait the
        full 10 seconds for a request that is never going to finish."""
        close_streams(app)
        if reload_watcher is not None:
            reload_watcher.close()

    graceful.run(
        app,
        on_stop=stop_waiting,
        host=cfg.host,
        port=cfg.port,
        # An empty Server header keeps the response from advertising which
        # server and version is running -- free reconnaissance otherwise.
        server_header=False,
        # Proxy trust is server.trust_proxy, applied by the rate limiter's
        # client_ip(); uvicorn's own X-Forwarded-For handling would be a
        # second, differently configured answer to the same question.
        proxy_headers=False,
        # Idle keep-alive connections are dropped rather than held until the
        # process runs out of sockets; in-flight requests get 10s to finish
        # on shutdown so the database is never left mid-write.
        timeout_keep_alive=75,
        timeout_graceful_shutdown=10,
        lifespan="on",
        log_level="info",
        # Every request is in the activity log already, and with logs.echo
        # on, a one-line summary goes to stdout from there (with the real
        # client address and who it was); uvicorn's own line would repeat it.
        access_log=False,
    )
