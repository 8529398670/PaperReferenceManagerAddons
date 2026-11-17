"""The rows of the Code and Datasets screens, and the enrichment that feeds them.

Code       one row per paper that links code: its repo links, each with what
           GitHub / OSF say about it (description, stars, method tags) and,
           for a link the OCR mangled, the repaired one.
Datasets   one row per paper that links data or names a public collection;
           the screen groups the same rows by dataset itself.

Both carry where each paper is curated (the lists, with positions, and the
tier boards' tiers) and how many of its figures are picked (Figs).

The enrichment (app/content/enrich.py) is network work over unique repos and
records, not papers, so it has its own lane here: one fetch at a time, after
the papers' code and dataset links are in, and never with no token (GitHub,
OSF), so a missing key means "not asked", never "failed".
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.boards import store as boards
from app.boards.board import UNRANKED
from app.content import links
from app.content import store as st
from app.core import db

ENRICH_IDLE_SECONDS = 30.0
ENRICH_PAUSE_SECONDS = 1.0
ENRICH_EVENT_SECONDS = 3.0


def memberships(store: db.Store) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """key -> {"lists": [{slug, name, position}], "tiers": [{slug, name, tier,
    color}]}: every list a paper is on, in one pass over the lists. A tier
    board counts as a list too (position is its row number) and also says
    which tier."""
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for summary in boards.list_boards(store):
        record = boards.get_board(store, summary["slug"])
        if record is None:
            continue
        doc = record.get("doc") or {}
        name = summary.get("name") or summary["slug"]
        sections = {t.get("id"): t for t in doc.get("sections") or []}
        for position, item in enumerate(doc.get("items") or [], start=1):
            key = item.get("key")
            if not key:
                continue
            entry = out.setdefault(key, {"lists": [], "tiers": []})
            entry["lists"].append({"slug": summary["slug"], "name": name, "position": position})
            section = item.get("section")
            if sections and section and section != UNRANKED and section in sections:
                tier = sections[section]
                entry["tiers"].append({"slug": summary["slug"], "name": name, "tier": tier.get("label") or section, "color": tier.get("color") or ""})
    return out


class Screens:
    def __init__(self, content: Any, figures: Any, enricher: Any, store: db.Store) -> None:
        self.content = content
        self.files: st.ContentStore = content.files
        self.figures = figures
        self.enricher = enricher
        self.store = store
        self._links: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._wanted: list[tuple[str, str]] | None = None
        self._last_event = 0.0
        self.publish: Callable[[str, dict[str, Any]], None] = lambda name, data: None
        self._task: asyncio.Task[None] | None = None

    # -- reading the papers ------------------------------------------------------

    def links_of(self, key: str) -> dict[str, Any]:
        path = self.files.dir(key) / "links.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}
        cached = self._links.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        found = self.files.read(key, "links.json") or {}
        with self._lock:
            self._links[key] = (mtime, found)
        return found

    def _paper(self, key: str, stages: dict[str, tuple[str, dict[str, Any], str]], member: dict[str, Any], figs: int) -> dict[str, Any] | None:
        paper = self.content.catalogue.get(key)
        if paper is None:
            return None
        record = paper.record
        oa_state, oa, _ = stages.get(st.OPENALEX, ("", {}, ""))
        mods_state, mods, _ = stages.get(st.MODALITIES, ("", {}, ""))
        return {
            "key": key, "title": record.get("title", ""), "year": record.get("year"), "doi": record.get("doi", ""),
            "journal": record.get("journal", ""), "added": record.get("date_added", ""), "has_pdf": bool(record.get("pdfs")),
            "cites": (oa or {}).get("cited_by_count") if oa_state == st.DONE else None,
            "mods": list((mods or {}).get("used") or []) if mods_state == st.DONE else [],
            "lists": member.get("lists", []), "tiers": member.get("tiers", []), "figs": figs,
        }

    def _inferred(self, rows: list[dict[str, Any]]) -> dict[str, set[str]]:
        """Repo -> the methods the papers linking it used (their modality tags,
        which come from the title, abstract and methods section -- never the
        full text, whose reference list would name everything)."""
        from app.content import enrich

        names = set(enrich.METHOD_NAMES)
        out: dict[str, set[str]] = {}
        for row in rows:
            used = {m for m in row["mods"] if m in names}
            for link in row["code"]:
                if link.get("repo"):
                    out.setdefault(link["repo"], set()).update(used)
        return out

    def _code_link(self, link: dict[str, Any]) -> dict[str, Any]:
        from app.content import enrich

        out = {"url": link.get("url", ""), "host": link.get("host", ""), "where": link.get("where", "")}
        repo = enrich.github_repo(out["url"])
        if repo:
            owner, name = repo
            out["repo"] = f"github:{owner}/{name}".lower()
            info = self.enricher.github(owner, name) if self.enricher else None
            if info is None:
                out["info"] = {"status": "pending"}
            else:
                out["info"] = {k: info.get(k) for k in ("status", "description", "stars", "language", "topics", "updated", "archived", "methods")}
                if info.get("status") == "not_found":
                    repair = self.enricher.repair(owner, name)
                    if repair and repair.get("url"):
                        out["repaired"] = {k: repair.get(k) for k in ("url", "tier", "confidence", "original")}
                        fixed = enrich.github_repo(repair["url"])
                        better = self.enricher.github(*fixed) if fixed else None
                        if better and better.get("status") == "ok":
                            out["info"] = {k: better.get(k) for k in ("status", "description", "stars", "language", "topics", "updated", "archived", "methods")}
            return out
        guid = enrich.osf_guid(out["url"])
        if guid:
            out["repo"] = f"osf:{guid}".lower()
            info = self.enricher.osf(guid) if self.enricher else None
            out["info"] = {"status": "pending"} if info is None else {
                k: info.get(k) for k in ("status", "title", "description", "category", "methods")
            }
        return out

    def code_rows(self) -> list[dict[str, Any]]:
        member = memberships(self.store)
        figs = self.figures.picks_per_paper()
        rows = []
        for key, stages in self.files.summaries().items():
            state, summary, _ = stages.get(st.CODE, ("", {}, ""))
            if state != st.DONE or not summary.get("n"):
                continue
            row = self._paper(key, stages, member.get(key, {}), figs.get(key, 0))
            if row is None:
                continue
            row["code"] = [self._code_link(link) for link in self.links_of(key).get("code") or []]
            if row["code"]:
                rows.append(row)
        inferred = self._inferred(rows)
        for row in rows:
            for link in row["code"]:
                if link.get("repo"):
                    confirmed = set((link.get("info") or {}).get("methods") or [])
                    link["inferred"] = sorted(inferred.get(link["repo"], set()) - confirmed)
        return rows

    def _data_link(self, link: dict[str, Any]) -> dict[str, Any]:
        from app.content import enrich

        out = {k: link.get(k) for k in ("url", "host", "where", "accession") if link.get(k)}
        url = out.get("url", "")
        repo = enrich.github_repo(url)
        guid = None if repo else enrich.osf_guid(url)
        if repo or guid:
            info = (self.enricher.github(*repo) if repo else self.enricher.osf(guid)) if self.enricher else None
            out["target"] = f"github:{repo[0]}/{repo[1]}".lower() if repo else f"osf:{guid}".lower()
            out["info"] = {"status": "pending"} if info is None else {
                "status": info.get("status"), "title": info.get("title") or info.get("full_name") or "", "description": info.get("description") or "",
            }
            return out
        target = enrich.record_target(url)
        if target:
            out["target"] = target
            info = self.enricher.record(target) if self.enricher else None
            out["info"] = {"status": "pending"} if info is None else {k: info.get(k) for k in ("status", "title", "description")}
        return out

    def dataset_rows(self) -> list[dict[str, Any]]:
        member = memberships(self.store)
        figs = self.figures.picks_per_paper()
        rows = []
        for key, stages in self.files.summaries().items():
            state, summary, _ = stages.get(st.DATASETS, ("", {}, ""))
            if state != st.DONE or not (summary.get("n") or summary.get("names")):
                continue
            row = self._paper(key, stages, member.get(key, {}), figs.get(key, 0))
            if row is None:
                continue
            found = self.links_of(key)
            row["data"] = [self._data_link(link) for link in found.get("data") or []]
            row["names"] = [
                {"name": n.get("name", ""), "url": n.get("url") or links.home(n.get("name", "")), "description": n.get("description") or links.describe(n.get("name", ""))}
                for n in found.get("names") or [] if n.get("name")
            ]
            row["code_n"] = len(found.get("code") or [])
            if row["data"] or row["names"]:
                rows.append(row)
        return rows

    # -- the enrichment lane -------------------------------------------------------

    def wanted(self) -> list[tuple[str, str]]:
        """What the enricher should fetch: every unique GitHub repo and OSF
        node the papers link (code or data), and every data record it can
        describe. Rebuilt when a paper's links change."""
        from app.content import enrich

        if self._wanted is not None:
            return self._wanted
        seen: set[tuple[str, str]] = set()
        out: list[tuple[str, str]] = []

        def add(item: tuple[str, str]) -> None:
            if item not in seen:
                seen.add(item)
                out.append(item)

        papers = sorted(self.content.catalogue.all(), key=lambda p: p.record.get("date_added") or "", reverse=True)
        for paper in papers:
            found = self.links_of(paper.key)
            for link in (found.get("code") or []) + (found.get("data") or []):
                url = link.get("url") or ""
                repo = enrich.github_repo(url)
                if repo:
                    add(("github", f"{repo[0]}/{repo[1]}"))
                    continue
                guid = enrich.osf_guid(url)
                if guid:
                    add(("osf", guid))
            for link in found.get("data") or []:
                url = link.get("url") or ""
                if enrich.github_repo(url) or enrich.osf_guid(url):
                    continue
                target = enrich.record_target(url)
                if target:
                    add(("record", target))
        self._wanted = out
        return out

    def heard(self, name: str, data: dict[str, Any]) -> None:
        """A paper's links changed: rebuild what to fetch."""
        if name == "paper" and data.get("stage") in (st.CODE, st.DATASETS):
            self._wanted = None

    def step(self) -> str | None:
        if self.enricher is None:
            return None
        did = self.enricher.step(self.wanted())
        if did:
            now = time.monotonic()
            if now - self._last_event >= ENRICH_EVENT_SECONDS:
                self._last_event = now
                self.publish("enrich", {"did": did})
        return did

    def start(self) -> None:
        self._task = asyncio.create_task(self._lane())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _lane(self) -> None:
        # Let the server finish starting (and the catalogue load) first.
        await asyncio.sleep(10)
        try:
            # The old app's GitHub / OSF answers (linked in by import-legacy),
            # so none is asked again; skips what is already converted.
            if self.enricher is not None and (self.files.root / "legacy").is_dir():
                seeded = await asyncio.to_thread(self.enricher.seed_legacy, self.files.root / "legacy")
                if any(seeded.values()):
                    print(f"[enrich] converted the old caches: {seeded}", flush=True)
            # The method-figure matches of every caption, once, so the first
            # Figures screen does not wait for them.
            await asyncio.to_thread(self.figures.listing, "method", limit=1)
        except Exception as error:  # noqa: BLE001
            print(f"[enrich] warm-up: {error!r}", flush=True)
        while True:
            try:
                did = await asyncio.to_thread(self.step)
            except Exception as error:  # noqa: BLE001 -- one bad answer must never stop the lane
                print(f"[enrich] {error!r}", flush=True)
                did = None
            await asyncio.sleep(ENRICH_PAUSE_SECONDS if did else ENRICH_IDLE_SECONDS)


__all__ = ["Path"]
