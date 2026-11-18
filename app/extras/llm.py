"""Three chat APIs by plain HTTP, for the paper summaries. Ported from the old
prma src/llm/llm.py, without its SDK-free `requests` dependency (urllib is
enough) and without its environment-variable fallback: keys and models are
in config.yaml's llm: section and nowhere else.

  claude  POST https://api.anthropic.com/v1/messages
  openai  POST https://api.openai.com/v1/chat/completions
  gemini  POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent

One call answers one (paper, section): the prompt asks for a HASHTAGS: line
and a SUMMARY: block, and parse() is forgiving when the model strays.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

PROVIDERS = ("claude", "openai", "gemini")
DEFAULT_MODELS = {"claude": "claude-opus-5-5", "openai": "gpt-5.4-nano", "gemini": "gemini-2.5-flash"}
# Input characters each provider is given at most (about 3.5-4 a token);
# longer text keeps its first 60% and last 40%, marked where it was cut.
INPUT_CHAR_BUDGETS = {"claude": 600_000, "openai": 400_000, "gemini": 2_500_000}
TEMPLATE_OVERHEAD = 8_000
RETRY_STATUS = (408, 425, 429, 500, 502, 503, 504, 529)
MAX_TRIES = 5
TIMEOUT_SECONDS = 180
MAX_TOKENS = 4096


class LlmError(Exception):
    """The provider could not be asked, or refused."""


@dataclass
class Choice:
    provider: str
    model: str
    api_key: str


def choose(settings: Any) -> Choice | None:
    """The provider and model config.yaml's llm: section picks, or None when
    no key is set. provider "" takes the first with a key: claude, openai,
    gemini."""
    keys = {"claude": settings.anthropic_api_key, "openai": settings.openai_api_key, "gemini": settings.gemini_api_key}
    provider = settings.provider or next((p for p in PROVIDERS if keys[p]), "")
    if not provider or not keys.get(provider):
        return None
    return Choice(provider, settings.model or DEFAULT_MODELS[provider], keys[provider])


def clip(text: str, provider: str) -> tuple[str, bool]:
    budget = INPUT_CHAR_BUDGETS.get(provider, 300_000) - TEMPLATE_OVERHEAD
    if len(text) <= budget:
        return text, False
    head = int(budget * 0.6)
    tail = budget - head
    marker = f"\n\n[ ... {len(text) - budget} characters cut to fit the context window ... ]\n\n"
    return text[:head] + marker + text[-tail:], True


Poster = Callable[[str, dict[str, str], bytes], tuple[int, dict[str, str], bytes]]


def _post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, error.read() or b""


_RETRY_BODY = re.compile(r"try\s+again\s+in\s+([\d.]+)\s*s", re.IGNORECASE)


class Client:
    def __init__(self, choice: Choice, poster: Poster | None = None) -> None:
        self.choice = choice
        self.poster = poster or _post
        self.sleep: Callable[[float], None] = time.sleep

    def _send(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"content-type": "application/json", **headers}
        last = ""
        for attempt in range(MAX_TRIES):
            try:
                status, answer_headers, raw = self.poster(url, headers, body)
            except (OSError, socket.timeout) as error:
                last = f"network: {error}"
                status, answer_headers, raw = 0, {}, b""
            if status == 200:
                try:
                    return json.loads(raw)
                except ValueError:
                    raise LlmError(f"{self.choice.provider} sent something that is not JSON") from None
            if status and status not in RETRY_STATUS:
                raise LlmError(f"{self.choice.provider} answered {status}: {_message(raw)}")
            if status:
                last = f"{self.choice.provider} answered {status}"
            if attempt == MAX_TRIES - 1:
                break
            wait = min(60.0, 5.0 * 2**attempt)
            hinted = answer_headers.get("retry-after") or ""
            match = _RETRY_BODY.search(raw.decode("utf-8", "replace")) if raw else None
            try:
                if hinted:
                    wait = float(hinted) + 1
                elif match:
                    wait = float(match.group(1)) + 1
            except ValueError:
                pass
            self.sleep(min(wait, 120.0))
        raise LlmError(last or f"{self.choice.provider} did not answer")

    def complete(self, system: str, user: str) -> str:
        c = self.choice
        if c.provider == "claude":
            data = self._send(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": c.api_key, "anthropic-version": "2023-06-01"},
                {"model": c.model, "max_tokens": MAX_TOKENS, "system": system, "messages": [{"role": "user", "content": user}]},
            )
            return "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text").strip()
        if c.provider == "openai":
            data = self._send(
                "https://api.openai.com/v1/chat/completions",
                {"authorization": f"Bearer {c.api_key}"},
                {"model": c.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            )
            choices = data.get("choices") or []
            return ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        if c.provider == "gemini":
            data = self._send(
                f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(c.model, safe='.-')}:generateContent",
                {"x-goog-api-key": c.api_key},
                {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                 "generationConfig": {"temperature": 0.2}},
            )
            candidates = data.get("candidates") or []
            parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
            return "".join(p.get("text", "") for p in parts).strip()
        raise LlmError(f"unknown provider {c.provider}")


def _message(raw: bytes) -> str:
    """The error message a provider's JSON carries, else the start of it."""
    try:
        data = json.loads(raw)
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return str((data[0].get("error") or {}).get("message") or data[0])[:300]
    except ValueError:
        pass
    return raw.decode("utf-8", "replace")[:300]


