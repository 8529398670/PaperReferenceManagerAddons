"""Each paper's derived content: the queue (what is queued, when it is
redone, failures and backoff, opening a paper), the OpenAlex stage against a
fake OpenAlex, the missing pool it fills (counters, dedup against the library,
search and tiered sort), and the routes. Against the small fake Zotero."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.content import openalex, pool as pool_mod
from app.content import store as st
from app.content.service import ContentService
from app.core import db
from app.library.catalogue import Catalogue
from app.library.zotero import Library
from app.search.index import Index
from app.tests.zotero_fixture import sample

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    openalex_enabled: bool = True
    openalex_api_key: str = ""


def work(wid: str, title: str, doi: str = "", refs: tuple[str, ...] = (), cited: int = 0, authors: tuple[str, ...] = ("A1",)) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}" if doi else None, "title": title,
        "publication_year": 2020, "cited_by_count": cited, "referenced_works": [f"https://openalex.org/{w}" for w in refs],
        "abstract_inverted_index": {"about": [1], "A": [0], title.split()[0].lower(): [2]},
        "authorships": [{"author": {"id": f"https://openalex.org/{a}", "display_name": f"Author {a}"}} for a in authors],
        "primary_location": {"source": {"display_name": "Journal"}},
    }


class FakeOpenAlex:
    """Answers like api.openalex.org from a dict of works."""

    def __init__(self) -> None:
        self.works: dict[str, dict[str, Any]] = {}
        self.by_doi: dict[str, str] = {}
        self.citers: dict[str, list[str]] = {}
        self.calls: list[str] = []
        self.fail = False

    def add(self, w: dict[str, Any], citers: tuple[str, ...] = ()) -> None:
        wid = openalex.wid_of(w["id"])
        self.works[wid] = w
        if w.get("doi"):
            self.by_doi[w["doi"].replace("https://doi.org/", "").lower()] = wid
        self.citers[wid] = list(citers)

    def __call__(self, url: str) -> tuple[int, dict[str, str], bytes]:
        from urllib.parse import parse_qs, unquote, urlparse

        self.calls.append(url)
        if self.fail:
            return 503, {}, b""
        parsed = urlparse(url)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        path = unquote(parsed.path)
        if "/works/https://doi.org/" in path:
            wid = self.by_doi.get(path.split("/works/https://doi.org/", 1)[1].lower())
            return (200, {}, json.dumps(self.works[wid]).encode()) if wid else (404, {}, b"")
        if path.startswith("/works/W"):
            wid = path.rsplit("/", 1)[1]
            return (200, {}, json.dumps(self.works[wid]).encode()) if wid in self.works else (404, {}, b"")
        flt = params.get("filter", "")
        if flt.startswith("ids.openalex:"):
            found = [self.works[w] for w in flt.split(":", 1)[1].split("|") if w in self.works]
            return 200, {}, json.dumps({"results": found}).encode()
        if flt.startswith("cites:"):
            found = [self.works[w] for w in self.citers.get(flt.split(":", 1)[1], []) if w in self.works]
            return 200, {}, json.dumps({"results": found, "meta": {"next_cursor": None}}).encode()
        return 404, {}, b""


class ContentTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root = root
        self.zotero = sample(root / "Zotero")
        self.index = Index(root / "cache" / "search.db")
        self.addCleanup(self.index.close)
        self.catalogue = Catalogue(Library(root / "Zotero", root / "cache"), self.index)
        self.catalogue.sync()
        self.store = db.open_store(root / "app.db", "k" * 64, False)
        self.settings = Settings()
        self.vocab = root / "modalities.yaml"
        self.vocab.write_text((ROOT / "config" / "modalities.yaml").read_text())
        self.content = ContentService(root / "papers", root / "cache" / "search.db", self.catalogue, self.store, self.vocab, lambda: self.settings)
        self.addCleanup(self.content.close)
        self.fake = FakeOpenAlex()
        self.content.client_factory = lambda key: self._client()
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.content.publish = lambda name, data: self.events.append((name, data))
        # The two papers with a DOI, and their networks.
        self.fake.add(work("W1", "Temporal autocorrelation", "10.1006/nimg.2001.0931", refs=("W10", "W11"), cited=1), citers=("W20",))
        self.fake.add(work("W2", "MindAlign decoding", "10.48550/arXiv.2606.20696", refs=("W10", "W12", "W1"), cited=2), citers=("W20", "W21"))
        for wid, title in (("W10", "Shared reference"), ("W11", "Only in one"), ("W12", "Another reference"), ("W20", "Citing both"), ("W21", "Citing one")):
            self.fake.add(work(wid, title, authors=("A9", wid)))

    def _client(self) -> openalex.Client:
        client = openalex.Client("", opener=self.fake)
        client.sleep = lambda seconds: None
        return client

    def key(self, title_start: str) -> str:
        return next(p.key for p in self.catalogue.all() if p.record["title"].startswith(title_start))

    def drain(self, lane: str = "local") -> int:
        n = 0
        while self.content.step(lane):
            n += 1
        return n

    # -- the queue -----------------------------------------------------------------

    def test_reconcile_queues_each_stage_once(self) -> None:
        # Five light stages each, and figures for the two with a PDF (the
        # heavy stages are only ever queued, never run by the server).
        self.assertEqual(self.content.reconcile(), 3 * 5 + 2)
        self.assertEqual(self.content.reconcile(), 0)
        counts = self.content.files.counts()
        self.assertEqual(counts["openalex"]["pending"], 3)
        self.assertEqual(counts["methods"]["pending"], 3)
        self.assertEqual(counts["figures"]["pending"], 2)
        self.assertEqual(counts["ocr"]["pending"], 0)

    def test_local_stages_fill_and_badge(self) -> None:
        self.content.reconcile()
        self.drain("local")
        counts = self.content.files.counts()
        # The review stage is only for papers on a list (app/review/), and
        # this service has no screener: test_review.py covers it.
        for stage in st.LOCAL:
            if stage != st.REVIEW:
                self.assertEqual(counts[stage]["done"], 3, stage)
        key = self.key("MindAlign")
        badge = self.content.badges([key])[key]
        self.assertEqual(badge["states"]["methods"], "done")
        self.assertIn("fMRI", badge["mods"])
        self.assertTrue(any(name == "paper" and data["key"] == key for name, data in self.events))

    def test_changed_text_redoes_only_local_stages(self) -> None:
        self.content.reconcile()
        self.drain("local")
        key = self.key("MindAlign")
        path = self.zotero.fulltext_path(self.catalogue.get(key).record["zkey"])
        path.write_text("Now with EEG and a repository at https://github.com/example/mindalign.")
        os.utime(path, (time.time() + 5, time.time() + 5))
        self.catalogue.sync(force=True)
        queued = self.content.reconcile()
        self.assertEqual(queued, 4)
        self.drain("local")
        self.assertEqual(self.content.badges([key])[key]["code"], 1)

    def test_editing_the_vocabulary_retags(self) -> None:
        self.content.reconcile()
        self.drain("local")
        self.vocab.write_text("modalities:\n  - label: EEG\n    phrases: [electroencephalogra]\n")
        os.utime(self.vocab, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.content.reconcile(), 3)  # every paper, text or not

    def test_opening_a_paper_puts_it_first(self) -> None:
        self.content.reconcile()
        last = self.key("Temporal")
        self.assertNotEqual(self.content.files.next_due(st.LOCAL, time.time())[0], last)
        self.content.open(last)
        self.assertEqual(self.content.files.next_due(st.LOCAL, time.time())[0], last)

    def test_not_ready_catalogue_drops_nothing(self) -> None:
        self.content.reconcile()
        self.drain("local")
        empty = Catalogue(Library(self.root / "Zotero", self.root / "cache2"), Index(self.root / "cache2" / "search.db"))
        self.content.catalogue = empty
        self.assertFalse(self.content.step("local"))
        self.assertEqual(self.content.reconcile(), 0)
        self.assertEqual(self.content.files.counts()["methods"]["done"], 3)

    # -- OpenAlex and the pool ------------------------------------------------------

    def test_openalex_fills_the_pool(self) -> None:
        self.content.reconcile()
        self.drain("net")
        counts = self.content.files.counts()["openalex"]
        # The paper with no DOI is looked up by title, which the fake does not know.
        self.assertEqual((counts["done"], counts["not_found"]), (2, 1))
        pool = self.content.pool
        found = {row["wid"]: row for row in pool.search(limit=50)["rows"]}
        # W1 is a library paper (its own OpenAlex id), so not missing.
        self.assertNotIn("W1", found)
        self.assertEqual(found["W10"]["lib_cites"], 2)
        self.assertEqual(found["W20"]["cites_lib"], 2)
        self.assertEqual(found["W20"]["conn"], 2)
        self.assertEqual(pool.totals()["refs"], 3)
        self.assertEqual(pool.totals()["citing"], 2)

    def test_not_found_is_asked_again_later(self) -> None:
        """A paper OpenAlex had no record of is looked up again once its wait
        (by how new the paper is) has passed, and only then."""
        from app.content import service as sv
        from app.content import store as st

        self.content.reconcile()
        self.drain("net")
        key = next(k for (k, s), (state, _) in self.content.files.rows().items() if s == st.OPENALEX and state == st.NOT_FOUND)
        calls = len(self.fake.calls)
        # Within the wait: nothing is asked.
        self.content._recheck_after = 0.0
        self.drain("net")
        self.assertEqual(len(self.fake.calls), calls)
        # Past it: asked again (still not there, so not found again).
        db = self.content.files._db
        db.execute("UPDATE tasks SET done_at = done_at - ? WHERE key = ? AND stage = ?", (31 * 86400, key, st.OPENALEX))
        self.content._recheck_after = 0.0
        self.assertTrue(self.content.step("net"))
        self.assertGreater(len(self.fake.calls), calls)
        self.assertEqual(self.content.files.of(key)[st.OPENALEX]["state"], st.NOT_FOUND)
        # The wait grows with the paper's age.
        now = 2_000_000_000.0
        self.assertEqual(sv.recheck_wait("2033-05-17 00:00:00", now), 86400.0)
        self.assertEqual(sv.recheck_wait("2033-01-01 00:00:00", now), 7 * 86400.0)
        self.assertEqual(sv.recheck_wait("2020-01-01 00:00:00", now), 30 * 86400.0)
        self.assertEqual(sv.recheck_wait("", now), 30 * 86400.0)

    def test_removing_a_paper_takes_its_network_back(self) -> None:
        self.content.reconcile()
        self.drain("net")
        self.zotero.delete(self.catalogue.get(self.key("MindAlign")).record["zkey"])
        self.catalogue.sync(force=True)
        self.content.reconcile()
        found = {row["wid"]: row for row in self.content.pool.search(limit=50)["rows"]}
        self.assertEqual(found["W10"]["lib_cites"], 1)
        self.assertNotIn("W12", found)
        self.assertNotIn("W21", found)

    def test_search_sort_and_skips(self) -> None:
        self.content.reconcile()
        self.drain("net")
        pool = self.content.pool
        hits = pool.search("shared OR citing", sort=[("relevance", True)])
        self.assertEqual({row["wid"] for row in hits["rows"]}, {"W10", "W20", "W21"})
        rows = pool.search(sort=pool_mod.parse_sort("conn:desc,title:asc"))["rows"]
        self.assertEqual([r["wid"] for r in rows][:2], ["W20", "W10"])  # both 2 connections; "Citing" < "Shared"
        self.content.skip(["W10"], True, "test")
        hidden = pool.search(skipped=self.content.skipped())
        self.assertNotIn("W10", {row["wid"] for row in hidden["rows"]})
        self.assertEqual(hidden["skipped"], 1)
        shown = pool.search(skipped=self.content.skipped(), show_skipped=True)
        self.assertTrue(next(r for r in shown["rows"] if r["wid"] == "W10")["skipped"])
        self.assertEqual(pool.search(paper=self.key("Temporal"))["counts"]["refs"], 2)
        self.assertEqual(pool.search("-shared")["counts"]["all"], 4)

    def test_failure_backs_off_and_retry_asks_again(self) -> None:
        self.content.reconcile()
        self.fake.fail = True
        self.drain("net")
        counts = self.content.files.counts()["openalex"]
        self.assertEqual(counts["failed"], 3)
        self.assertIsNone(self.content.files.next_due((st.OPENALEX,), time.time()))
        self.fake.fail = False
        self.assertEqual(self.content.files.retry(stage=st.OPENALEX), 3)
        self.drain("net")
        self.assertEqual(self.content.files.counts()["openalex"]["done"], 2)

    def test_meta_feeds_the_list_ops(self) -> None:
        self.content.reconcile()
        self.drain("local")
        key = self.key("MindAlign")
        meta = self.content.meta([key], True)[key]
        self.assertIn("fMRI", meta["mods"])
        self.assertIn("code", meta)


class RetryAfterTest(unittest.TestCase):
    def test_429_waits_then_answers(self) -> None:
        answers = [(429, {"retry-after": "2"}, b""), (200, {}, b'{"id": "https://openalex.org/W5"}')]
        slept: list[float] = []
        client = openalex.Client("k", opener=lambda url: answers.pop(0))
        client.sleep = slept.append
        self.assertEqual(openalex.wid_of(client.by_doi("10.1/x")["id"]), "W5")
        self.assertEqual(slept, [2.0])

    def test_404_is_not_found(self) -> None:
        client = openalex.Client("", opener=lambda url: (404, {}, b""))
        with self.assertRaises(openalex.NotFound):
            client.by_doi("10.1/x")


try:
    from app.tests.route_support import RoutesTestCase
except unittest.SkipTest:  # pragma: no cover -- no httpx2
    RoutesTestCase = None  # type: ignore[assignment,misc]


if RoutesTestCase is not None:

    class ContentRoutesTest(RoutesTestCase):
        def test_routes_answer(self) -> None:
            headers = {"Authorization": f"Bearer {self.user_key}"}
            status = self.client.get("/api/content/status", headers=headers)
            self.assertEqual(status.status_code, 200, status.text)
            self.assertIn("openalex", status.json()["stages"])
            missing = self.client.get("/api/missing?sort=year:desc,conn:desc", headers=headers)
            self.assertEqual(missing.status_code, 200, missing.text)
            self.assertEqual(missing.json()["counts"], {"all": 0, "refs": 0, "citing": 0})
            self.assertEqual(self.client.get("/api/missing/authors", headers=headers).status_code, 200)
            badges = self.client.post("/api/papers/badges", json={"keys": ["x"]}, headers=headers)
            self.assertEqual(badges.status_code, 200, badges.text)
            self.assertEqual(self.client.get("/api/paper/content?key=nope", headers=headers).status_code, 404)
            self.assertEqual(self.client.post("/api/papers/retry", json={"stage": "bogus"}, headers=headers).status_code, 400)
            skip = self.client.post("/api/missing/skip", json={"wids": ["W1"]}, headers=headers)
            self.assertEqual(skip.json()["changed"], 1)
            papers = self.client.get("/api/content/papers?stage=openalex&state=errors", headers=headers)
            self.assertEqual(papers.status_code, 200, papers.text)
            self.assertEqual(self.client.get("/api/papers?has=code", headers=headers).status_code, 200)
            self.assertEqual(self.client.get("/api/papers?has=bogus", headers=headers).status_code, 400)


if __name__ == "__main__":
    unittest.main()
