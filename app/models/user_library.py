"""A person's own library: a ZoteroWebDAV server they read instead of the
server's library (the one config.yaml names). Only the library is theirs:
lists, review, figure picks and summaries stay shared, and what is worked out
for a paper (methods, code, OCR, OpenAlex) is kept once per paper for
everyone. See app/library/registry.py.

The address and the API key are sealed inside the user record with their own
subkey of secret.key (PURPOSE_LIBRARY), on top of the record's encryption,
because server.encrypt_at_rest can be off. The key is never sent back; the
address only to its owner, on /api/me.

Only a remote server can be chosen here. A local Zotero folder is a path on
the server's own disk, so it stays the owner's, in config.yaml.

Everyone but the owner is held to public addresses: a host that resolves to
this machine or the local network is refused, at saving and again at every
connection (registry.py), so an account cannot use the server to reach
what sits beside it.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

from app.core import encryption
from app.core.config import REMOTE_KEY_RE, REMOTE_LIBRARY_RE, remote_url_ok
from app.core.db import BUCKET_USERS, Record, Store
from app.models import to_iso, utc_now
from app.models.users import User

MAX_URL = 300


class LibrarySourceError(ValueError):
    """A source that cannot be stored, said without the address or key."""


@dataclass(frozen=True)
class Source:
    """A ZoteroWebDAV library to read: a user's own, or (user_id 0) the
    server's, from config.yaml. id names its cache folder."""

    user_id: int
    url: str
    key: str
    name: str
    set_at: datetime | None

    @property
    def id(self) -> str:
        return f"u{self.user_id}" if self.user_id else "server"


def server_source(cfg: Any) -> Source:
    """The server's library as a Source: library.remote_* in config.yaml."""
    library = cfg.library
    return Source(0, library.remote_url, library.remote_key, library.remote_library, None)


def _seal(secret_key: str, value: str) -> str:
    return encryption.xchacha_encrypt_string(encryption.subkey(secret_key, encryption.PURPOSE_LIBRARY), value)


def _open(secret_key: str, sealed: str) -> str:
    return encryption.xchacha_decrypt_string(encryption.subkey(secret_key, encryption.PURPOSE_LIBRARY), sealed)


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def public_host(url: str) -> bool:
    """Whether every address the URL's host resolves to is public. Unresolvable
    counts as not public."""
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if not address.is_global or address.is_multicast:
            return False
    return True


def check(url: str, key: str, name: str, *, public_only: bool, host_ok: Callable[[str], bool] | None = None) -> tuple[str, str, str]:
    """The source, checked. LibrarySourceError says what is wrong, never
    echoing the address or the key."""
    url, key, name = normalize_url(url), key.strip(), name.strip()
    if not url or len(url) > MAX_URL or not remote_url_ok(url):
        raise LibrarySourceError("the address must be an https:// address")
    if REMOTE_KEY_RE.fullmatch(key) is None:
        raise LibrarySourceError("that is not a ZoteroWebDAV API key (id.secret)")
    if REMOTE_LIBRARY_RE.fullmatch(name) is None:
        raise LibrarySourceError("the library name may only hold letters, digits, dot, dash and underscore")
    if public_only and not (host_ok or public_host)(url):
        raise LibrarySourceError("the address must be a public server, not this machine or the local network")
    return url, key, name


def source_of(user: User, secret_key: str) -> Source | None:
    """The user's own library, or None for the server's. A field that will
    not open (a key restored from elsewhere) counts as none."""
    if not user.library_url or not user.library_key:
        return None
    try:
        url, key = _open(secret_key, user.library_url), _open(secret_key, user.library_key)
    except (encryption.CipherTextError, encryption.BadKeyError, ValueError):
        return None
    return Source(user.id, url, key, user.library_name, user.library_set_at)


def set_source(store: Store, user_id: int, url: str, key: str, name: str, secret_key: str) -> bool:
    """Stores an already checked source. False if there is no such account."""

    def mutate(record: Record) -> None:
        record["library_url"] = _seal(secret_key, url)
        record["library_key"] = _seal(secret_key, key)
        record["library_name"] = name
        record["library_set_at"] = to_iso(utc_now())

    return store.update_value(BUCKET_USERS, user_id, mutate) is not None


def clear_source(store: Store, user_id: int) -> bool:
    """Back to the server's library. False if there is no such account."""

    def mutate(record: Record) -> None:
        for field in ("library_url", "library_key", "library_name", "library_set_at"):
            record.pop(field, None)

    return store.update_value(BUCKET_USERS, user_id, mutate) is not None
