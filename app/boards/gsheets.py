"""The few Google Sheets and Drive calls the list mirror makes
(app/boards/sheetsync.py), by plain HTTP. Ported from the old prma
src/server/gsheets.py, with urllib instead of requests.

Credentials are config.yaml's google_sheets: section: an installed-app OAuth
client and a refresh token (`python -m app manage google-login` makes one).
The access token is kept in memory and refreshed a minute before it ends;
nothing is written to disk.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

TOKEN_URI = "https://oauth2.googleapis.com/token"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE = "https://www.googleapis.com/drive/v3/files"
TIMEOUT_SECONDS = 60

Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class GoogleError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Google said {status}: {message}")
        self.status = status


def _transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() or b""


def _message(raw: bytes) -> str:
    try:
        data = json.loads(raw)
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        return str(data.get("error_description") or error or data)[:300]
    except (ValueError, AttributeError):
        return raw.decode("utf-8", "replace")[:300]


class Client:
    def __init__(self, settings: Callable[[], Any], transport: Transport | None = None) -> None:
        self.settings = settings
        self.transport = transport or _transport
        self.sleep: Callable[[float], None] = time.sleep
        self._lock = threading.Lock()
        self._token = ""
        self._expiry = 0.0
        self._for = ""

    def _headers(self) -> dict[str, str]:
        cfg = self.settings()
        who = f"{cfg.client_id}|{cfg.refresh_token}"
        with self._lock:
            if not self._token or time.time() > self._expiry - 60 or self._for != who:
                body = urllib.parse.urlencode({
                    "client_id": cfg.client_id, "client_secret": cfg.client_secret,
                    "refresh_token": cfg.refresh_token, "grant_type": "refresh_token",
                }).encode()
                try:
                    status, raw = self.transport("POST", TOKEN_URI, {"content-type": "application/x-www-form-urlencoded"}, body)
                except (OSError, socket.timeout) as error:
                    raise GoogleError(0, f"could not reach Google: {error}") from None
                if status != 200:
                    raise GoogleError(status, "refreshing the sign-in failed -- run `python -m app manage google-login` and "
                                      "update config.yaml (" + _message(raw) + ")")
                data = json.loads(raw)
                self._token = data["access_token"]
                self._expiry = time.time() + float(data.get("expires_in") or 3600)
                self._for = who
            headers = {"authorization": "Bearer " + self._token}
        if cfg.quota_project:
            headers["x-goog-user-project"] = cfg.quota_project
        return headers

    def call(self, method: str, url: str, params: dict[str, Any] | None = None, body: Any = None) -> dict[str, Any]:
        """One request, retried with backoff on 429 / 5xx. GoogleError otherwise."""
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        delay = 2.0
        for attempt in range(5):
            headers = {**self._headers(), "content-type": "application/json"}
            try:
                status, raw = self.transport(method, url, headers, data)
            except (OSError, socket.timeout) as error:
                status, raw = 0, str(error).encode()
            if status == 401 and attempt == 0:
                with self._lock:
                    self._token = ""
                continue
            if status in (0, 429, 500, 502, 503, 504) and attempt < 4:
                self.sleep(delay)
                delay *= 2
                continue
            if not 200 <= status < 300:
                raise GoogleError(status, _message(raw))
            return json.loads(raw) if raw else {}
        raise GoogleError(0, "gave up after retries")

    # -- spreadsheets ---------------------------------------------------------------

    def create(self, title: str, tab: str) -> tuple[str, int]:
        """A new spreadsheet with one tab -> (spreadsheet id, tab id)."""
        out = self.call("POST", SHEETS, body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": tab, "gridProperties": {"frozenRowCount": 1}}}],
        })
        return out["spreadsheetId"], out["sheets"][0]["properties"]["sheetId"]

    def tabs(self, sid: str) -> dict[int, dict[str, Any]]:
        """{tab id: {title, rows, cols}}; GoogleError 404 when it is gone."""
        out = self.call("GET", f"{SHEETS}/{sid}", {"fields": "sheets.properties"})
        found = {}
        for sheet in out.get("sheets") or []:
            props = sheet["properties"]
            grid = props.get("gridProperties") or {}
            found[props["sheetId"]] = {"title": props["title"], "rows": grid.get("rowCount", 0), "cols": grid.get("columnCount", 0)}
        return found

    def batch(self, sid: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return self.call("POST", f"{SHEETS}/{sid}:batchUpdate", body={"requests": requests})

    @staticmethod
    def _range(tab: str, cell: str = "") -> str:
        return "'" + tab.replace("'", "''") + "'" + (f"!{cell}" if cell else "")

    def read(self, sid: str, tab: str) -> list[list[Any]]:
        """Every value on a tab, as typed (numbers as numbers)."""
        rng = self._range(tab)
        out = self.call("GET", f"{SHEETS}/{sid}/values/{urllib.parse.quote(rng, safe='')}",
                        {"valueRenderOption": "UNFORMATTED_VALUE", "majorDimension": "ROWS"})
        return out.get("values") or []

    def write(self, sid: str, tab: str, rows: list[list[Any]]) -> dict[str, Any]:
        """rows at A1, RAW: a DOI or "=..." stays the text it is."""
        rng = self._range(tab, "A1")
        return self.call("PUT", f"{SHEETS}/{sid}/values/{urllib.parse.quote(rng, safe='')}", {"valueInputOption": "RAW"},
                         {"range": rng, "majorDimension": "ROWS", "values": rows})

    # -- drive (only for share_with and folder_id) -------------------------------------

    def share(self, sid: str, email: str) -> dict[str, Any]:
        return self.call("POST", f"{DRIVE}/{sid}/permissions", {"sendNotificationEmail": "false"},
                         {"type": "user", "role": "writer", "emailAddress": email})

    def move(self, sid: str, folder: str) -> dict[str, Any]:
        current = self.call("GET", f"{DRIVE}/{sid}", {"fields": "parents"})
        return self.call("PATCH", f"{DRIVE}/{sid}", {"addParents": folder, "removeParents": ",".join(current.get("parents") or [])}, {})
