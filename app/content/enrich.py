"""What is at the other end of a paper's links: GitHub repos, OSF projects and
data-archive records, fetched one at a time and cached as plain JSON.

Ported from the old prma's src/github/github.py, src/osf/osf.py, the
enrichment half of src/tasks/code.py and the record titles of
src/tasks/datasets.py, with what they learned kept:

  - a 404 is an answer: a private, deleted or OCR-mangled repo is cached as
    "not_found" so it is never asked again. A 5xx, a 429, a timeout is a fact
    about right now, never cached, and the item waits a while before its next
    try (in memory), so one bad host can't make the worker spin.
  - OCR damages repo names in predictable ways (a truncated tail, a dropped
    hyphen, a typo) while the owner survives, so a 404'd repo is repaired by
    listing the owner's real repos and matching the broken name against them.
  - the methods a repo / project names (fMRI, EEG, ...) come from its README /
    Home wiki, whole-word, with guards against "PET" the animal and "Meg" the
    person.
  - Zenodo 403s a spoofed browser User-Agent; the honest one works everywhere.
  - osf.io renders in the browser and every page's <title> is "OSF", so OSF
    records are described through the API, never the page.

Cache layout (one JSON per item, written atomically):

  <root>/github/<owner_repo-hash>.json         repo metadata + methods
  <root>/github/<owner_repo-hash>.readme.md    its README (<= 200 KB)
  <root>/github/<owner_repo-hash>.repair.json  a 404'd repo's repair
  <root>/osf/<guid-hash>.json                  project metadata + methods
  <root>/osf/<guid-hash>.wiki.md               its Home wiki (<= 200 KB)
  <root>/records/<target-hash>.json            an archive record's title

Network: urllib only, injectable for tests. One writer (the thread calling
step()) and any number of readers; readers only read files, through a small
in-memory cache that a file's mtime invalidates.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from app.content.store import paper_dir_name

METHOD_NAMES = ("fMRI", "EEG", "ECoG", "fNIRS", "MEG", "PET", "EMG")

GITHUB_API = "https://api.github.com"
OSF_API = "https://api.osf.io/v2"
# Honest, and not only on principle: Zenodo's API 403s a pretend Chrome and
# answers this. Every other host here answers both.
USER_AGENT = "prma/1.0 (paper-reference-manager; +https://github.com/)"
TIMEOUT_SECONDS = 20
# Nothing we read is bigger than this; a runaway download stops here.
MAX_BODY = 5_000_000
# A keyword scan only needs the text; a giant README must not bloat the cache.
TEXT_MAX = 200_000
DESCRIPTION_MAX = 1000
# An owner with more repos than this is listed only this far (sorted by most
# recently updated, which is where a paper's repo usually is).
REPO_PAGES = 3

# A transient failure waits this long before its next try, doubling, up to
# an hour. In memory only: a restart tries everything again, which is fine.
BACKOFF_FIRST = 60.0
BACKOFF_MAX = 3600.0
# A 401 means the key is wrong; asking again every second won't fix it.
BAD_KEY_WAIT = 600.0
# Nobody should wait on a rate limit longer than this, even if the header says so.
RATE_WAIT_MAX = 3600.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    status: int  # 0 when there was no HTTP answer at all (network, timeout)
    headers: dict[str, str] = field(default_factory=dict)  # lower-case names
    body: bytes = b""
    error: str = ""

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except ValueError:
            return None

    def text(self) -> str:
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", self.headers.get("content-type", ""), re.I)
        if m:
            charset = m.group(1)
        try:
            return self.body.decode(charset, "replace")
        except LookupError:
            return self.body.decode("utf-8", "replace")


Fetch = Callable[..., FetchResult]


def urllib_fetch(url: str, headers: dict[str, str] | None = None, data: bytes | None = None, method: str | None = None) -> FetchResult:
    """A GET (or a POST with data). Never raises: an HTTP error is its status,
    a network error or timeout is status 0. Redirects are followed, which is
    what OSF's /guids/<guid>/ needs (it 302s to the typed endpoint)."""
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    merged.update(headers or {})
    request = urllib.request.Request(url, headers=merged, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return FetchResult(response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(MAX_BODY))
    except urllib.error.HTTPError as error:
        try:
            body = error.read(64_000)
        except Exception:
            body = b""
        return FetchResult(error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, body)
    except Exception as error:  # URLError, timeouts, resets, bad TLS, ...
        return FetchResult(0, {}, b"", f"{type(error).__name__}: {error}")


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

# Sentence punctuation that trails a URL in prose, plus the ellipsis OCR and
# PDF layout leave on a truncated link ("github.com/u/Surfa…").
_TRAILING = ".,;:!?'\"”’)>]}»…"

# github.com paths that are site chrome, not a user's repo.
_RESERVED_OWNERS = {
    "about", "features", "pricing", "topics", "search", "marketplace", "sponsors", "settings", "orgs", "apps",
    "enterprise", "login", "join", "new", "notifications", "explore", "collections", "events", "readme", "site",
    "security", "contact", "pulls", "issues", "users", "trending", "customer-stories", "team", "codespaces",
}
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def _parse(url: str):
    u = (url or "").strip().rstrip(_TRAILING)
    if not u:
        return None
    # A bare host/path gets https://; "mailto:", "doi:" and the like keep
    # their scheme (and are then not a host we know).
    if not re.match(r"(?i)^[a-z][a-z0-9+-]*:", u):
        u = "https://" + u.lstrip("/")
    try:
        p = urlparse(u)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    segs = [urllib.parse.unquote(s) for s in (p.path or "").split("/") if s]
    return p, host, segs


def _clean_repo(name: str) -> str:
    name = name.strip().rstrip(_TRAILING)
    name = re.sub(r"(?i)\.git$", "", name)
    # OCR's ellipsis may come through percent-encoded and decoded; cut at
    # the first character a repo name can't have.
    m = re.match(r"[A-Za-z0-9._-]+", name)
    name = m.group(0) if m else ""
    return "" if name in (".", "..") else name


def github_repo(url: str) -> tuple[str, str] | None:
    """("owner", "repo") from a GitHub repo / raw / codeload / API / github.io
    URL, with or without a scheme, with .git, /tree/main, trailing
    punctuation. None for gists, users / orgs alone, site pages, other hosts.

    A github.io page is served from a repo: <owner>.github.io/<project>/ from
    repo <project>, and the bare <owner>.github.io (or a file at its root)
    from the repo named <owner>.github.io."""
    parsed = _parse(url)
    if not parsed:
        return None
    p, host, segs = parsed
    if host.endswith(".github.io"):
        owner = host[: -len(".github.io")]
        if "." in owner or not _OWNER_RE.match(owner):
            return None
        if segs and "." not in segs[0]:
            repo = _clean_repo(segs[0])
        else:
            repo = f"{owner}.github.io"
        return (owner, repo) if repo else None
    if host == "api.github.com":
        if len(segs) < 3 or segs[0] != "repos":
            return None
        segs = segs[1:]
    elif host not in ("github.com", "raw.githubusercontent.com", "codeload.github.com"):
        return None
    if len(segs) < 2:
        return None
    owner, repo = segs[0].strip(), _clean_repo(segs[1])
    if owner.lower() in _RESERVED_OWNERS or not _OWNER_RE.match(owner) or not repo or not _REPO_RE.match(repo):
        return None
    return owner, repo


# osf.io path segments that are site chrome or sub-resources, never a GUID.
_RESERVED_GUIDS = {
    "preprints", "dashboard", "search", "login", "logout", "register", "settings", "support", "explore",
    "myprojects", "registries", "institutions", "quickfiles", "project", "wiki", "files", "overview", "home",
    "metrics", "download", "forks", "registrations", "comments", "contributors", "osfstorage", "components",
    "analytics", "about", "meetings", "collections", "token", "users", "node",
}
_GUID_RE = re.compile(r"^[0-9a-z]{5}$")
_DOI_OSF_RE = re.compile(r"(?i)10\.17605/osf\.io/([0-9a-z]+)")


def osf_guid(url: str) -> str | None:
    """The 5-character OSF GUID of an osf.io URL or an OSF DOI:
      osf.io/<guid>[/wiki/home | /files/osfstorage | /overview]  -> <guid>
      osf.io/project/<guid>/..., osf.io/download/<guid>        -> <guid>
      osf.io/preprints/<provider>/<guid>_v2                    -> <guid>
      doi.org/10.17605/OSF.IO/<GUID>                           -> <guid>"""
    parsed = _parse(url)
    if not parsed:
        return None
    p, host, segs = parsed
    if host == "doi.org" or host.endswith(".doi.org"):
        m = _DOI_OSF_RE.search(urllib.parse.unquote(p.path or ""))
        cand = m.group(1).lower() if m else ""
        return cand if _GUID_RE.match(cand) else None
    if host != "osf.io" and not host.endswith(".osf.io"):
        return None
    if host != "osf.io":
        return None  # api.osf.io, files.osf.io: not a page anyone links
    if not segs:
        return None
    first = segs[0].lower()
    if first == "preprints" and len(segs) >= 2:
        cand = segs[-1]
    elif first in ("project", "node", "download") and len(segs) >= 2:
        cand = segs[1]
    else:
        cand = segs[0]
    cand = re.sub(r"(?i)_v\d+$", "", cand.strip().rstrip(_TRAILING)).lower()
    if not _GUID_RE.match(cand) or cand in _RESERVED_GUIDS:
        return None
    return cand


def _zenodo_id(u: str) -> str:
    m = re.search(r"zenodo\.org/(?:records?|deposit|uploads|api/records)/(\d+)", u) or re.search(r"zenodo\.(\d+)", u)
    return m.group(1) if m else ""


def _figshare_id(u: str) -> str:
    m = re.search(r"figshare\.(\d+)", u) or re.search(r"figshare\.com/(?:s/)?articles?/(?:[^/?#]+/){0,2}(\d+)", u)
    return m.group(1) if m else ""


def record_target(url: str) -> str | None:
    """A stable cache id for a record URL we can describe:
      zenodo:<record id>, figshare:<article id>, openneuro:dsNNNNNN, osf:<guid>,
      page:<url> for any other http(s) page (its <title> describes it).
    None for an empty or non-http value, or a Zenodo / Figshare / OpenNeuro
    link with no record id in it (a search page, a site home)."""
    parsed = _parse(url)
    if not parsed:
        return None
    p, host, segs = parsed
    if p.scheme.lower() not in ("http", "https") or not host or "." not in host:
        return None
    u = (p.geturl() or "").lower()
    if "zenodo" in host or (host.endswith("doi.org") and "zenodo" in u):
        ident = _zenodo_id(u)
        return f"zenodo:{ident}" if ident else None
    if "figshare" in host or (host.endswith("doi.org") and "figshare" in u):
        ident = _figshare_id(u)
        return f"figshare:{ident}" if ident else None
    if "openneuro" in host or (host.endswith("doi.org") and ("openneuro" in u or "10.18112" in u)):
        m = re.search(r"\b(ds\d{6})", u)
        return f"openneuro:{m.group(1)}" if m else None
    guid = osf_guid(url)
    if guid:
        return f"osf:{guid}"
    if host == "osf.io":
        return None  # an osf.io page with no GUID: its <title> is just "OSF"
    page = p._replace(fragment="").geturl()
    return f"page:{page}"


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------
# The old vocabulary, as whole words plus spelled-out phrases. "Whole word"
# here means no letter or digit on either side, so "eeg_data" and
# "rs-fMRI" count but "EMG" inside "SEMGroup" does not. Three labels are also
# ordinary words, so their case matters:
#   PET  upper case only: "my pet project" / topic "pets" are not imaging;
#   MEG  "MEG" or "meg" (GitHub topics are lower case), never "Meg" the name;
#   EMG  any case, but only whole.
_BOUND_L = r"(?<![A-Za-z0-9])"
_BOUND_R = r"(?![A-Za-z0-9])"
_METHOD_RULES: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    ("fMRI", re.compile(_BOUND_L + r"(?:fmri|fmriprep)" + _BOUND_R, re.I), ("functional mri", "functional magnetic resonance")),
    ("EEG", re.compile(_BOUND_L + r"(?:i?eeg|eeglab)" + _BOUND_R, re.I), ("electroencephalogra",)),
    ("ECoG", re.compile(_BOUND_L + r"ecog" + _BOUND_R, re.I), ("electrocorticogra",)),
    ("fNIRS", re.compile(_BOUND_L + r"f?nirs" + _BOUND_R, re.I), ("functional near-infrared", "functional near infrared", "near-infrared spectroscopy")),
    ("MEG", re.compile(_BOUND_L + r"(?:MEG|meg)" + _BOUND_R), ("magnetoencephalogra",)),
    ("PET", re.compile(_BOUND_L + r"PET" + _BOUND_R), ("positron emission",)),
    ("EMG", re.compile(_BOUND_L + r"s?emg" + _BOUND_R, re.I), ("electromyogra",)),
)


