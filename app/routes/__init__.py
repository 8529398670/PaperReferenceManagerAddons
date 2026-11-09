"""The URL map -- the only place that knows every route this server answers.
Read build_routes top to bottom to see the whole surface.

The API stays deliberately small: it covers logging in, managing who can log
in, issuing the API keys that let non-browser callers in, and reading the UI's
text. Everything else an app does belongs in a new module in this package
(server side) and in static/js/ (browser side) -- see
references/architecture.md for where the line sits and why.

Protection comes from where a route is registered. group() attaches guards to
each route it builds, so a protected route cannot be written without its
guard, and the list below is a complete statement of who may call what.
Guards attach per route (Starlette's Route(middleware=...)), not per path
prefix, so a group never leaks onto routes outside it.
"""
from __future__ import annotations

from typing import Callable, Sequence

from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from app.core.config import Config
from app.core.security import RequireAdmin, RequireLogin, RequireSession
from app.core.security import Guard
from app.core.security import RequireOwner
from app.core.security import RequireAPIKey
from app.core.static_files import StaticServer
from app.mcp.protocol import Server as MCPServer
from app.routes import (
    account,
    admin,
    api_keys,
    auth,
    boards,
    library,
    jobs,
    logs,
    mcp_tools,
    meta,
    openapi,
    sessions,
    settings,
    shortcuts,
    team,
    two_factor,
)
from app.routes.api_keys import RequireAPIKeys
from app.routes.helpers import get_config, not_found


class RequireMCP(Guard):
    """Makes /mcp answer 404 while server.mcp or auth.api_keys is off --
    exactly what an unregistered route would say. Checked per request rather
    than by registering /mcp or not, because both can be switched while the
    server runs."""

    def refuse(self, request: Request) -> Response | None:
        cfg = get_config(request)
        if not cfg.mcp_enabled or not cfg.api_keys_enabled:
            return not_found("not found")
        return None


class RequireTwoFactor(Guard):
    """The same for setting up 2FA while auth.two_factor is off. Finishing a
    sign-in is not behind this: one already under way may as well end."""

    def refuse(self, request: Request) -> Response | None:
        return None if get_config(request).two_factor_enabled else not_found("not found")


def group(*guards: type) -> Callable[..., Route]:
    """A route builder whose routes all run behind the given guards, in
    order. Usage: signed_in = group(RequireLogin); signed_in("/api/me", me)."""
    middleware = [Middleware(guard) for guard in guards]

    def route(path: str, endpoint: Callable, methods: Sequence[str] = ("GET",)) -> Route:
        return Route(path, endpoint, methods=list(methods), middleware=middleware)

    return route


