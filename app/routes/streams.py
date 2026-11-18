"""The re-check every app stream needs: an open stream was let in once, maybe
hours ago, and ends when the session or key that opened it no longer would be.
Like still_owner in app/core/security.py, it goes straight to the session or
key, not through resolve_actor, so a stream staying open never counts as the
person being there."""
from __future__ import annotations

import hashlib
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from app.core.security import actor_from, decrypt_cookie
from app.models.api_keys import load_api_key
from app.models.sessions import load_session
from app.routes.helpers import get_config, get_store, run


def still_signed_in(request: Request) -> Callable[[], Awaitable[bool]]:
    store, cfg = get_store(request), get_config(request)
    actor = actor_from(request)
    if actor is not None and actor.via_api_key:
        credential = request.headers.get("authorization", "").partition(" ")[2].strip()

        def check() -> bool:
            return load_api_key(store, credential) is not None
    else:
        credential = decrypt_cookie(cfg, request.cookies.get(cfg.session_cookie_name, ""))

        def check() -> bool:
            return load_session(store, credential) is not None

    async def allowed() -> bool:
        return await run(check)

    return allowed


# The page's stream protocol: static/js/live.js asks with ?v=2, opens one
# stream per session (shared by its tabs) and stops on "replaced". A page
# still running older code opens a stream per tab and reconnects forever,
# which used up the browser's six connections and left every request
# spinning; it gets 204, and a browser never reconnects after a 204.
STREAM_VERSION = "2"


def stream_refused(request: Request) -> Response | None:
    if request.query_params.get("v") != STREAM_VERSION:
        return Response(status_code=204)
    return None


def stream_owner(request: Request) -> str:
    """Who a stream belongs to: the session (or key) it came with, so one
    session holds one stream of each kind. "" (no limit) when the page says
    it cannot share streams between its tabs (?solo=1)."""
    if request.query_params.get("solo") == "1":
        return ""
    cfg = get_config(request)
    actor = actor_from(request)
    if actor is not None and actor.via_api_key:
        credential = request.headers.get("authorization", "").partition(" ")[2].strip()
    else:
        credential = decrypt_cookie(cfg, request.cookies.get(cfg.session_cookie_name, ""))
    return hashlib.sha256(credential.encode("utf-8")).hexdigest() if credential else ""
