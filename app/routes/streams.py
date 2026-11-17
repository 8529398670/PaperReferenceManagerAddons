"""The re-check every app stream needs: an open stream was let in once, maybe
hours ago, and ends when the session or key that opened it no longer would be.
Like still_owner in app/core/security.py, it goes straight to the session or
key, not through resolve_actor, so a stream staying open never counts as the
person being there."""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.requests import Request

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
