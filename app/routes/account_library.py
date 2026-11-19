"""Your own library: read your ZoteroWebDAV server instead of the server's
library, on the Account screen. See app/models/user_library.py for what is
stored and app/library/registry.py for how it is read.

Session only, like two-factor: an address and a key are set by a person at
the page, never by an API key or an agent. Nothing here ever answers with the
key, and a refusal never repeats the address or the key."""
from __future__ import annotations

from typing import Annotated, Any, ClassVar

from msgspec import Meta
from starlette.requests import Request

from app.apidocs import SESSION_ONLY, Reply, route
from app.apidocs import Request as RequestType
from app.core.logs import KIND_AUTH
from app.core.security import actor_from
from app.library.remote import Remote, RemoteError
from app.models import user_library, users
from app.models.users import User
from app.routes.helpers import Refused, get_config, get_store
from app.routes.logs import audit

TAG = "Account"


class MyLibrary(Reply, kw_only=True):
    """Which library you read, and how it is doing."""

    api_name: ClassVar[str] = "MyLibrary"
    own: Annotated[bool, Meta(description="Whether you read your own ZoteroWebDAV server. false: the server's library.")]
    url: Annotated[str, Meta(description="Your server's address. Empty when own is false.")]
    key_set: Annotated[bool, Meta(description="Whether an API key is stored. The key itself is never sent back.")]
    name: Annotated[str, Meta(description="The WebDAV library read on that server. Empty: your default one.")]
    ready: bool
    papers: int
    error: Annotated[str, Meta(description="Why the last look at your library failed. Empty when it did not.")]
    last_sync: Annotated[float, Meta(description="When your library was last read, in Unix seconds. 0: not yet.")]


def my_library(request: Request, user: User) -> MyLibrary:
    source = user_library.source_of(user, get_config(request).secret_key)
    libraries = getattr(request.app.state, "libraries", None)
    if source is None or libraries is None:
        server = request.app.state.library if libraries is None else libraries.server
        status = server.catalogue.status
        return MyLibrary(own=False, url="", key_set=False, name="", ready=status.ready, papers=status.papers,
                         error=status.error, last_sync=status.last_sync)
    service = libraries.for_user(user, start=False)
    if service is libraries.server:
        return MyLibrary(own=True, url=source.url, key_set=True, name=source.name, ready=False, papers=0,
                         error="this address is not allowed: it must be a public server", last_sync=0.0)
    status = service.catalogue.status
    error = status.error or getattr(service.library, "error", "")
    return MyLibrary(own=True, url=source.url, key_set=True, name=source.name, ready=status.ready, papers=status.papers,
                     error=error, last_sync=status.last_sync)


class SetMyLibrary(RequestType):
    url: Annotated[str, Meta(description="Your ZoteroWebDAV server's address, https://.", max_length=user_library.MAX_URL)]
    key: Annotated[str, Meta(description="An API key from that server (id.secret). Empty keeps the one stored.", max_length=300)] = ""
    library: Annotated[str, Meta(description="Which of your WebDAV libraries to read. Empty: your default one.", max_length=64)] = ""


def check_server(remote: Remote) -> None:
    """One read, to know the address and key work before they are kept."""
    try:
        page = remote.get_json("/api/library/changes", {"since": 0, "limit": 1})
    except RemoteError as error:
        raise Refused(400, str(error)) from None
    if "rev" not in page:
        raise Refused(400, "that address answered, but not as a ZoteroWebDAV server")


@route(
    "POST /api/account/library", summary="Read your own library",
    tag=TAG, access=SESSION_ONLY,
    description="Read your ZoteroWebDAV server instead of this server's library: its address, an API key "
    "from it, and optionally which WebDAV library. The address and key are checked with one read before they "
    "are kept. Lists, review and what is worked out for each paper stay shared.",
)
def set_my_library(request: Request, body: SetMyLibrary) -> MyLibrary:
    store, cfg, actor = get_store(request), get_config(request), actor_from(request)
    key = body.key.strip()
    if not key:
        current = user_library.source_of(actor.user, cfg.secret_key)
        if current is None:
            raise Refused(400, "an API key is needed")
        key = current.key
    is_owner = actor.user.id == users.get_owner_id(store)
    libraries = getattr(request.app.state, "libraries", None)
    try:
        url, key, name = user_library.check(
            body.url, key, body.library, public_only=not is_owner,
            host_ok=libraries.host_ok if libraries is not None else user_library.public_host,
        )
    except user_library.LibrarySourceError as invalid:
        raise Refused(400, str(invalid)) from None
    factory: Any = libraries.remote_factory if libraries is not None else (lambda s: Remote(s.url, s.key, s.name))
    check_server(factory(user_library.Source(actor.user.id, url, key, name, None)))
    if not user_library.set_source(store, actor.user.id, url, key, name, cfg.secret_key):
        raise Refused.internal("account library: the signed-in account has no record")
    audit(request, KIND_AUTH, "own library set", {"user_id": actor.user.id})
    user = users.get_user(store, actor.user.id)
    if libraries is not None and user is not None:
        libraries.for_user(user)
    return my_library(request, user or actor.user)


