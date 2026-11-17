"""The Review screen (P6): the missing pool screened on its abstracts one
batch at a time (pool.py's rv_* columns, app/review/missing.py), the
library's candidates as rows (app/review/view.py), the Review column on the
Code and Datasets screens, and the read routes everyone signed in may use."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.content import pool as P
from app.content import store as st
from app.content.screens import review_state
from app.core import db
from app.review.missing import MissingReview
from app.review.service import ReviewService
from app.review.view import ReviewView
from app.tests import test_content
from app.tests.test_review import DECODER, DEFAULTS

IN_TITLE = "Decoding inner speech from fMRI with a transformer"
IN_ABSTRACT = "We decode inner speech from fMRI with a vision transformer. Data come from the Natural Scenes Dataset (NSD)."
NEAR_TITLE = "A deep model of speech"
NEAR_ABSTRACT = "We decode speech from fMRI with a deep network."
EEG_TITLE = "EEG rhythms"
EEG_ABSTRACT = "We record EEG and MEG from 20 people at rest and describe alpha rhythms."


def works(*rows: tuple[str, str, str]) -> list[dict]:
    return [{"wid": wid, "title": title, "abstract": abstract, "year": 2024, "cited_by": 3, "authors": [["A1", "Ada Lovelace", ""]]}
            for wid, title, abstract in rows]


class PoolReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.pool = P.Pool(self.root / "search.db")
        self.addCleanup(self.pool.close)
        self.store = db.open_store(self.root / "app.db", "k" * 64, False)
        self.review = ReviewService(self.store, DEFAULTS)
        self.missing = MissingReview(self.review, self.pool)
        self.events: list[tuple[str, dict]] = []
        self.missing.publish = lambda name, data: self.events.append((name, data))
        self.pool.put_paper("lib1", "s1", works(("W1", IN_TITLE, IN_ABSTRACT), ("W2", NEAR_TITLE, NEAR_ABSTRACT)), [])
        self.pool.put_paper("lib2", "s2", works(("W1", IN_TITLE, IN_ABSTRACT), ("W3", EEG_TITLE, EEG_ABSTRACT)), works(("W4", "No abstract here", "")))

    def drain(self) -> int:
        n = 0
        while True:
            did = self.missing.step()
            if not did:
                return n
            n += did

    def test_the_pool_is_screened_once_and_read_back(self) -> None:
        self.assertEqual(self.drain(), 4)
        self.assertEqual(self.drain(), 0)
        snap = self.missing.snapshot()
        self.assertEqual(snap["progress"], {"screened": 4, "total": 4})
        self.assertEqual(snap["counts"], {"included": 1, "near_misses": 1, "excluded": 2, "no_abstract": 1})
        [paper] = snap["papers"]
        self.assertEqual(paper["wid"], "W1")
        self.assertEqual(paper["lib_cites"], 2)
        self.assertEqual(paper["datasets"], ["NSD (Natural Scenes Dataset)"])
        self.assertTrue(paper["task"])
        [near] = snap["near_misses"]
        self.assertEqual((near["wid"], near["near_miss"], near["miss_label"]), ("W2", "attention", "names no architecture"))
        self.assertEqual(sum(snap["reasons"].values()), 2)
        self.assertIn("no_attention_abstract", snap["reasons"])
        self.assertTrue(self.events and self.events[0][0] == "review_pool")
        # A skipped work is left out.
        self.assertEqual(self.missing.snapshot({"W1"})["papers"], [])

    def test_new_rules_or_a_changed_abstract_screen_again(self) -> None:
        self.drain()
        self.review.save_setup("default", "Owner", changes=[{"path": "thresholds.abstract.decoding_min.value", "value": 50}])
        self.assertEqual(self.drain(), 4)
        self.assertEqual(self.missing.snapshot()["counts"]["included"], 0)
        self.review.reset()
        self.drain()
        # Only the work whose abstract changed is screened again.
        self.pool.put_paper("lib1", "s1b", works(("W1", IN_TITLE, IN_ABSTRACT), ("W2", NEAR_TITLE, NEAR_ABSTRACT + " It uses self-attention.")), [])
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.missing.snapshot()["counts"]["included"], 2)

    def test_a_work_in_full(self) -> None:
        self.drain()
        found = self.missing.work("W1", [])
        self.assertEqual(found["mode"], "abstract")
        self.assertTrue(found["verdict"]["include"])
        self.assertEqual(found["abstract"], IN_ABSTRACT)
        self.assertIn("TR", found["fields"])
        self.assertIsNone(self.missing.work("W999", []))

    def test_calibration_is_measured(self) -> None:
        judged = [(IN_TITLE, IN_ABSTRACT, True), (NEAR_TITLE, NEAR_ABSTRACT, True), (EEG_TITLE, EEG_ABSTRACT, False)]
        cal = self.missing.calibration(lambda: judged, 1)
        self.assertEqual((cal["recall_found"], cal["recall_total"], cal["recall"]), (1, 2, 0.5))
        self.assertEqual((cal["precision_agreed"], cal["precision_passed"], cal["precision"]), (1, 1, 1.0))
        self.assertEqual(cal["measured_over"], 3)
        # Cached until the verdicts move.
        self.assertIs(self.missing.calibration(lambda: [], 1), cal)
        empty = self.missing.calibration(lambda: [], 2)
        self.assertIsNone(empty["recall"])
        self.assertEqual(empty["configured_precision"], 0.94)


class PoolUpgradeTest(unittest.TestCase):
    def test_a_version_1_pool_keeps_its_works_and_refills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "search.db"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE pool_meta (name TEXT PRIMARY KEY, value TEXT)")
            old.execute("INSERT INTO pool_meta VALUES ('version', '1')")
            old.execute(
                "CREATE TABLE works (id INTEGER PRIMARY KEY, wid TEXT UNIQUE NOT NULL, doi TEXT NOT NULL DEFAULT '',"
                " title TEXT NOT NULL DEFAULT '', title_f TEXT NOT NULL DEFAULT '', journal TEXT NOT NULL DEFAULT '', year INTEGER,"
                " pubdate TEXT NOT NULL DEFAULT '', cited_by INTEGER NOT NULL DEFAULT 0, oa_pdf TEXT NOT NULL DEFAULT '',"
                " authors TEXT NOT NULL DEFAULT '[]', lib_cites INTEGER NOT NULL DEFAULT 0, cites_lib INTEGER NOT NULL DEFAULT 0,"
                " in_lib INTEGER NOT NULL DEFAULT 0)")
            old.execute("INSERT INTO works (wid, title, lib_cites) VALUES ('W1', 'Old work', 1)")
            old.execute("CREATE TABLE filled (lib_key TEXT PRIMARY KEY, sig TEXT NOT NULL)")
            old.execute("INSERT INTO filled VALUES ('lib1', 's1')")
            old.commit()
            old.close()
            pool = P.Pool(path)
            try:
                self.assertEqual(pool.work("W1")["title"], "Old work")
                # Every paper's network is put in again, bringing abstracts.
                self.assertEqual(pool.filled(), {})
                self.assertEqual(pool.review_due("sig", 10), [(1, "Old work", "")])
            finally:
                pool.close()
            again = P.Pool(path)
            again.close()


class ReviewViewTest(test_content.ContentTest):
    def setUp(self) -> None:
        super().setUp()
        self.review = ReviewService(self.store, DEFAULTS, self.content.files)
        self.wanted: set[str] = set()
        self.review.candidates_fn = lambda: set(self.wanted)
        self.content.review = self.review

        class NoFigures:
            def picks_per_paper(self) -> dict:
                return {}

        self.view = ReviewView(self.review, self.content, NoFigures(), self.store)

    def test_candidates_as_rows(self) -> None:
        key = self.key("MindAlign")
        self.wanted.add(key)
        self.review.candidates_changed()
        self.content.reconcile()
        library = self.view.library()
        [row] = library["papers"]
        self.assertEqual((row["key"], row["state"]), (key, "waiting"))
        self.assertEqual(library["counts"]["waiting"], 1)
        self.assertEqual(review_state({st.REVIEW: (st.PENDING, {}, "")}), "waiting")
        self.drain("local")
        library = self.view.library()
        [row] = library["papers"]
        self.assertIn(row["state"], ("included", "borderline", "excluded"))
        self.assertTrue(row["current"])
        if row["state"] == "excluded":
            self.assertTrue(row["why"])
            self.assertNotIn("terms", row["why"][0])
        else:
            self.assertTrue(all(f["value"] or f.get("note") for f in row["fields"].values()))
        self.assertEqual(library["counts"][row["state"]], 1)
        self.assertEqual(len(library["fields"]), len(self.review.rules.fields))
        self.assertTrue(library["tasks"])
        full = self.view.paper(key)
        self.assertIn("evidence", next(iter(full["fields"].values())))
        summary = self.content.files.summaries([key])[key]
        self.assertEqual(review_state(summary), row["state"])
        self.assertEqual(review_state({}), "")

    def test_an_included_paper_carries_its_values(self) -> None:
        key = self.key("MindAlign")
        self.wanted.add(key)
        self.review.candidates_changed()
        stored = self.review.screen("BrainFormer: inner speech", "", "", DECODER)
        self.assertTrue(stored["verdict"]["include"])
        self.content.files.write(key, "review.json", stored)
        self.content.files.settle(key, st.REVIEW, "x", st.DONE, {"include": True}, "")
        [row] = self.view.library()["papers"]
        self.assertEqual(row["state"], "included")
        self.assertEqual(row["fields"]["TR"]["value"], "2000 ms")
        self.assertEqual(row["fields"]["TR"]["source"], "auto")
        json.dumps(row)


try:
    from starlette.testclient import TestClient
except (ImportError, RuntimeError):
    TestClient = None


@unittest.skipIf(TestClient is None, "needs httpx2 (pip install httpx2)")
class ReviewReadRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        from app.tests.test_settings_routes import SettingsRoutesTest

        helper = SettingsRoutesTest("test_settings_are_the_owners_alone")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper

    def test_everyone_signed_in_reads_the_review(self) -> None:
        for who in (self.helper.owner, self.helper.other):
            status, library = self.helper.call("GET", "/api/review/library", cookie=who)
            self.assertEqual(status, 200, library)
            self.assertIn("counts", library)
            self.assertTrue(library["criteria"])
            status, missing = self.helper.call("GET", "/api/review/missing", cookie=who)
            self.assertEqual(status, 200, missing)
            self.assertEqual(missing["papers"], [])
            self.assertIn("calibration", missing)
        self.assertEqual(self.helper.call("GET", "/api/review/paper?key=nope", cookie=self.helper.other)[0], 404)
        self.assertEqual(self.helper.call("GET", "/api/review/missing/work?wid=W1", cookie=self.helper.other)[0], 404)
        self.assertEqual(self.helper.client.get("/api/review/library").status_code, 401)

    def test_on_mcp(self) -> None:
        status, reply = self.helper.call("POST", "/mcp", key=self.helper.key, body={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_review_missing", "arguments": {}},
        })
        self.assertEqual(status, 200)
        self.assertFalse(reply["result"].get("isError"), reply)


if __name__ == "__main__":
    unittest.main()