def methods_in(text: str) -> list[str]:
    """Which of METHOD_NAMES a README / wiki / abstract names, in
    METHOD_NAMES order."""
    if not text:
        return []
    low = text.lower()
    return [label for label, rx, phrases in _METHOD_RULES if rx.search(text) or any(ph in low for ph in phrases)]


# ---------------------------------------------------------------------------
# Repairing an OCR-mangled repo name
# ---------------------------------------------------------------------------


def _norm_name(s: str) -> str:
    """Lowercase alphanumerics: the '-' / '_' / '.' OCR most often adds or
    loses don't count, so TO-START, to_start and TOSTART are one key."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def best_repo_match(bad: str, names: Iterable[str]) -> tuple[str, str, float] | None:
    """(real_name, tier, confidence) for the repo `bad` most plausibly meant,
    or None. Tiers, most trustworthy first:
      exact   the names are equal once punctuation is ignored;
      prefix  the broken name is the start of a real one (OCR cut the tail);
              of several, the SHORTEST completion is the careful guess;
      fuzzy   WRatio >= 90 catches typo-level edits.
    Below that it abstains: a 404 is better than the wrong repo."""
    from rapidfuzz import fuzz, process

    names = [n for n in names if n]
    nb = _norm_name(bad)
    if not names or len(nb) < 3:
        return None
    normed = [(n, _norm_name(n)) for n in names]
    for n, nn in normed:
        if nn == nb:
            return n, "exact", 1.0
    if len(nb) >= 5:
        prefixes = [n for n, nn in normed if nn.startswith(nb)]
        if len(prefixes) == 1:
            return prefixes[0], "prefix", 0.97
        if prefixes:
            best = min(prefixes, key=lambda n: (len(_norm_name(n)), -fuzz.WRatio(bad, n)))
            return best, "prefix", 0.92
    cand = process.extractOne(bad, names, scorer=fuzz.WRatio)
    if cand and cand[1] >= 90:
        return cand[0], "fuzzy", round(float(cand[1]) / 100, 3)
    return None


# ---------------------------------------------------------------------------
# Record descriptions
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
# A 200 is not an answer when the title is a directory listing or the bare
# site name (the real title is rendered by JavaScript we don't run).
_JUNK_TITLE = re.compile(r"(?i)^\s*(?:index of\b.*|osf|zenodo|figshare|openneuro|dryad|nitrc|neurovault|github)\s*$")
# A soft 404 wearing a 200. Searched, not anchored: the archives decorate it.
_NOT_FOUND_TITLE = re.compile(r"(?i)\bnot\s+found\b|\berror\s*40\d\b|\b40[34]\b")
# Cosmetics the archives glue on: the page already says which archive it is.
_TITLE_TRIMS = (
    (re.compile(r"(?i)^dryad\s*\|\s*data:\s*"), ""),
    (re.compile(r"(?i)\s*·\s*datasets? at hugging face\s*$"), ""),
    (re.compile(r"(?i)^nitrc:\s*"), ""),
    (re.compile(r"(?i):\s*tool/resource info\s*$"), ""),
    (re.compile(r"(?i)\s*[-|]\s*openneuro\s*$"), ""),
    (re.compile(r"(?i)\s*\|\s*zenodo\s*$"), ""),
)


def _plain(raw: Any, cap: int = DESCRIPTION_MAX) -> str:
    """One line of prose from HTML / markdown-ish text."""
    t = re.sub(r"<[^>]+>", " ", str(raw or ""))
    t = " ".join(html.unescape(t).split())
    return t[:cap]


def tidy_title(raw: Any) -> str:
    """A title, or "" when what came back was not an answer."""
    t = _plain(raw, 10_000)
    for rx, sub in _TITLE_TRIMS:
        t = rx.sub(sub, t).strip()
    if not t or _JUNK_TITLE.match(t) or _NOT_FOUND_TITLE.search(t):
        return ""
    return t[:300]


def _meta_description(page: str) -> str:
    for tag in _META_RE.findall(page):
        name = re.search(r"""(?:name|property)\s*=\s*["']([^"']+)["']""", tag, re.I)
        if name and name.group(1).lower() in ("description", "og:description", "twitter:description"):
            content = re.search(r"""content\s*=\s*(["'])(.*?)\1""", tag, re.I | re.S)
            if content and content.group(2).strip():
                return _plain(content.group(2))
    return ""


def _markdown_summary(text: str, name: str = "") -> str:
    """The opening prose of a README: headings, badges and the line that just
    repeats the dataset's name are dropped."""
    out: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "![", "[![", "|", "```", "---", "===")):
            continue
        if name and _norm_name(s) == _norm_name(name):
            continue
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
        s = re.sub(r"[*_`]{1,3}", "", s)
        out.append(s)
        if sum(len(x) for x in out) > DESCRIPTION_MAX:
            break
    return _plain(" ".join(out))