# -- the prompt and the answer -------------------------------------------------------------

_MARKER = re.compile(r"^---\s*(SYSTEM|USER)\s*---\s*$", re.IGNORECASE | re.MULTILINE)
_HASHTAGS = re.compile(r"^\s*HASHTAGS\s*:\s*(.+?)$", re.IGNORECASE | re.MULTILINE)
_SUMMARY = re.compile(r"^\s*SUMMARY\s*:\s*\n?(.*)\Z", re.IGNORECASE | re.DOTALL | re.MULTILINE)

BUILTIN_SYSTEM = (
    "You are a scientific literature summarizer. You are given ONE section of an academic paper and must produce a "
    "STRUCTURED, DETAILED OVERVIEW of that section. Do not editorialize; do not introduce information that is not in the "
    "source; do not omit specifics like sample sizes, techniques, numerical values, statistical tests, datasets, study "
    "design, patient counts, inclusion / exclusion criteria, or named variables. If the source is empty, garbled, or "
    "clearly truncated, say so explicitly."
)
BUILTIN_USER = """Paper title: {title}
DOI: {doi}
Section: {section_display}

Produce EXACTLY two blocks in this exact format, in this order, with the literal "HASHTAGS:" and "SUMMARY:" labels:

HASHTAGS: <3 to 8 single-token hashtags, each starting with '#', no spaces inside a tag>

SUMMARY:
<a detailed structured overview of the section. Use short paragraphs or bullet points. Preserve specific details. Do not invent or extrapolate.>

--- BEGIN {section_display} SECTION ---
{text}
--- END {section_display} SECTION ---
"""


def parse_prompt(raw: str) -> tuple[str, str] | None:
    """A prompt file's SYSTEM and USER blocks; None when either is missing.
    Anything before the first marker is a comment."""
    markers = list(_MARKER.finditer(raw))
    blocks: dict[str, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(raw)
        blocks[marker.group(1).upper()] = raw[marker.end():end].strip("\n")
    if "SYSTEM" not in blocks or "USER" not in blocks:
        return None
    return blocks["SYSTEM"], blocks["USER"]


def fill(template: str, title: str, doi: str, section_display: str, text: str) -> str:
    """The placeholders a prompt may use; any other {name} is left as typed."""
    values = {"title": title or "(untitled)", "doi": doi or "(unknown)", "section_display": section_display, "text": text}
    return re.sub(r"\{(title|doi|section_display|text)\}", lambda m: values[m.group(1)], template)


def parse_answer(raw: str) -> dict[str, str]:
    """{hashtags, summary} out of the answer; everything as the summary when
    the format was not followed."""
    if not raw:
        return {"hashtags": "", "summary": ""}
    tags = _HASHTAGS.search(raw)
    found = _SUMMARY.search(raw)
    if found:
        summary = found.group(1).strip()
    elif tags:
        summary = (raw[:tags.start()] + raw[tags.end():]).strip()
    else:
        summary = raw.strip()
    hashtags = " ".join(t for t in (tags.group(1).split() if tags else []) if t.startswith("#"))
    return {"hashtags": hashtags, "summary": summary}