class FindLibraries(RequestType):
    url: Annotated[str, Meta(description="Your ZoteroWebDAV server's address, https://.", max_length=user_library.MAX_URL)]
    key: Annotated[str, Meta(description="An API key from that server (id.secret). Empty: the one stored.", max_length=300)] = ""


class WebDAVLibrary(Reply, kw_only=True):
    api_name: ClassVar[str] = "WebDAVLibraryChoice"
    name: Annotated[str, Meta(description="Its WebDAV name: what library is set to.")]
    label: Annotated[str, Meta(description="The owner's note on what it is for. May be empty.")]
    primary: Annotated[bool, Meta(description="true for the one read when no library is named.")]


class WebDAVLibraries(Reply, kw_only=True):
    """The WebDAV libraries a key can read on its server, the default one first."""

    api_name: ClassVar[str] = "WebDAVLibraries"
    libraries: list[WebDAVLibrary]


def list_libraries(remote: Remote) -> list[WebDAVLibrary]:
    try:
        page = remote.get_json("/api/webdav/libraries")
    except RemoteError as error:
        if "HTTP 404" in str(error):
            raise Refused(400, "that server does not list WebDAV libraries (WebDAV may be switched off there)") from None
        raise Refused(400, str(error)) from None
    rows = page.get("libraries")
    if not isinstance(rows, list):
        raise Refused(400, "that address answered, but not as a ZoteroWebDAV server")
    out = [
        WebDAVLibrary(name=str(row.get("name") or ""), label=str(row.get("label") or ""), primary=bool(row.get("primary")))
        for row in rows
        if isinstance(row, dict) and row.get("name") and row.get("enabled", True)
    ]
    out.sort(key=lambda row: (not row.primary, row.name))
    return out


@route(
    "POST /api/account/library/libraries", summary="Your WebDAV libraries on a server",
    tag=TAG, access=SESSION_ONLY,
    description="The WebDAV libraries an API key can read on a ZoteroWebDAV server, to choose which one "
    "you read. An empty key uses the one stored. Nothing is saved.",
)
def find_my_libraries(request: Request, body: FindLibraries) -> WebDAVLibraries:
    store, cfg, actor = get_store(request), get_config(request), actor_from(request)
    key = body.key.strip()
    if not key:
        current = user_library.source_of(actor.user, cfg.secret_key)
        if current is None:
            raise Refused(400, "an API key is needed")
        key = current.key
    is_owner = actor.user.id == users.get_owner_id(store)
    libraries = getattr(request.app.state, "libraries", None)
    try:
        url, key, _ = user_library.check(
            body.url, key, "", public_only=not is_owner,
            host_ok=libraries.host_ok if libraries is not None else user_library.public_host,
        )
    except user_library.LibrarySourceError as invalid:
        raise Refused(400, str(invalid)) from None
    factory: Any = libraries.remote_factory if libraries is not None else (lambda s: Remote(s.url, s.key, s.name))
    return WebDAVLibraries(libraries=list_libraries(factory(user_library.Source(actor.user.id, url, key, "", None))))


@route(
    "POST /api/account/library/clear", summary="Read the server's library again",
    tag=TAG, access=SESSION_ONLY,
    description="Forget your own library's address and key and read this server's library again.",
)
def clear_my_library(request: Request) -> MyLibrary:
    store, actor = get_store(request), actor_from(request)
    if not user_library.clear_source(store, actor.user.id):
        raise Refused.internal("account library: the signed-in account has no record")
    libraries = getattr(request.app.state, "libraries", None)
    if libraries is not None:
        libraries.forget_user(actor.user.id)
    audit(request, KIND_AUTH, "own library cleared", {"user_id": actor.user.id})
    user = users.get_user(store, actor.user.id)
    return my_library(request, user or actor.user)
