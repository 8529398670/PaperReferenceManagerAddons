"""Phase 5: the heavy stages' queue (claims, leases, the worker's heartbeat, the
server hearing what a worker finished), the Figures screen's picks and
listing, the Code / Datasets rows, the legacy figure import and the .xlsx
export. Against the small fake Zotero; no torch, no network."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from typing import Any

from app.content import legacy
from app.content import store as st
from app.content.figures import Figures, clean_caption, split_id
from app.content.screens import Screens, memberships
from app.tests import test_content as tc


class ContentTest(unittest.TestCase):
    """The content tests' fake library and queue, without their tests."""

    setUp = tc.ContentTest.setUp
    _client = tc.ContentTest._client
    key = tc.ContentTest.key


def png(width: int, height: int) -> bytes:
    """A PNG header that says its size: all png_size reads."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"


class HeavyQueueTest(ContentTest):
    def test_claim_is_exclusive_and_a_lease_runs_out(self) -> None:
        self.content.reconcile()
        files = self.content.files
        first = files.claim(st.HEAVY, "w1", now=1000.0, lease=60)
        self.assertIsNotNone(first)
        self.assertEqual(first["stage"], st.FIGURES)
        self.assertTrue(first["input"]["pdf"].endswith(".pdf"))
        second = files.claim(st.HEAVY, "w2", now=1000.0, lease=60)
        self.assertNotEqual((first["key"], first["stage"]), (second["key"], second["stage"]))
        # Nothing else is due until a lease runs out; then w1's task is.
        self.assertIsNone(files.claim(st.HEAVY, "w3", now=1001.0, lease=60))
        again = files.claim(st.HEAVY, "w3", now=1061.0, lease=60)
        self.assertIn(again["key"], (first["key"], second["key"]))

    def test_server_never_takes_heavy_tasks_and_restart_keeps_a_workers_claim(self) -> None:
        self.content.reconcile()
        while self.content.step("local"):
            pass
        counts = self.content.files.counts()
        self.assertEqual(counts["figures"]["pending"], 2)
        task = self.content.files.claim(st.HEAVY, "w1")
        reopened = st.ContentStore(self.root / "papers")
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.of(task["key"])[st.FIGURES]["state"], st.RUNNING)

    def test_finish_is_heard_with_figures_and_ocr(self) -> None:
        self.content.reconcile()
        heard: list[str] = []
        self.content.on_figures = heard.append
        task = self.content.files.claim(st.HEAVY, "w1")
        self.content.files.write(task["key"], "figures.json", {"figures": [{"n": 1, "caption": "Figure 1. The architecture", "dup": False}]})
        self.content.files.finish(task["key"], st.FIGURES, task["sig"], st.DONE, {"n": 1, "boxes": 1})
        self.content._heard = 0
        self.events.clear()
        self.assertGreaterEqual(self.content.watch(), 1)
        self.assertIn(task["key"], heard)
        self.assertTrue(any(name == "paper" and data["stage"] == st.FIGURES for name, data in self.events))
        self.assertEqual(self.content.badges([task["key"]])[task["key"]]["figures"], 1)
        self.assertEqual(self.content.paper(task["key"])["figures"][0]["n"], 1)

    def test_workers_check_in_and_go_stale(self) -> None:
        files = self.content.files
        files.beat({"id": "w1", "host": "h", "pid": 1, "doing": "figures k", "stages": ["figures"]})
        self.assertTrue(files.workers()[0]["alive"])
        self.assertFalse(files.workers(now=time.time() + 600)[0]["alive"])
        files.gone("w1")
        self.assertEqual(files.workers(), [])

    def test_version_one_file_is_upgraded_in_place(self) -> None:
        import sqlite3

        path = self.root / "old"
        path.mkdir()
        db = sqlite3.connect(path / "content.db")
        db.execute(
            "CREATE TABLE tasks (key TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL, sig TEXT NOT NULL DEFAULT '',"
            " priority REAL NOT NULL DEFAULT 0, added TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,"
            " error TEXT NOT NULL DEFAULT '', first_failed REAL, last_failed REAL, next_at REAL NOT NULL DEFAULT 0,"
            " done_at REAL, summary TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (key, stage))"
        )
        db.execute("INSERT INTO tasks (key, stage, state, sig) VALUES ('k', 'openalex', 'done', 'doi:x')")
        db.execute("PRAGMA user_version = 1")
        db.commit()
        db.close()
        upgraded = st.ContentStore(path)
        self.addCleanup(upgraded.close)
        self.assertEqual(upgraded.rows()[("k", "openalex")], ("done", "doi:x"))


class FiguresTest(ContentTest):
    def setUp(self) -> None:
        super().setUp()
        self.keywords = self.root / "method-images.txt"
        self.keywords.write_text("[strong]\narchitecture\nschematic\n[weak]\nlayer\n")
        self.figures = Figures(self.content, self.store, self.keywords)
        self.content.reconcile()
        self.paper_key = self.key("MindAlign")
        sig = self.content.files.rows()[(self.paper_key, st.FIGURES)][1]
        self.content.files.write(self.paper_key, "figures.json", {"figures": [
            {"n": 1, "page": 2, "caption": "Figure 1. The model architecture: an encoder.", "dup": False},
            {"n": 2, "page": 3, "caption": "Figure 2. Results across subjects.", "dup": False},
            {"n": 3, "page": 3, "caption": "Figure 2 again", "dup": True},
        ]})
        self.content.files.settle(self.paper_key, st.FIGURES, sig, st.DONE, {"n": 2, "boxes": 3})

    def test_listing_views_and_picks(self) -> None:
        everything = self.figures.listing("all")
        self.assertEqual(everything["total"], 1)
        self.assertEqual([f["n"] for f in everything["papers"][0]["figures"]], [1, 2])
        method = self.figures.listing("method")
        self.assertEqual([f["n"] for f in method["papers"][0]["figures"]], [1])
        self.assertIn("architecture", method["terms"][0]["name"])
        # A pick of the duplicate shows it; the other view says it is picked there.
        self.figures.pick("all", [f"{self.paper_key}#figure-3", f"{self.paper_key}#figure-1"], True)
        self.assertEqual(self.figures.state("all")["selected"], [f"{self.paper_key}#figure-3", f"{self.paper_key}#figure-1"])
        self.assertEqual(len(self.figures.listing("all")["papers"][0]["figures"]), 3)
        self.assertTrue(self.figures.listing("method")["papers"][0]["figures"][0]["picked_other"])
        self.assertEqual(self.figures.listing("method", chip="other")["total"], 1)
        self.assertEqual(self.figures.picks_per_paper()[self.paper_key], 2)

    def test_skip_hides_and_clear_comes_back(self) -> None:
        self.figures.skip("all", [self.paper_key], True)
        self.assertEqual(self.figures.listing("all")["total"], 0)
        self.assertEqual(self.figures.listing("all", chip="skipped")["total"], 1)
        before = self.figures.state("all")
        self.figures.replace("all", [], [])
        self.assertEqual(self.figures.listing("all")["total"], 1)
        self.figures.replace("all", before["selected"], before["skipped"])
        self.assertEqual(self.figures.state("all")["skipped"], [self.paper_key])

    def test_export_rows_in_pick_order(self) -> None:
        self.figures.pick("method", [f"{self.paper_key}#figure-2", f"{self.paper_key}#figure-1"], True)
        rows = self.figures.export_rows("method")
        self.assertEqual([r["figure"] for r in rows], [2, 1])
        self.assertIn("Results", rows[0]["caption"])

    def test_helpers(self) -> None:
        self.assertEqual(split_id("10.1/x#y#figure-12"), ("10.1/x#y", 12))
        self.assertIsNone(split_id("nope"))
        self.assertEqual(clean_caption("Fig. 1 The en-\ncoder\nDownloaded from x.org"), "Fig. 1 The encoder")
        from app.core import middleware

        # The grid's images do not use up the API's rate budget.
        self.assertEqual(middleware.budget_for("GET", "/api/figures/image"), middleware.BUDGET_MEDIA)
        self.assertEqual(middleware.budget_for("GET", "/api/figures"), middleware.BUDGET_GENERAL)


class LegacyFiguresTest(ContentTest):
    def test_old_crops_and_picks_come_over(self) -> None:
        self.content.reconcile()
        key = self.key("MindAlign")
        prefix = key.replace("/", "_")
        old = self.root / "old-output"
        (old / "images" / "ALL").mkdir(parents=True)
        (old / "cache" / "papers").mkdir(parents=True)
        (old / "images" / "ALL" / f"{prefix}-figure-1.png").write_bytes(png(800, 600))
        (old / "images" / "ALL" / f"{prefix}-figure-2.png").write_bytes(png(400, 300))
        (old / "images" / f"{prefix}-Figures.png").write_bytes(png(10, 10))
        (old / "cache" / "papers" / f"{prefix}.json").write_text(json.dumps({"yolo": {"meta": {"dpi": 200}, "pages": [
            [{"type": "figure", "bbox": [100, 100, 500, 400], "confidence": 0.9},
             {"type": "figure_caption", "bbox": [100, 410, 500, 450], "ocr": {"rapid": "Figure 1. The model archi-\ntecture"}}],
            [{"type": "figure", "bbox": [100, 100, 500, 400], "confidence": 0.9}],
        ]}}))
        (old / "cache" / "images-state.json").write_text(json.dumps({"selected": [f"{key}#figure-2"], "skipped": []}))
        result = legacy.seed_figures(self.content, old, progress=lambda line: None)
        self.assertEqual((result.done, result.figures), (1, 2))
        manifest = self.content.files.read(key, "figures.json")
        self.assertEqual([(f["n"], f["page"], f["w"]) for f in manifest["figures"]], [(1, 1, 800), (2, 2, 400)])
        self.assertEqual(manifest["figures"][0]["caption"], "Figure 1. The model architecture")
        self.assertTrue((self.content.files.dir(key) / "figures" / "montage.png").is_file())
        self.assertEqual(self.content.files.of(key)[st.FIGURES]["state"], st.DONE)
        # A second run finds it done; reconcile leaves it done.
        self.assertEqual(legacy.seed_figures(self.content, old, progress=lambda line: None).already, 1)
        self.content.reconcile()
        self.assertEqual(self.content.files.of(key)[st.FIGURES]["state"], st.DONE)
        figures = Figures(self.content, self.store, self.root / "none.txt")
        self.assertEqual(legacy.import_figure_picks(figures, old), {"all": 1})
        self.assertEqual(figures.state("all")["selected"], [f"{key}#figure-2"])


class FakeEnricher:
    def __init__(self) -> None:
        self.asked: list[Any] = []

    def github(self, owner: str, repo: str) -> dict[str, Any] | None:
        if repo == "gone":
            return {"status": "not_found"}
        return {"status": "ok", "description": f"{owner}/{repo}", "stars": 3, "methods": ["EEG"]}

    def repair(self, owner: str, repo: str) -> dict[str, Any] | None:
        return {"url": f"https://github.com/{owner}/real", "tier": "prefix", "confidence": 0.9, "original": f"https://github.com/{owner}/{repo}"}

    def osf(self, guid: str) -> dict[str, Any] | None:
        return None

    def record(self, target: str) -> dict[str, Any] | None:
        return {"status": "ok", "title": "A record", "description": "What it is"}

    def step(self, wanted: list[Any]) -> str | None:
        self.asked.append(list(wanted))
        return None


class ScreensTest(ContentTest):
    def test_code_rows_carry_enrichment_and_membership(self) -> None:
        self.content.reconcile()
        while self.content.step("local"):
            pass
        key = self.key("MindAlign")
        self.content.files.write(key, "links.json", {
            "code": [{"url": "https://github.com/lab/tool", "host": "GitHub", "where": "body"},
                     {"url": "https://github.com/lab/gone", "host": "GitHub", "where": "body"}],
            "data": [{"url": "https://openneuro.org/datasets/ds000105", "host": "OpenNeuro", "where": "body", "accession": "ds000105"}],
            "names": [{"name": "HCP (Human Connectome Project)"}],
        })
        self.content.files.settle(key, st.CODE, "x", st.DONE, {"n": 2})
        self.content.files.settle(key, st.DATASETS, "x", st.DONE, {"n": 1, "names": 1})
        figures = Figures(self.content, self.store, self.root / "none.txt")
        figures.pick("all", [f"{key}#figure-1"], True)
        screens = Screens(self.content, figures, FakeEnricher(), self.store)
        rows = screens.code_rows()
        row = next(r for r in rows if r["key"] == key)
        self.assertEqual(row["figs"], 1)
        tool, gone = row["code"]
        self.assertEqual(tool["info"]["methods"], ["EEG"])
        self.assertEqual(gone["repaired"]["url"], "https://github.com/lab/real")
        data = next(r for r in screens.dataset_rows() if r["key"] == key)
        self.assertEqual(data["data"][0]["info"]["title"], "A record")
        self.assertTrue(data["names"][0]["description"])
        self.assertEqual(data["code_n"], 2)
        wanted = screens.wanted()
        self.assertIn(("github", "lab/tool"), wanted)
        self.assertTrue(any(kind == "record" for kind, _ in wanted))

    def test_memberships_name_lists_and_tiers(self) -> None:
        from app.core import db

        self.store.put(db.BUCKET_BOARDS, "t", {"slug": "t", "name": "Tiers", "created_at": "1", "doc": {
            "items": [{"key": "a", "section": "s1"}, {"key": "b", "section": "unranked"}],
            "sections": [{"id": "s1", "label": "A", "color": "#e5484d"}, {"id": "unranked", "label": "Unranked"}],
        }})
        found = memberships(self.store)
        self.assertEqual(found["a"]["tiers"][0]["tier"], "A")
        self.assertEqual(found["b"]["tiers"], [])
        self.assertEqual(found["b"]["lists"][0]["position"], 2)


try:
    from app.tests.route_support import RoutesTestCase
except unittest.SkipTest:  # pragma: no cover -- no httpx2
    RoutesTestCase = None  # type: ignore[assignment,misc]


if RoutesTestCase is not None:

    class Phase5RoutesTest(RoutesTestCase):
        def test_routes_answer(self) -> None:
            headers = {"Authorization": f"Bearer {self.user_key}"}
            for path in ("/api/figures", "/api/figures?view=method&chip=lead", "/api/figures/state", "/api/code", "/api/datasets"):
                answer = self.client.get(path, headers=headers)
                self.assertEqual(answer.status_code, 200, f"{path}: {answer.text}")
            self.assertEqual(self.client.post("/api/figures/pick", json={"view": "all", "ids": ["bad"]}, headers=headers).status_code, 400)
            picked = self.client.post("/api/figures/pick", json={"view": "all", "ids": ["k#figure-1"]}, headers=headers)
            self.assertEqual(picked.json()["selected"], ["k#figure-1"])
            csv = self.client.get("/api/figures/export?view=all&format=csv", headers=headers)
            self.assertEqual(csv.status_code, 200)
            self.assertIn("order,id,key", csv.text)
            self.assertEqual(self.client.get("/api/figures/image?key=nope&n=1", headers=headers).status_code, 404)

        def test_xlsx_export(self) -> None:
            from io import BytesIO

            from openpyxl import load_workbook

            headers = {"Authorization": f"Bearer {self.user_key}"}
            answer = self.client.post("/api/export/xlsx", json={"filename": "code", "sheets": [
                {"name": "Papers", "columns": ["Title", "Year", "Link"], "rows": [["=SUM(1)", 2020, "https://x.org/a"], ["B", None, ""]]},
            ]}, headers=headers)
            self.assertEqual(answer.status_code, 200, answer.text)
            sheet = load_workbook(BytesIO(answer.content)).active
            self.assertEqual(sheet["A2"].value, "=SUM(1)")
            self.assertEqual(sheet["A2"].data_type, "s")
            self.assertEqual(sheet["C2"].hyperlink.target, "https://x.org/a")
            self.assertEqual(self.client.post("/api/export/xlsx", json={"sheets": []}, headers=headers).status_code, 400)


if __name__ == "__main__":
    unittest.main()
