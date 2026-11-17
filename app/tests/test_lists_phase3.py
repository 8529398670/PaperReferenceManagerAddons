"""Phase 3 of the lists: whole lists (duplicate, rename with a redirect,
delete to the trash and back, purge), rows moving between lists (copy, move,
import from another list or the rest of the library), and one paper's tags
and cells kept the same on every list that shares them."""
from __future__ import annotations

from datetime import timedelta

from app.boards import store as boards
from app.core import db
from app.models import to_iso, utc_now
from app.tests.test_list_ops import NODOI_TITLE
from app.tests.test_lists_routes import MINDALIGN, WOOLRICH, LibraryCase


class Phase3Case(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        boards.create_board(self.store, "Main", "test", slug="main")
        self.ops("main", [
            {"op": "add", "paper": WOOLRICH},
            {"op": "add", "paper": MINDALIGN},
            {"op": "tag", "rows": [WOOLRICH], "add": ["fmri"]},
            {"op": "set_cell", "row": WOOLRICH, "col": "Notes", "value": "classic"},
        ])

    def ops(self, slug: str, batch: list, status: int = 200) -> dict:
        code, body = self.call("POST", f"/api/lists/{slug}/ops", key=self.user_key, body={"ops": batch})
        self.assertEqual(code, status, body)
        return body

    def post(self, path: str, body: dict | None = None, status: int = 200) -> dict:
        code, answer = self.call("POST", path, key=self.user_key, body=body or {})
        self.assertEqual(code, status, answer)
        return answer

    def doc(self, slug: str) -> dict:
        code, body = self.call("GET", f"/api/lists/{slug}", key=self.user_key)
        self.assertEqual(code, 200, body)
        return body["list"]["doc"]

    def row(self, slug: str, key: str) -> dict:
        return next(r for r in self.doc(slug)["items"] if r["key"] == key)

    def keys(self, slug: str) -> list[str]:
        return [r["key"] for r in self.doc(slug)["items"]]


class ListLifecycleTest(Phase3Case):

    def test_new_copy_and_partial_copy(self) -> None:
        empty = self.post("/api/lists", {"name": "Empty"})["list"]
        self.assertEqual((empty["slug"], empty["count"]), ("empty", 0))
        full = self.post("/api/lists", {"name": "Main copy", "from": "main"})["list"]
        self.assertEqual((full["count"], full["copied_from"]), (2, "main"))
        self.assertEqual(self.row("main-copy", WOOLRICH)["fields"]["notes"], "classic")
        part = self.post("/api/lists", {"name": "Only Mindalign", "from": "main", "keys": [MINDALIGN]})["list"]
        doc = self.doc(part["slug"])
        self.assertEqual([r["key"] for r in doc["items"]], [MINDALIGN])
        # Only the tags those rows use come along.
        self.assertEqual(doc["vocab"]["tags"], [])
        self.post("/api/lists", {"name": "x", "keys": [MINDALIGN]}, status=400)
        self.post("/api/lists", {"name": "x", "from": "nope"}, status=404)
        # A name that is a route word gets a slug of its own.
        self.assertEqual(self.post("/api/lists", {"name": "Deleted"})["list"]["slug"], "deleted-list")

    def test_rename_moves_the_slug_and_keeps_the_old_one(self) -> None:
        self.post("/api/lists", {"name": "Aim 1", "from": "main"})
        self.ops("aim-1", [{"op": "options", "sync": "off"}, {"op": "move", "row": MINDALIGN, "to": 1}])
        renamed = self.post("/api/lists/aim-1/rename", {"name": "Aim One"})["list"]
        self.assertEqual(renamed["slug"], "aim-one")
        # The old slug answers the list as it is now, ops and history included.
        code, body = self.call("GET", "/api/lists/aim-1", key=self.user_key)
        self.assertEqual((code, body["list"]["slug"], body["list"]["name"]), (200, "aim-one", "Aim One"))
        self.assertEqual(len(self.call("GET", "/api/lists/aim-1/history", key=self.user_key)[1]["versions"]), 1)
        self.ops("aim-1", [{"op": "move", "row": WOOLRICH, "to": 1}])
        self.assertEqual(self.keys("aim-one"), [WOOLRICH, MINDALIGN])
        # Back again: the old slug is free, so it returns to it.
        self.assertEqual(self.post("/api/lists/aim-one/rename", {"name": "Aim 1"})["list"]["slug"], "aim-1")
        self.assertEqual(self.call("GET", "/api/lists/aim-one", key=self.user_key)[1]["list"]["slug"], "aim-1")
        # A new list at an alias takes the slug over.
        self.post("/api/lists/aim-1/rename", {"name": "Aim Uno"})
        self.assertEqual(self.post("/api/lists", {"name": "Aim 1"})["list"]["slug"], "aim-1")
        self.assertEqual(self.call("GET", "/api/lists/aim-1", key=self.user_key)[1]["list"]["name"], "Aim 1")
        # The main list keeps its slug; a name with nothing in it is refused.
        self.assertEqual(self.post("/api/lists/main/rename", {"name": "Everything"})["list"]["slug"], "main")
        self.post("/api/lists/main/rename", {"name": "!!!"}, status=400)

    def test_delete_to_the_trash_and_back(self) -> None:
        self.post("/api/lists", {"name": "Scratch", "from": "main"})
        self.post("/api/lists/scratch/delete")
        self.assertNotIn("scratch", [row["slug"] for row in self.call("GET", "/api/lists", key=self.user_key)[1]["lists"]])
        self.assertEqual(self.call("GET", "/api/lists/scratch", key=self.user_key)[0], 410)
        self.ops("scratch", [{"op": "remove", "rows": [WOOLRICH]}], status=410)
        trash = self.call("GET", "/api/lists/deleted", key=self.user_key)[1]
        self.assertEqual(([row["slug"] for row in trash["lists"]], trash["days"]), (["scratch"], 30))
        # A new list can't take a deleted one's slug while it can still come back.
        self.assertEqual(self.post("/api/lists", {"name": "Scratch"})["list"]["slug"], "scratch-2")
        self.post("/api/lists/scratch/undelete")
        self.assertEqual(self.keys("scratch"), [WOOLRICH, MINDALIGN])
        self.post("/api/lists/main/delete", status=400)
        self.post("/api/lists/scratch/undelete", status=404)

    def test_purge_after_thirty_days(self) -> None:
        for name in ("Old", "Recent"):
            self.post("/api/lists", {"name": name, "from": "main"})
            self.ops(name.lower(), [{"op": "options", "sync": "off"}, {"op": "remove", "rows": [WOOLRICH]}])
            self.post(f"/api/lists/{name.lower()}/delete")
        self.store.update_value(db.BUCKET_BOARDS, "old", lambda r: r.update(deleted_at=to_iso(utc_now() - timedelta(days=31))))
        self.assertEqual(boards.purge_deleted(self.store), 1)
        self.assertIsNone(self.store.get(db.BUCKET_BOARDS, "old"))
        self.assertFalse([key for key, _ in self.store.all(db.BUCKET_BOARD_VERSIONS) if str(key).startswith("old:")])
        self.assertTrue([key for key, _ in self.store.all(db.BUCKET_BOARD_VERSIONS) if str(key).startswith("recent:")])
        self.assertIsNotNone(self.store.get(db.BUCKET_BOARDS, "recent"))


class RowsBetweenListsTest(Phase3Case):

    def test_copy_and_move_rows(self) -> None:
        self.post("/api/lists", {"name": "Aim"})
        self.ops("aim", [{"op": "add", "paper": NODOI_TITLE}])
        nodoi = self.keys("aim")[0]
        answer = self.ops("aim", [{"op": "import_list", "from": "main", "keys": [WOOLRICH], "at": "top"}])
        result = answer["results"][0]
        self.assertEqual((result["imported"], result["at"]), ([WOOLRICH], 1))
        row = self.row("aim", WOOLRICH)
        self.assertEqual((row["tags"], row["fields"]["notes"]), (["fmri"], "classic"))
        self.assertIn("fmri", [t["name"] for t in self.doc("aim")["vocab"]["tags"]])
        # Copy skips a paper the target has; move lifts it into place with the rest.
        again = self.ops("aim", [{"op": "import_list", "from": "main", "keys": [WOOLRICH, MINDALIGN], "at": "bottom"}])["results"][0]
        self.assertEqual((again["imported"], again["skipped"]), ([MINDALIGN], [WOOLRICH]))
        self.assertEqual(self.keys("aim"), [WOOLRICH, nodoi, MINDALIGN])
        moved = self.ops("aim", [{"op": "import_list", "from": "main", "keys": [WOOLRICH, MINDALIGN], "at": "bottom", "existing": "move"}])["results"][0]
        self.assertEqual(moved["moved"], [WOOLRICH, MINDALIGN])
        self.assertEqual(self.keys("aim"), [nodoi, WOOLRICH, MINDALIGN])

    def test_import_filters_and_remaining_papers(self) -> None:
        self.post("/api/lists", {"name": "Aim"})
        picked = self.ops("aim", [{"op": "import_list", "from": "main", "tags": ["fmri"], "match": "none"}])["results"][0]
        self.assertEqual(picked["imported"], [MINDALIGN])
        none = self.ops("aim", [{"op": "import_list", "from": "main", "year_from": 2030}])["results"][0]
        self.assertEqual(none["imported"], [])
        code, remaining = self.call("GET", "/api/lists/aim/remaining", key=self.user_key)
        self.assertEqual((code, remaining["total"]), (200, 2))
        shelf = self.ops("aim", [{"op": "import_remaining", "range": "1", "shelf": True}])["results"][0]
        self.assertEqual((len(shelf["imported"]), shelf["to"], shelf["remaining"]), (1, "shelf", 1))
        self.assertEqual(len(self.doc("aim")["staging"]), 1)


class SharedEditsTest(Phase3Case):
    """An edit on A shows on B and C; not on a locked D; deleting a column on A
    doesn't delete it on B."""

    def setUp(self) -> None:
        super().setUp()
        for name in ("B", "C", "D"):
            self.post("/api/lists", {"name": name, "from": "main"})
        self.ops("c", [{"op": "options", "sync": "one-way"}])
        self.post("/api/lists/d/lock", {"locked": True})

    def test_an_edit_travels(self) -> None:
        answer = self.ops("main", [
            {"op": "tag", "rows": [MINDALIGN], "add": ["premier"]},
            {"op": "set_cell", "row": WOOLRICH, "col": "Notes", "value": "the classic"},
        ])
        reached = {entry["slug"]: entry for entry in answer["mirrored"]}
        self.assertEqual(reached["b"]["papers"], 2)
        self.assertEqual(reached["c"]["papers"], 2)
        self.assertEqual(reached["d"]["skipped"], "locked")
        for slug in ("b", "c"):
            self.assertEqual(self.row(slug, MINDALIGN)["tags"], ["premier"])
            self.assertEqual(self.row(slug, WOOLRICH)["fields"]["notes"], "the classic")
        self.assertEqual(self.row("d", MINDALIGN)["tags"], [])
        # A one-way list takes the others' edits but keeps its own.
        self.assertEqual(self.ops("c", [{"op": "tag", "rows": [WOOLRICH], "add": ["mine"]}])["mirrored"], [])
        self.assertNotIn("mine", self.row("main", WOOLRICH)["tags"])
        # Off: neither.
        self.ops("b", [{"op": "options", "sync": "off"}])
        self.ops("main", [{"op": "tag", "rows": [WOOLRICH], "remove": ["fmri"]}])
        self.assertEqual(self.row("b", WOOLRICH)["tags"], ["fmri"])
        self.assertEqual(self.row("c", WOOLRICH)["tags"], ["mine"])

    def test_a_column_delete_does_not_travel(self) -> None:
        self.ops("main", [{"op": "column_delete", "col": "Notes"}])
        self.assertIn("notes", [c["id"] for c in self.doc("b")["columns"]])
        self.assertEqual(self.row("b", WOOLRICH)["fields"]["notes"], "classic")

    def test_arrivals_are_filled_from_the_sharing_lists(self) -> None:
        self.post("/api/lists", {"name": "Fresh"})
        answer = self.ops("fresh", [{"op": "add", "paper": WOOLRICH}])
        self.assertEqual(answer["mirrored"][0]["filled"], 1)
        row = self.row("fresh", WOOLRICH)
        self.assertEqual((row["tags"], row["fields"]["notes"]), (["fmri"], "classic"))
        self.assertEqual(answer["rev"], self.call("GET", "/api/lists/fresh", key=self.user_key)[1]["list"]["rev"])

    def test_undo_by_restore_travels_too(self) -> None:
        rev = self.call("GET", "/api/lists/main", key=self.user_key)[1]["list"]["rev"]
        self.ops("main", [{"op": "tag", "rows": [WOOLRICH], "add": ["premier"]}])
        self.assertIn("premier", self.row("b", WOOLRICH)["tags"])
        self.post("/api/lists/main/restore", {"rev": rev})
        self.assertNotIn("premier", self.row("b", WOOLRICH)["tags"])


class TiersTest(Phase3Case):
    """A tier board is a list with sections: rows grouped by tier, ranked
    within it, moved across tiers; the same shelf, CSV and versions."""

    def setUp(self) -> None:
        super().setUp()
        self.post("/api/lists", {"name": "Tiers", "from": "main"})
        self.ops("tiers", [{"op": "options", "sync": "off"}, {"op": "add", "paper": NODOI_TITLE}])
        self.nodoi = self.keys("tiers")[2]
        self.ops("tiers", [{"op": "sections", "on": True}])

    def tier_of(self) -> dict[str, str]:
        return {r["key"]: r["section"] for r in self.doc("tiers")["items"]}

    def test_switching_on_puts_everything_in_unranked(self) -> None:
        doc = self.doc("tiers")
        self.assertEqual([t["label"] for t in doc["sections"]], ["S", "A", "B", "C", "D", "Unranked"])
        self.assertEqual(set(self.tier_of().values()), {"unranked"})
        self.assertEqual(doc["options"]["section_target"], "unranked")
        self.assertTrue(self.call("GET", "/api/lists", key=self.user_key)[1]["lists"][1]["sections"])

    def test_rank_within_and_move_across(self) -> None:
        self.ops("tiers", [{"op": "section_set", "rows": [MINDALIGN], "section": "A"}])
        self.ops("tiers", [{"op": "section_set", "rows": [WOOLRICH], "section": "s"}])
        self.assertEqual(self.keys("tiers"), [WOOLRICH, MINDALIGN, self.nodoi])
        self.ops("tiers", [{"op": "section_set", "rows": [self.nodoi], "section": "A", "rank": 1}])
        self.assertEqual(self.keys("tiers"), [WOOLRICH, self.nodoi, MINDALIGN])
        # A plain move into another tier's stretch snaps back into its own tier.
        self.ops("tiers", [{"op": "move", "row": MINDALIGN, "to": 1}])
        self.assertEqual(self.keys("tiers"), [WOOLRICH, MINDALIGN, self.nodoi])
        self.assertEqual(self.tier_of()[MINDALIGN], "a")
        # Added papers land in the target tier.
        self.ops("tiers", [{"op": "remove", "rows": [WOOLRICH]}, {"op": "section_target", "section": "B"}])
        self.ops("tiers", [{"op": "add", "paper": WOOLRICH, "at": "top"}])
        self.assertEqual(self.tier_of()[WOOLRICH], "b")
        self.assertEqual(self.keys("tiers"), [MINDALIGN, self.nodoi, WOOLRICH])
        self.ops("tiers", [{"op": "section_set", "rows": [WOOLRICH], "section": "Nope"}], status=400)

    def test_section_ops(self) -> None:
        self.ops("tiers", [{"op": "section_set", "rows": [MINDALIGN, WOOLRICH], "section": "A"}])
        added = self.ops("tiers", [{"op": "section_add", "label": "Premier", "color": "#112233", "at": 1}])["results"][0]
        self.assertEqual((added["section"], added["at"]), ("premier", 1))
        self.ops("tiers", [
            {"op": "section_rename", "section": "premier", "label": "Top"},
            {"op": "section_desc", "section": "Top", "desc": "the best"},
            {"op": "section_color", "section": "Top", "color": "#445566"},
            {"op": "section_move", "section": "Top", "to": "down"},
            {"op": "section_target", "section": "a"},
        ])
        doc = self.doc("tiers")
        top = doc["sections"][1]
        self.assertEqual((top["label"], top["desc"], top["color"]), ("Top", "the best", "#445566"))
        # Unranked stays last, and can be neither moved nor deleted.
        self.ops("tiers", [{"op": "section_move", "section": "Top", "to": 99}])
        self.assertEqual([t["id"] for t in self.doc("tiers")["sections"]][-2:], ["premier", "unranked"])
        self.ops("tiers", [{"op": "section_move", "section": "Unranked", "to": 1}], status=400)
        self.ops("tiers", [{"op": "section_delete", "section": "unranked"}], status=400)
        self.ops("tiers", [{"op": "section_add", "label": "top"}], status=400)
        # Deleting a tier: its rows to the top of Unranked, the target back to Unranked.
        moved = self.ops("tiers", [{"op": "section_delete", "section": "A"}])["results"][0]
        self.assertEqual(moved["moved"], 2)
        doc = self.doc("tiers")
        self.assertEqual(doc["options"]["section_target"], "unranked")
        self.assertEqual([r["key"] for r in doc["items"]], [MINDALIGN, WOOLRICH, self.nodoi])
        self.assertNotIn("a", [t["id"] for t in doc["sections"]])

    def test_csv_and_rows_say_the_tier(self) -> None:
        self.ops("tiers", [{"op": "section_set", "rows": [MINDALIGN], "section": "A"}])
        text = self.request("GET", "/api/lists/tiers/export.csv", key=self.user_key).text
        head, first = text.lstrip("﻿").splitlines()[:2]
        self.assertTrue(head.startswith("#,DOI_or_Key,Cite,Title,Year,Tier,Tags"))
        self.assertIn(",A,", first)
        rows = self.call("GET", "/api/lists/tiers/rows", key=self.user_key)[1]["rows"]
        self.assertEqual(rows[0]["tier"], "A")

    def test_switching_off_keeps_the_order(self) -> None:
        self.ops("tiers", [{"op": "section_set", "rows": [self.nodoi], "section": "S"}])
        self.ops("tiers", [{"op": "sections", "on": False}])
        doc = self.doc("tiers")
        self.assertEqual((doc["sections"], doc["items"][0]["key"]), ([], self.nodoi))
        self.assertNotIn("section", doc["items"][0])

    def test_pull_tiers(self) -> None:
        self.ops("tiers", [{"op": "section_set", "rows": [self.nodoi], "section": "S"}])
        self.post("/api/lists", {"name": "Other"})
        result = self.ops("other", [{"op": "pull_tiers"}])["results"][0]
        self.assertEqual(len(result["pulled"]), 3)
        tier = {r["key"]: r["fields"].get("tier") for r in self.doc("other")["items"]}
        self.assertEqual((tier[self.nodoi], tier[WOOLRICH]), ("S", "Unranked"))
        self.ops("other", [{"op": "pull_tiers", "from": "main"}], status=400)


class LegacyTiersTest(Phase3Case):
    def test_tiers_json_becomes_a_tier_board(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        from app.boards import legacy

        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "cache"
            cache.mkdir()
            (cache / "tiers.json").write_text(json.dumps({
                "columns": [{"id": "notes", "label": "Notes"}],
                "vocab": {"tags": [{"name": "premier", "color": "#e5484d"}], "mods": [{"name": "fMRI", "color": "#cfe0fb"}]},
                "tiers": [
                    {"id": "s", "label": "S", "color": "#ff5c5c", "desc": "best", "items": [{"key": WOOLRICH, "title": "W", "mods": ["fMRI"], "tags": ["premier"]}]},
                    {"id": "unranked", "label": "Unranked", "items": [{"key": MINDALIGN, "title": "M"}]},
                ],
            }))
            (cache / "tiers-lock.json").write_text(json.dumps({"locked": True}))
            done = legacy.import_lists(self.store, Path(folder))
        self.assertEqual([(d.slug, d.action, d.rows) for d in done], [("tiers", "created", 2)])
        record = boards.get_board(self.store, "tiers")
        doc = record["doc"]
        self.assertTrue(record["locked"])
        self.assertEqual([t["label"] for t in doc["sections"]], ["S", "Unranked"])
        self.assertEqual(doc["sections"][0]["desc"], "best")
        self.assertEqual([(r["key"], r["section"], r["tags"]) for r in doc["items"]], [(WOOLRICH, "s", ["fMRI", "premier"]), (MINDALIGN, "unranked", [])])


class SheetTest(Phase3Case):
    """Reading a Google Sheet: only docs.google.com, by the sheet's ID, and the
    links behind its cells out of the zipped HTML export."""

    LINK = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit#gid=7"

    def test_only_the_sheet_id_is_used(self) -> None:
        from app.boards import gsheet

        self.assertEqual(gsheet.export_url(self.LINK), "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/export?format=csv&gid=7")
        self.assertEqual(gsheet.zip_url("https://evil.example/?u=" + self.LINK), "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/export?format=zip")
        with self.assertRaises(ValueError):
            gsheet.export_url("https://evil.example/spreadsheets/d/x")
        self.post("/api/sheet/csv", {"url": "https://evil.example/x"}, status=400)

    def test_links_behind_the_cells(self) -> None:
        import io
        import zipfile

        from app.boards import gsheet

        rows = gsheet.rows("Title,Datasets\r\nA paper,\"UK Biobank\nzenodo 1\"\r\n,\r\nOther,plain\r\n")
        self.assertEqual(rows, [["Title", "Datasets"], ["A paper", "UK Biobank\nzenodo 1"], ["Other", "plain"]])
        html = (
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>Title</td><td>Datasets</td></tr>"
            "<tr><td>A paper</td><td><a href=\"https://www.google.com/url?q=https://ukbiobank.ac.uk&amp;sa=D\">UK Biobank</a><br>"
            "<a href=\"https://zenodo.org/1\">zenodo 1</a></td></tr>"
            "<tr><td>Other</td><td>plain</td></tr></table>"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Sheet1.html", html)
            archive.writestr("Other tab.html", "<table><tr><td>nothing</td></tr></table>")
        links = gsheet.links_from_zip(buffer.getvalue(), rows)
        self.assertIsNone(links[0])
        self.assertEqual(links[1], {1: [["UK Biobank", "https://ukbiobank.ac.uk"], ["\n", None], ["zenodo 1", "https://zenodo.org/1"]]})
        self.assertIsNone(links[2])
        with self.assertRaises(ValueError):
            gsheet.links_from_zip(b"not a zip", rows)

    def test_route_answers_rows_and_links(self) -> None:
        from unittest import mock

        from app.boards import gsheet

        with mock.patch.object(gsheet, "fetch_csv", return_value="Title\nA\n"), mock.patch.object(gsheet, "fetch_links", side_effect=ValueError("no zip")):
            body = self.post("/api/sheet/csv", {"url": self.LINK})
        self.assertEqual((body["rows"], body["links"], body["links_error"]), ([["Title"], ["A"]], None, "no zip"))
        with mock.patch.object(gsheet, "fetch_csv", side_effect=ValueError("share it")):
            self.assertEqual(self.post("/api/sheet/csv", {"url": self.LINK}, status=400)["error"], "share it")

    def test_the_sheet_link_is_remembered(self) -> None:
        self.ops("main", [{"op": "options", "sheet_url": self.LINK}])
        self.assertEqual(self.doc("main")["options"]["sheet_url"], self.LINK)
        self.ops("main", [{"op": "options", "sheet_url": "https://evil.example/x"}], status=400)