def build_routes(static_server: StaticServer, cfg: Config) -> list[BaseRoute]:
    """cfg is the configuration the server started with: it decides only
    what is set up once (the activity log's routes). Everything a request
    reads, it reads from the running configuration."""
    public = group()
    signed_in = group(RequireLogin)
    sessions_only = group(RequireLogin, RequireSession)
    # API keys: any signed-in user manages their own, from a browser session.
    my_keys = group(RequireAPIKeys, RequireLogin, RequireSession)
    # Admin only: deciding who gets in.
    admins = group(RequireAdmin)
    # The two admin routes that hand out a login link also require a browser
    # session. A login link becomes a session, and a session can mint API
    # keys -- so if an admin-scoped key could create accounts or reissue
    # links, a leaked key could turn itself into a fresh session and a fresh
    # key, and revoking the leaked one would not end the compromise. The rule
    # is: an API key may use what an account can do, but it never creates
    # credentials. See RequireSession.
    #
    # Deleting an account requires a session too, for a different reason: it
    # cannot be undone. A leaked admin key can disable accounts, which an
    # admin can reverse; it must not be able to erase them. Who may delete
    # whom (the owner rules) is enforced in credentials.delete_user.
    admin_sessions = group(RequireAdmin, RequireSession)
    # Admin view of every key in the app -- "who has standing access" -- and
    # the ability to revoke or delete someone else's.
    admin_keys = group(RequireAPIKeys, RequireAdmin, RequireSession)
    # The activity log and the Settings screen: the owner only, from a
    # browser session -- not other admins, not any API key, not the signed
    # out; all of them get 404 (see RequireOwner).
    owner = group(RequireOwner)
    # Passwords and 2FA change how an account signs in, so setting them needs
    # a browser session, like the PIN: a key that could set a password could
    # turn itself into a session.
    my_two_factor = group(RequireTwoFactor, RequireLogin, RequireSession)

    routes: list[BaseRoute] = [
        # Public: the login link's page and the call it makes, the UI's text
        # (needed to render the signed-out page at all), and the healthcheck.
        # Opening a login link only shows a page; the link is spent by the
        # POST that page sends when the person confirms. See auth.py.
        public("/login/{credential:path}", static_server.serve_login_page),
        public("/api/login", auth.redeem_login_link, ["POST"]),
        public("/api/login/two-factor", two_factor.finish_sign_in, ["POST"]),
        public("/api/language", meta.get_language),
        public("/api/health", meta.get_health),
        public("/api/ready", meta.get_ready),
        # Any signed-in user.
        signed_in("/api/me", account.me),
        signed_in("/api/account/rename", account.rename, ["POST"]),
        signed_in("/api/account/shortcuts", shortcuts.set_my_shortcuts, ["POST"]),
        # A session only, for the same reason as every route that hands out
        # a login link: the link becomes a session. See admin_sessions above.
        sessions_only("/api/account/login-link", account.create_my_login_link, ["POST"]),
        signed_in("/api/account/login-link/cancel", account.cancel_my_login_link, ["POST"]),
        # The account's own sessions. A session only: a key has none, and
        # signing devices out is a person's decision.
        sessions_only("/api/account/sessions", sessions.list_my_sessions),
        sessions_only("/api/account/sessions/revoke-others", sessions.revoke_others, ["POST"]),
        sessions_only("/api/account/sessions/{session_id}/label", sessions.label_one, ["POST"]),
        sessions_only("/api/account/sessions/{session_id}/revoke", sessions.revoke_one, ["POST"]),
        my_two_factor("/api/account/two-factor/start", two_factor.start_setup, ["POST"]),
        my_two_factor("/api/account/two-factor/confirm", two_factor.confirm_setup, ["POST"]),
        my_two_factor("/api/account/two-factor/disable", two_factor.disable, ["POST"]),
        signed_in("/api/logout", account.logout, ["POST"]),
        signed_in("/api/team", team.list_team),
        signed_in("/api/openapi.json", openapi.get_openapi),
        my_keys("/api/keys", api_keys.list_my_keys),
        my_keys("/api/keys", api_keys.create_my_key, ["POST"]),
        my_keys("/api/keys/{key_id}/rename", api_keys.rename_my_key, ["POST"]),
        my_keys("/api/keys/{key_id}/expiry", api_keys.set_my_key_expiry, ["POST"]),
        my_keys("/api/keys/{key_id}/revoke", api_keys.revoke_my_key, ["POST"]),
        my_keys("/api/keys/{key_id}/delete", api_keys.delete_my_key, ["POST"]),
        my_keys("/api/keys/{key_id}/restore", api_keys.restore_my_key, ["POST"]),
        admins("/api/admin/users", admin.list_users),
        admin_sessions("/api/admin/users", admin.create_user, ["POST"]),
        admin_sessions("/api/admin/users/{user_id}/reissue-login", admin.reissue_login, ["POST"]),
        admins("/api/admin/users/{user_id}/cancel-login-link", admin.cancel_login_link, ["POST"]),
        admins("/api/admin/users/{user_id}/disabled", admin.set_user_disabled, ["POST"]),
        admins("/api/admin/users/{user_id}/revoke-access", admin.revoke_access, ["POST"]),
        admin_sessions("/api/admin/users/{user_id}/rename", admin.rename_user, ["POST"]),
        admin_sessions("/api/admin/users/{user_id}/role", admin.set_user_role, ["POST"]),
        admin_sessions("/api/admin/users/{user_id}/delete", admin.delete_user, ["POST"]),
        admin_sessions("/api/admin/users/{user_id}/reset-two-factor", admin.reset_two_factor, ["POST"]),
        # A session only, like your own devices list: a key that could end
        # sessions could end the one that would revoke it.
        admin_sessions("/api/admin/users/{user_id}/sessions", sessions.list_user_sessions),
        admin_sessions("/api/admin/users/{user_id}/sessions/{session_id}/revoke", sessions.revoke_user_session, ["POST"]),
        admin_keys("/api/admin/keys", api_keys.list_all_keys),
        admin_keys("/api/admin/keys", api_keys.create_key_for_user, ["POST"]),
        admin_keys("/api/admin/keys/{key_id}/rename", api_keys.rename_any_key, ["POST"]),
        admin_keys("/api/admin/keys/{key_id}/expiry", api_keys.set_any_key_expiry, ["POST"]),
        admin_keys("/api/admin/keys/{key_id}/revoke", api_keys.revoke_any_key, ["POST"]),
        admin_keys("/api/admin/keys/{key_id}/delete", api_keys.delete_any_key, ["POST"]),
        admin_keys("/api/admin/keys/{key_id}/restore", api_keys.restore_any_key, ["POST"]),
        # config.yaml, as the owner's Settings screen. See settings.py.
        owner("/api/owner/settings", settings.get_settings),
        owner("/api/owner/settings", settings.save_settings, ["POST"]),
        # Background jobs. See app/core/jobs.py.
        owner("/api/owner/jobs", jobs.list_jobs),
        owner("/api/owner/jobs/{name}/run", jobs.run_job, ["POST"]),
        # The Zotero library, read live. See app/library/ and routes/library.py.
        signed_in("/api/papers", library.list_papers),
        signed_in("/api/papers/recent", library.recent_papers),
        signed_in("/api/paper", library.get_paper),
        signed_in("/api/paper/pdf", library.get_pdf),
        signed_in("/api/library/status", library.library_status),
        signed_in("/api/library/links", library.get_config_links),
        signed_in("/api/library/stream", library.stream_library),
        # The userscripts' "do I have this paper", with an API key.
        signed_in("/api/exists", library.post_exists, ["POST"]),
        signed_in("/api/version", library.get_version),
        # The lists. Every change is a batch of ops. See app/boards/.
        signed_in("/api/lists", boards.list_lists),
        signed_in("/api/lists", boards.create_list, ["POST"]),
        signed_in("/api/lists/schema", boards.get_schema),
        signed_in("/api/lists/stream", boards.stream_lists),
        signed_in("/api/lists/{slug}", boards.get_list),
        signed_in("/api/lists/{slug}/ops", boards.post_ops, ["POST"]),
        signed_in("/api/lists/{slug}/rows", boards.get_rows),
        signed_in("/api/lists/{slug}/export.csv", boards.get_export_csv, ["GET", "POST"]),
        signed_in("/api/lists/{slug}/history", boards.get_history),
        signed_in("/api/lists/{slug}/history/{rev}", boards.get_version),
        signed_in("/api/lists/{slug}/restore", boards.post_restore, ["POST"]),
        signed_in("/api/lists/{slug}/lock", boards.post_lock, ["POST"]),
        signed_in("/api/cite", boards.post_cite, ["POST"]),
        signed_in("/api/cite/styles", boards.get_cite_styles),
        signed_in("/api/refs/parse", boards.post_refs_parse, ["POST"]),
    ]

    # The activity log (app/core/logs.py). Switched off in config.yaml, none
    # of it exists and track.js sends nothing.
    if cfg.logs.enabled:
        routes += [
            # What someone did on the page, sent by track.js. Theirs to send,
            # the owner's to read.
            signed_in("/api/logs/events", logs.record_ui_events, ["POST"]),
            owner("/api/owner/logs/days", logs.list_log_days),
            owner("/api/owner/logs/days/{date}", logs.get_log_day),
            owner("/api/owner/logs/days/{date}/download", logs.download_log_day),
            owner("/api/owner/logs/days/{date}/delete", logs.delete_log_day, ["POST"]),
            owner("/api/owner/logs/prune", logs.prune_logs, ["POST"]),
            owner("/api/owner/logs/ip-names", logs.list_ip_names),
            owner("/api/owner/logs/ip-names", logs.set_ip_name, ["POST"]),
            owner("/api/owner/logs/ip-names/delete", logs.delete_ip_name, ["POST"]),
            owner("/api/owner/logs/stream", logs.stream_log_changes),
        ]

    # MCP: agents calling the app with an API key (see app/mcp and
    # mcp_tools.py). Keys only -- RequireAPIKey turns a browser session away --
    # and every tool runs at the key's effective role, so this is the API above
    # in another shape, not a wider one.
    #
    # Always registered: server.mcp and auth.api_keys can be switched while
    # the server runs, so RequireMCP checks them per request and answers 404
    # when either is off -- without API keys nothing could authenticate to it.
    mcp = MCPServer(mcp_tools.build_registry())
    routes += [
        group(RequireMCP, RequireAPIKey)("/mcp", mcp.endpoint, ["POST"]),
        group(RequireMCP)("/mcp", mcp.method_not_allowed, ["GET", "DELETE"]),
    ]


    return routes + [
        # Any other /api/ path is a JSON 404, not the index.html fallback.
        Route("/api/{rest:path}", meta.unknown_api),
        # Catch-all static serving. Must stay last -- it matches every
        # remaining path, so anything added after this line never runs.
        Route("/{path:path}", static_server.endpoint),
    ]