# ---------------------------------------------------------------------------
# Small file helpers
# ---------------------------------------------------------------------------


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json(path: Path, value: Any) -> None:
    _write_atomic(path, json.dumps(value, ensure_ascii=False, indent=1).encode("utf-8"))


class _Transient(Exception):
    """Could not ask right now (network, 5xx, 429, a bad minute): not cached,
    the item waits and is tried again."""

    def __init__(self, message: str, wait: float | None = None) -> None:
        super().__init__(message)
        self.wait = wait


class _BadKey(Exception):
    """401: the key is wrong or expired. The whole kind waits."""


# ---------------------------------------------------------------------------
# The enricher
# ---------------------------------------------------------------------------


class Enricher:
    def __init__(self, root: Path, tokens: Callable[[], tuple[str, str]], fetch: Fetch | None = None) -> None:
        self.root = Path(root)
        self.tokens = tokens
        self.fetch: Fetch = fetch or urllib_fetch
        self.clock: Callable[[], float] = time.time
        self._lock = threading.Lock()
        self._mem: dict[Path, tuple[float, Any]] = {}
        # In memory only: when each failed item / kind / host may be tried again.
        self._item_wait: dict[str, tuple[float, int]] = {}
        self._kind_wait: dict[str, float] = {}
        self._host_wait: dict[str, float] = {}
        # Owner -> its repo names (None: no such owner), so several broken
        # links under one owner list the profile once.
        self._owner_repos: dict[str, list[str] | None] = {}
        for kind in ("github", "osf", "records"):
            (self.root / kind).mkdir(mode=0o700, parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------------

    @staticmethod
    def _gh_key(owner: str, repo: str) -> str:
        # GitHub names are case-insensitive; one file per repo however a paper spelled it.
        return f"{owner}/{repo}".lower()

    def _gh_path(self, owner: str, repo: str, suffix: str = ".json") -> Path:
        return self.root / "github" / (paper_dir_name(self._gh_key(owner, repo)) + suffix)

    def _osf_path(self, guid: str, suffix: str = ".json") -> Path:
        return self.root / "osf" / (paper_dir_name(guid.lower()) + suffix)

    def _record_path(self, target: str) -> Path:
        return self.root / "records" / (paper_dir_name(target) + ".json")

    # -- reading ---------------------------------------------------------------

    def _read(self, path: Path) -> Any:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            with self._lock:
                self._mem.pop(path, None)
            return None
        with self._lock:
            hit = self._mem.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        with self._lock:
            if len(self._mem) > 20_000:
                self._mem.clear()
            self._mem[path] = (mtime, value)
        return value

    def _save(self, path: Path, value: Any) -> None:
        _write_json(path, value)
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return
        with self._lock:
            self._mem[path] = (mtime, value)

    def github(self, owner: str, repo: str) -> dict | None:
        """The cached repo, or None when it hasn't been fetched yet."""
        return self._read(self._gh_path(owner, repo))

    def readme(self, owner: str, repo: str) -> str:
        try:
            return self._gh_path(owner, repo, ".readme.md").read_text(encoding="utf-8")
        except OSError:
            return ""

    def osf(self, guid: str) -> dict | None:
        return self._read(self._osf_path(guid))

    def wiki(self, guid: str) -> str:
        try:
            return self._osf_path(guid, ".wiki.md").read_text(encoding="utf-8")
        except OSError:
            return ""

    def record(self, target: str) -> dict | None:
        return self._read(self._record_path(target))

    def repair(self, owner: str, repo: str) -> dict | None:
        """A 404'd repo's repair: {"url", "repo", "tier", "confidence",
        "original"} or {"tier": "none"}; None when not tried yet."""
        return self._read(self._gh_path(owner, repo, ".repair.json"))

    def effective_repo(self, owner: str, repo: str) -> tuple[str, str]:
        """The repo to show for (owner, repo): the repaired one when a repair
        matched, else the same pair."""
        fix = self.repair(owner, repo) or {}
        if fix.get("tier") not in (None, "none") and fix.get("repo"):
            return owner, fix["repo"]
        return owner, repo

    # -- the worker --------------------------------------------------------------

    def step(self, wanted: Iterable[tuple[str, str]]) -> str | None:
        """Do the network work for the first item in `wanted` that still needs
        some, and cache the answer. Items: ("github", "owner/repo"),
        ("osf", guid), ("record", target). A GitHub item may need up to three
        visits: its fetch, then (on a 404) its repair, then the repaired repo's
        fetch. Returns what it did, or None when nothing was left to do (all
        cached, waiting out a failure, or missing a key)."""
        github_token, osf_token = self.tokens()
        now = self.clock()
        for kind, ident in wanted:
            ident = str(ident or "").strip()
            if not ident:
                continue
            action = self._next_action(kind, ident, github_token, osf_token, now)
            if action is None:
                continue
            name, label, run = action
            try:
                run()
            except _BadKey as error:
                self._kind_wait[name] = now + BAD_KEY_WAIT
                return f"{label} (key refused: {error})"
            except _Transient as error:
                self._fail(f"{kind}:{ident}", now, error.wait)
                return f"{label} (failed, will retry: {error})"
            except Exception as error:  # a bug or an odd answer: don't spin on it
                self._fail(f"{kind}:{ident}", now, None)
                return f"{label} (failed, will retry: {type(error).__name__}: {error})"
            self._item_wait.pop(f"{kind}:{ident}", None)
            return label
        return None

    def _fail(self, key: str, now: float, wait: float | None) -> None:
        _, attempts = self._item_wait.get(key, (0.0, 0))
        attempts += 1
        delay = wait if wait else min(BACKOFF_FIRST * 2 ** (attempts - 1), BACKOFF_MAX)
        self._item_wait[key] = (now + delay, attempts)

    def _waiting(self, key: str, now: float) -> bool:
        until = self._item_wait.get(key, (0.0, 0))[0]
        return until > now

    def _next_action(self, kind: str, ident: str, github_token: str, osf_token: str, now: float):
        if self._waiting(f"{kind}:{ident}", now):
            return None
        if kind == "github":
            if not github_token or self._kind_wait.get("github", 0.0) > now:
                return None
            owner, _, repo = ident.partition("/")
            if not owner or not repo:
                return None
            rec = self.github(owner, repo)
            if rec is None:
                return "github", f"github {owner}/{repo}", lambda: self._fetch_github(owner, repo, github_token)
            if rec.get("status") == "not_found":
                fix = self.repair(owner, repo)
                if fix is None:
                    return "github", f"repair {owner}/{repo}", lambda: self._repair(owner, repo, github_token)
                if fix.get("repo") and fix.get("tier") != "none" and self.github(owner, fix["repo"]) is None:
                    fixed = fix["repo"]
                    return "github", f"github {owner}/{fixed} (repaired)", lambda: self._fetch_github(owner, fixed, github_token)
            return None
        if kind == "osf":
            if not osf_token or self._kind_wait.get("osf", 0.0) > now:
                return None
            guid = ident.lower()
            if self.osf(guid) is not None:
                return None
            return "osf", f"osf {guid}", lambda: self._fetch_osf(guid, osf_token)
        if kind == "record":
            if self.record(ident) is not None:
                return None
            host = self._record_host(ident)
            if self._host_wait.get(host, 0.0) > now:
                return None
            return "record", f"record {ident}", lambda: self._fetch_record(ident, osf_token)
        return None

    # -- GitHub ------------------------------------------------------------------

    def _gh_get(self, path: str, token: str, accept: str = "application/vnd.github+json") -> FetchResult:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "Authorization": f"Bearer {token}"}
        r = self.fetch(f"{GITHUB_API}{path}", headers=headers)
        now = self.clock()
        remaining = r.headers.get("x-ratelimit-remaining")
        reset = r.headers.get("x-ratelimit-reset")
        if remaining == "0" and reset:
            # Out of requests until reset: every GitHub item waits, not just this one.
            try:
                self._kind_wait["github"] = min(float(reset), now + RATE_WAIT_MAX) + 1
            except ValueError:
                self._kind_wait["github"] = now + BACKOFF_FIRST
        if r.status == 401:
            raise _BadKey("GitHub answered 401")
        if r.status in (403, 429) and (remaining == "0" or r.status == 429 or b"rate limit" in r.body.lower()):
            wait = _retry_after(r) or (max(self._kind_wait.get("github", 0.0) - now, 0) or BACKOFF_FIRST)
            self._kind_wait["github"] = max(self._kind_wait.get("github", 0.0), now + min(wait, RATE_WAIT_MAX))
            raise _Transient(f"rate limited ({r.status})", wait)
        if r.status == 0 or r.status >= 500:
            raise _Transient(r.error or f"GitHub answered {r.status}")
        return r

    def _fetch_github(self, owner: str, repo: str, token: str) -> None:
        r = self._gh_get(f"/repos/{owner}/{repo}", token)
        base = {"owner": owner, "repo": repo, "url": f"https://github.com/{owner}/{repo}", "fetched_at": _now_iso()}
        if r.status in (404, 410, 451):
            # Private, deleted, DMCA'd -- or OCR-mangled, which repair() looks at next.
            self._save(self._gh_path(owner, repo), {**base, "status": "not_found", "http": r.status})
            return
        if r.status == 403:
            self._save(self._gh_path(owner, repo), {**base, "status": "forbidden", "http": r.status})
            return
        meta = r.json() if r.status == 200 else None
        if not isinstance(meta, dict):
            raise _Transient(f"GitHub answered {r.status} without a repo")
        readme = self._github_readme(owner, repo, token)
        rec = {
            **base,
            "status": "ok",
            "full_name": meta.get("full_name") or f"{owner}/{repo}",
            "url": meta.get("html_url") or base["url"],
            "description": (meta.get("description") or "").strip(),
            "stars": meta.get("stargazers_count"),
            "language": meta.get("language") or "",
            "topics": meta.get("topics") or [],
            "homepage": meta.get("homepage") or "",
            "updated": meta.get("pushed_at") or meta.get("updated_at") or "",
            "archived": bool(meta.get("archived")),
            "readme_chars": len(readme),
        }
        rec["methods"] = methods_in(_haystack(rec, readme))
        if readme:
            _write_atomic(self._gh_path(owner, repo, ".readme.md"), readme.encode("utf-8"))
        self._save(self._gh_path(owner, repo), rec)

    def _github_readme(self, owner: str, repo: str, token: str) -> str:
        """The default README (the /readme endpoint finds README.md / .rst /
        .txt). "" when the repo has none; a transient failure raises, so the
        repo is tried again rather than cached untagged forever."""
        r = self._gh_get(f"/repos/{owner}/{repo}/readme", token)
        if r.status in (404, 410):
            return ""
        data = r.json() if r.status == 200 else None
        if not isinstance(data, dict):
            raise _Transient(f"README answered {r.status}")
        content = data.get("content") or ""
        if data.get("encoding") == "base64":
            try:
                text = base64.b64decode(content).decode("utf-8", "replace")
            except (ValueError, TypeError):
                return ""
        else:
            text = content if isinstance(content, str) else ""
        return text[:TEXT_MAX]

    def _list_owner_repos(self, owner: str, token: str) -> list[str] | None:
        key = owner.lower()
        if key in self._owner_repos:
            return self._owner_repos[key]
        names: list[str] = []
        result: list[str] | None = names
        for page in range(1, REPO_PAGES + 1):
            r = self._gh_get(f"/users/{owner}/repos?per_page=100&sort=updated&page={page}", token)
            if r.status in (404, 410):
                result = names if names else None  # no such owner: OCR got the profile too
                break
            data = r.json() if r.status == 200 else None
            if not isinstance(data, list):
                raise _Transient(f"repo list answered {r.status}")
            names += [str(d.get("name")) for d in data if isinstance(d, dict) and d.get("name")]
            if len(data) < 100:
                break
        if len(self._owner_repos) > 500:
            self._owner_repos.clear()
        self._owner_repos[key] = result
        return result

    def _repair(self, owner: str, repo: str, token: str) -> None:
        names = self._list_owner_repos(owner, token)
        original = f"https://github.com/{owner}/{repo}"
        match = best_repo_match(repo, names or [])
        if match and match[0].lower() != repo.lower():
            fixed, tier, confidence = match
            value = {
                "url": f"https://github.com/{owner}/{fixed}", "repo": fixed, "tier": tier,
                "confidence": confidence, "original": original, "fetched_at": _now_iso(),
            }
        else:
            value = {"tier": "none", "original": original, "owner_found": names is not None, "fetched_at": _now_iso()}
        self._save(self._gh_path(owner, repo, ".repair.json"), value)

    # -- OSF ---------------------------------------------------------------------

    def _osf_get(self, url: str, token: str, accept: str = "application/vnd.api+json") -> FetchResult:
        headers = {"Accept": accept}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = self.fetch(url, headers=headers)
        if r.status == 401 and token:
            raise _BadKey("OSF answered 401")
        if r.status == 0 or r.status == 429 or r.status >= 500:
            raise _Transient(r.error or f"OSF answered {r.status}", _retry_after(r))
        return r

    def _fetch_osf(self, guid: str, token: str) -> None:
        r = self._osf_get(f"{OSF_API}/guids/{guid}/", token)
        base = {"guid": guid, "url": f"https://osf.io/{guid}/", "fetched_at": _now_iso()}
        if r.status in (404, 410):
            self._save(self._osf_path(guid), {**base, "status": "not_found", "http": r.status})
            return
        if r.status == 403:
            # Private or embargoed: the key is fine, this one just isn't readable.
            self._save(self._osf_path(guid), {**base, "status": "forbidden", "http": r.status})
            return
        body = r.json() if r.status == 200 else None
        node = body.get("data") if isinstance(body, dict) else None
        if not isinstance(node, dict):
            raise _Transient(f"OSF answered {r.status} without a record")
        attrs = node.get("attributes") or {}
        rtype = node.get("type") or ""
        wiki = ""
        # Only projects and registrations carry wikis; a preprint or a file
        # has its description and nothing else.
        if rtype in ("nodes", "registrations"):
            wiki = self._osf_wiki(guid, rtype, token)
        rec = {
            **base,
            "status": "ok",
            "type": rtype,
            "title": html.unescape(attrs.get("title") or attrs.get("name") or "").strip(),
            "description": html.unescape(attrs.get("description") or "").strip(),
            "category": attrs.get("category") or "",
            "tags": attrs.get("tags") or [],
            "updated": attrs.get("date_modified") or "",
            "wiki_chars": len(wiki),
        }
        rec["methods"] = methods_in(_haystack(rec, wiki))
        if wiki:
            _write_atomic(self._osf_path(guid, ".wiki.md"), wiki.encode("utf-8"))
        self._save(self._osf_path(guid), rec)

    def _osf_wiki(self, guid: str, rtype: str, token: str) -> str:
        r = self._osf_get(f"{OSF_API}/{rtype}/{guid}/wikis/", token)
        if r.status in (403, 404, 410):
            return ""
        data = r.json() if r.status == 200 else None
        if not isinstance(data, dict):
            raise _Transient(f"wiki list answered {r.status}")
        wikis = [w for w in data.get("data") or [] if isinstance(w, dict)]
        if not wikis:
            return ""
        chosen = next((w for w in wikis if str((w.get("attributes") or {}).get("name") or "").lower() == "home"), wikis[0])
        url = (chosen.get("links") or {}).get("download") or f"{OSF_API}/wikis/{chosen.get('id')}/content/"
        r = self._osf_get(url, token, accept="text/markdown, text/plain, */*")
        if r.status in (403, 404, 410):
            return ""
        if r.status != 200:
            raise _Transient(f"wiki answered {r.status}")
        return r.text()[:TEXT_MAX]

    # -- records -----------------------------------------------------------------

    @staticmethod
    def _record_host(target: str) -> str:
        kind, _, rest = target.partition(":")
        if kind == "page":
            return (urlparse(rest).hostname or "").lower()
        return kind

    def _record_get(self, target: str, url: str, **kwargs: Any) -> FetchResult:
        r = self.fetch(url, **kwargs)
        if r.status == 0 or r.status == 429 or r.status >= 500:
            wait = _retry_after(r)
            # A host that is down is down for every record on it.
            self._host_wait[self._record_host(target)] = self.clock() + min(wait or BACKOFF_FIRST, RATE_WAIT_MAX)
            raise _Transient(r.error or f"answered {r.status}", wait)
        return r

    def _fetch_record(self, target: str, osf_token: str) -> None:
        kind, _, ident = target.partition(":")
        base = {"target": target, "fetched_at": _now_iso()}
        title, description = "", ""
        if kind == "zenodo":
            url = f"https://zenodo.org/records/{ident}"
            r = self._record_get(target, f"https://zenodo.org/api/records/{ident}")
            if r.status == 200:
                meta = (r.json() or {}).get("metadata") or {}
                title, description = tidy_title(meta.get("title")), _plain(meta.get("description"))
        elif kind == "figshare":
            url = f"https://figshare.com/articles/{ident}"
            r = self._record_get(target, f"https://api.figshare.com/v2/articles/{ident}")
            if r.status == 200:
                data = r.json() or {}
                url = data.get("url_public_html") or url
                title, description = tidy_title(data.get("title")), _plain(data.get("description"))
        elif kind == "openneuro":
            url = f"https://openneuro.org/datasets/{ident}"
            query = json.dumps({"query": '{dataset(id:"%s"){draft{description{Name} readme}}}' % ident}).encode("utf-8")
            r = self._record_get(target, "https://openneuro.org/crn/graphql", headers={"Content-Type": "application/json"}, data=query, method="POST")
            if r.status == 200:
                body = r.json() or {}
                draft = ((body.get("data") or {}).get("dataset") or {}).get("draft") or {}
                name = ((draft.get("description") or {}).get("Name")) or ""
                errors = " ".join(str(e.get("message") or "") for e in body.get("errors") or [] if isinstance(e, dict))
                if not name and re.search(r"(?i)does not exist|not found", errors):
                    self._save(self._record_path(target), {**base, "url": url, "status": "not_found", "title": "", "description": "", "http": 404})
                    return
                if not name and errors:
                    # GraphQL puts its failures in a 200; with no data that is
                    # OpenNeuro having a bad minute, not a missing dataset.
                    self._host_wait["openneuro"] = self.clock() + BACKOFF_FIRST
                    raise _Transient(f"OpenNeuro: {errors[:200]}")
                title, description = tidy_title(name), _markdown_summary(draft.get("readme") or "", name)
        elif kind == "osf":
            url = f"https://osf.io/{ident}/"
            headers = {"Accept": "application/vnd.api+json"}
            if osf_token:
                headers["Authorization"] = f"Bearer {osf_token}"
            r = self._record_get(target, f"{OSF_API}/guids/{ident}/", headers=headers)
            if r.status == 200:
                attrs = ((r.json() or {}).get("data") or {}).get("attributes") or {}
                title, description = tidy_title(attrs.get("title") or attrs.get("name")), _plain(attrs.get("description"))
        elif kind == "page":
            url = ident
            r = self._record_get(target, url, headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
            if r.status == 200 and "html" in r.headers.get("content-type", "html").lower():
                page = r.text()
                m = _TITLE_RE.search(page)
                raw_title = _plain(m.group(1), 10_000) if m else ""
                if raw_title and _NOT_FOUND_TITLE.search(raw_title):
                    self._save(self._record_path(target), {**base, "url": url, "status": "not_found", "title": "", "description": "", "http": 200})
                    return
                title, description = tidy_title(raw_title), _meta_description(page)
        else:
            raise ValueError(f"unknown record target {target!r}")
        if r.status == 200:
            status = "ok"
        elif r.status in (404, 410):
            status = "not_found"
        else:
            status = f"http_{r.status}"  # another 4xx: a fact about the link
        if description and title and _norm_name(description) == _norm_name(title):
            description = ""
        self._save(self._record_path(target), {**base, "url": url, "status": status, "title": title, "description": description, "http": r.status})

    # -- the old prma's caches ---------------------------------------------------

    def seed_legacy(self, legacy_root: Path) -> dict[str, int]:
        """Convert the old caches (<legacy_root>/github, /osf, /datasets) into
        this shape, once: an item already here is left alone. Old records
        whose README / wiki fetch failed transiently, or that cached an error
        (401, 5xx), are skipped so they are fetched properly."""
        legacy_root = Path(legacy_root)
        counts = {"github": 0, "repairs": 0, "osf": 0, "records": 0, "skipped": 0}
        for path in sorted((legacy_root / "github").glob("*.json")):
            old = _load(path)
            if not isinstance(old, dict) or not old.get("owner") or not old.get("repo"):
                counts["skipped"] += 1
                continue
            owner, repo = str(old["owner"]), str(old["repo"])
            converted = _github_from_legacy(old)
            if converted and self.github(owner, repo) is None:
                readme = str(old.get("readme") or "")[:TEXT_MAX]
                if readme:
                    _write_atomic(self._gh_path(owner, repo, ".readme.md"), readme.encode("utf-8"))
                self._save(self._gh_path(owner, repo), converted)
                counts["github"] += 1
            elif not converted:
                counts["skipped"] += 1
            resolve = old.get("resolve")
            if isinstance(resolve, dict) and old.get("status") == "not_found" and self.repair(owner, repo) is None:
                self._save(self._gh_path(owner, repo, ".repair.json"), _repair_from_legacy(owner, repo, resolve))
                counts["repairs"] += 1
        for path in sorted((legacy_root / "osf").glob("*.json")):
            old = _load(path)
            guid = str((old or {}).get("guid") or "").lower() if isinstance(old, dict) else ""
            converted = _osf_from_legacy(old) if guid else None
            if not converted:
                counts["skipped"] += 1
                continue
            if self.osf(guid) is not None:
                continue
            wiki = str(old.get("readme") or "")[:TEXT_MAX]
            if wiki:
                _write_atomic(self._osf_path(guid, ".wiki.md"), wiki.encode("utf-8"))
            self._save(self._osf_path(guid), converted)
            counts["osf"] += 1
        for path in sorted((legacy_root / "datasets").glob("*.json")):
            old = _load(path)
            target = record_target(str((old or {}).get("url") or "")) if isinstance(old, dict) else None
            converted = _record_from_legacy(old, target) if target else None
            if not converted:
                counts["skipped"] += 1
                continue
            if self.record(target) is not None:
                continue
            self._save(self._record_path(target), converted)
            counts["records"] += 1
        return counts


def _retry_after(r: FetchResult) -> float | None:
    try:
        value = float(r.headers.get("retry-after") or 0)
    except ValueError:
        return None
    return value or None


def _haystack(rec: dict, text: str) -> str:
    """What a repo / project is scanned for methods in: its name, description,
    topics / tags, and its README / wiki."""
    parts = [
        rec.get("full_name") or rec.get("title") or "",
        rec.get("description") or "",
        " ".join(str(t) for t in rec.get("topics") or rec.get("tags") or []),
        text or "",
    ]
    return "\n".join(p for p in parts if p)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _github_from_legacy(old: dict) -> dict | None:
    owner, repo = str(old["owner"]), str(old["repo"])
    base = {"owner": owner, "repo": repo, "url": old.get("url") or f"https://github.com/{owner}/{repo}", "fetched_at": old.get("fetched_at") or _now_iso(), "legacy": True}
    status = old.get("status")
    if status == "not_found":
        return {**base, "status": "not_found", "http": 404}
    if status != "ok" or old.get("readme_status") == "error":
        return None
    readme = str(old.get("readme") or "")[:TEXT_MAX]
    rec = {
        **base,
        "status": "ok",
        "full_name": old.get("full_name") or f"{owner}/{repo}",
        "description": old.get("description") or "",
        "stars": old.get("stars"),
        "language": old.get("language") or "",
        "topics": old.get("topics") or [],
        "homepage": old.get("homepage") or "",
        "updated": old.get("pushed_at") or "",
        "archived": bool(old.get("archived")),
        "readme_chars": len(readme),
    }
    rec["methods"] = methods_in(_haystack(rec, readme))
    return rec


def _repair_from_legacy(owner: str, repo: str, resolve: dict) -> dict:
    original = f"https://github.com/{owner}/{repo}"
    at = resolve.get("at") or _now_iso()
    if resolve.get("matched") and resolve.get("repo"):
        try:
            confidence = round(float(resolve.get("score") or 0) / 100, 3)
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "url": resolve.get("url") or f"https://github.com/{owner}/{resolve['repo']}", "repo": resolve["repo"],
            "tier": resolve.get("method") or "fuzzy", "confidence": confidence, "original": original, "fetched_at": at, "legacy": True,
        }
    return {"tier": "none", "original": original, "fetched_at": at, "legacy": True}


def _osf_from_legacy(old: dict) -> dict | None:
    guid = str(old.get("guid")).lower()
    base = {"guid": guid, "url": old.get("url") or f"https://osf.io/{guid}/", "fetched_at": old.get("fetched_at") or _now_iso(), "legacy": True}
    status = old.get("status")
    if status in ("not_found", "forbidden"):
        return {**base, "status": status}
    if status != "ok" or old.get("readme_status") == "error":
        return None
    wiki = str(old.get("readme") or "")[:TEXT_MAX]
    rec = {
        **base,
        "status": "ok",
        "type": old.get("type") or "",
        "title": old.get("title") or "",
        "description": old.get("description") or "",
        "category": old.get("category") or "",
        "tags": old.get("tags") or [],
        "updated": old.get("date_modified") or "",
        "wiki_chars": len(wiki),
    }
    rec["methods"] = methods_in(_haystack(rec, wiki))
    return rec


def _record_from_legacy(old: dict, target: str) -> dict | None:
    """The old cache kept a title only, and cached 404s and nameless pages as
    an empty title; a 0 / 5xx answer was never written, but skip one if seen."""
    try:
        http = int(old.get("http") or 0)
    except (TypeError, ValueError):
        http = 0
    title = tidy_title(old.get("title"))
    if title:
        status = "ok"
    elif http in (404, 410):
        status = "not_found"
    elif http == 200:
        status = "ok"
    elif 400 <= http < 500 and http != 429:
        status = f"http_{http}"
    else:
        return None
    return {
        "target": target, "url": old.get("url") or "", "status": status, "title": title, "description": "",
        "http": http, "fetched_at": old.get("fetched_at") or _now_iso(), "legacy": True,
    }
