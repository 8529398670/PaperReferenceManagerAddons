"""The library and list routes over HTTP, against a fake Zotero: who may call
them, the userscripts' lookup, and lists changing only through ops."""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from app.boards import legacy, store as boards
from app.tests.route_support import RoutesTestCase
from app.tests.zotero_fixture import sample

MINDALIGN = "10.48550/arXiv.2606.20696"
WOOLRICH = "10.1006/nimg.2001.0931"


class LibraryCase(RoutesTestCase):
    """A route test against the fake Zotero, with the library and lists
    services pointed at it."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.zotero = sample(self.root / "Zotero")
        super().setUp()
        self.set_config(library=replace(self.cfg.library, source="local", zotero_dir=self.root / "Zotero", index_path=self.root / "cache" / "search.db"))
        # build_app made its services from the boot config; point them here.
        from app.library.service import LibraryService
        from app.boards.service import BoardService

        self.app.state.library.close()
        library = LibraryService(self.holder.get())
        self.addCleanup(library.close)
        library.catalogue.sync()
        self.app.state.library = library
        self.app.state.boards = BoardService(self.store, library.catalogue)


class LibraryRoutesTest(LibraryCase):

    def test_signed_in_only(self) -> None:
        for path in ("/api/papers", "/api/paper?key=x", "/api/lists", "/api/version", "/api/lists/schema"):
            self.assertEqual(self.call("GET", path)[0], 401, path)
        self.assertEqual(self.call("POST", "/api/exists", body={"queries": []})[0], 401)

    def test_search_and_one_paper(self) -> None:
        status, body = self.call("GET", "/api/papers?q=prewhitening", key=self.user_key)
        self.assertEqual(status, 200)
        self.assertEqual([p["key"] for p in body["papers"]], [WOOLRICH])
        self.assertEqual(body["status"]["papers"], 3)
        status, body = self.call("GET", "/api/papers?q=temporal+autocorelation&mode=title", key=self.user_key)
        self.assertEqual(body["papers"][0]["key"], WOOLRICH)
        status, body = self.call("GET", "/api/papers?sort=year&dir=asc&limit=1", key=self.user_key)
        self.assertEqual((body["papers"][0]["year"], body["next"], body["total"]), (2001, 1, 3))
        self.assertEqual(self.call("GET", "/api/papers?sort=nope", key=self.user_key)[0], 400)
        status, body = self.call("GET", "/api/paper?key=" + MINDALIGN.upper(), key=self.user_key)
        self.assertEqual((status, body["paper"]["abstract"][:13]), (200, "A transformer"))
        self.assertEqual(self.call("GET", "/api/paper?key=10.1/none", key=self.user_key)[0], 404)

    def test_pdf_is_only_ever_the_papers_own(self) -> None:
        response = self.request("GET", "/api/paper/pdf?key=" + WOOLRICH, key=self.user_key)
        self.assertEqual((response.status_code, response.headers["content-type"]), (200, "application/pdf"))
        self.assertEqual(response.content, b"%PDF-1.4 test")
        # A paper with no PDF, and a path dressed as a key.
        self.assertEqual(self.call("GET", "/api/paper/pdf?key=nodoi-zotero-ITEM0004", key=self.user_key)[0], 404)
        self.assertEqual(self.call("GET", "/api/paper/pdf?key=../../etc/passwd", key=self.user_key)[0], 404)

    def test_exists(self) -> None:
        queries = [{"id": 1, "doi": WOOLRICH.upper()}, {"id": 2, "title": "MindAlign: decoding inner speech from fMRI signals."}, {"id": 3, "doi": "10.9/x"}]
        status, body = self.call("POST", "/api/exists", key=self.user_key, body={"queries": queries})
        self.assertEqual((status, [r["exists"] for r in body["results"]]), (200, [True, True, False]))
        # A browser session needs its CSRF token, like any POST.
        self.assertEqual(self.call("POST", "/api/exists", cookie=self.user_cookie, body={"queries": []})[0], 403)
        token = self.csrf(self.user_cookie)
        self.assertEqual(self.call("POST", "/api/exists", cookie=self.user_cookie, body={"queries": [], "csrf_token": token})[0], 200)
        self.assertEqual(self.call("POST", "/api/exists", key=self.user_key, body={"queries": [{}] * 5001})[0], 400)
        status, body = self.call("GET", "/api/version", key=self.user_key)
        self.assertEqual((status, body["papers"]), (200, 3))

    def test_lists_change_only_through_ops(self) -> None:
        token = self.csrf(self.owner_cookie)
        self.assertEqual(self.call("POST", "/api/lists", cookie=self.owner_cookie, body={"name": "Aim 1"})[0], 403)
        status, body = self.call("POST", "/api/lists", cookie=self.owner_cookie, body={"name": "Aim 1", "csrf_token": token})
        self.assertEqual((status, body["list"]["slug"]), (200, "aim-1"))
        # A second list of the same name gets a slug of its own.
        self.assertEqual(self.call("POST", "/api/lists", key=self.user_key, body={"name": "Aim 1"})[1]["list"]["slug"], "aim-1-2")

        ops = [
            {"op": "add", "paper": WOOLRICH},
            {"op": "add", "paper": "mindalign decoding inner speech from fmri signals", "at": "top"},
            {"op": "tag", "rows": ["#1", "#2"], "add": ["fMRI"]},
            {"op": "set_cell", "row": "#1", "col": "Notes", "value": "key paper"},
        ]
        status, body = self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": ops})
        self.assertEqual((status, body["rev"]), (200, 2))
        doc = body["list"]["doc"]
        self.assertEqual([i["key"] for i in doc["items"]], [MINDALIGN, WOOLRICH])
        self.assertEqual(doc["items"][0]["fields"]["notes"], "key paper")
        self.assertTrue(body["list"]["papers"][WOOLRICH]["has_pdf"])

        # All or nothing: the bad op names itself and nothing lands.
        status, body = self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": [{"op": "move", "row": "#1", "to": 2}, {"op": "move", "row": "#9", "to": 1}]})
        self.assertEqual((status, body["index"]), (400, 1))
        self.assertEqual(self.call("GET", "/api/lists/aim-1", key=self.user_key)[1]["list"]["rev"], 2)
        # A paper the library does not have, by title, is refused with the closest.
        status, body = self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": [{"op": "add", "paper": "a paper about something else"}]})
        self.assertEqual(status, 400)
        # if_rev, and a dry run that changes nothing.
        self.assertEqual(self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"if_rev": 1, "ops": [{"op": "remove", "rows": ["#1"]}]})[0], 409)
        status, body = self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"dry_run": True, "ops": [{"op": "remove", "rows": ["#1"]}]})
        self.assertEqual((status, body["changed"], len(body["list"]["doc"]["items"])), (200, False, 1))
        self.assertEqual(len(self.call("GET", "/api/lists/aim-1", key=self.user_key)[1]["list"]["doc"]["items"]), 2)
        # Every change kept the version it replaced.
        versions = [k for k, v in self.store.all("board_versions") if v["slug"] == "aim-1"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(self.call("POST", "/api/lists/nope/ops", key=self.user_key, body={"ops": [{"op": "remove", "rows": ["#1"]}]})[0], 404)

    def test_a_list_made_from_an_import(self) -> None:
        # What the Import dialog sends for a CSV: the list and its rows in one call.
        ops = [
            {"op": "tag_create", "name": "fMRI", "color": "#336699"},
            {"op": "column_add", "label": "Verdict"},
            {"op": "add", "paper": {"key": WOOLRICH, "title": "Woolrich", "doi": WOOLRICH}, "if_absent": True, "auto_tag": False, "prefill": False, "at": "bottom", "tags": ["fMRI"], "cells": {"Notes": "key paper", "Verdict": "yes"}},
            {"op": "add", "paper": {"key": MINDALIGN, "title": "MindAlign", "doi": MINDALIGN}, "if_absent": True, "auto_tag": False, "prefill": False, "at": "bottom"},
        ]
        status, body = self.call("POST", "/api/lists", key=self.user_key, body={"name": "Imported", "ops": ops})
        self.assertEqual(status, 200, body)
        self.assertEqual((body["list"]["slug"], body["list"]["count"]), ("imported", 2))
        doc = self.call("GET", "/api/lists/imported", key=self.user_key)[1]["list"]["doc"]
        self.assertEqual([i["key"] for i in doc["items"]], [WOOLRICH, MINDALIGN])
        self.assertEqual((doc["items"][0]["tags"], doc["items"][0]["fields"]["notes"], doc["items"][0]["fields"]["verdict"]), (["fMRI"], "key paper", "yes"))
        # The planner learns a new list's columns (Notes is one) from GET /api/lists.
        self.assertIn("Notes", [c["label"] for c in self.call("GET", "/api/lists", key=self.user_key)[1]["new_list"]["columns"]])
        # The import is a change of its own: undoing to rev 1 is the empty list.
        self.assertEqual(self.call("GET", "/api/lists/imported/history/1", key=self.user_key)[1]["version"]["doc"]["items"], [])

        # A bad op makes nothing, and names itself.
        status, body = self.call("POST", "/api/lists", key=self.user_key, body={"name": "Broken", "ops": [ops[3], {"op": "move", "row": "#9", "to": 1}]})
        self.assertEqual((status, body["index"]), (400, 1))
        self.assertEqual(self.call("GET", "/api/lists/broken", key=self.user_key)[0], 404)
        # Not with from.
        self.assertEqual(self.call("POST", "/api/lists", key=self.user_key, body={"name": "Copy", "from": "imported", "ops": ops})[0], 400)

        # Added onto a list from a row on, the new papers keep the file's order.
        third = [k for k in self.call("GET", "/api/papers", key=self.user_key)[1]["papers"] if k["key"] not in (WOOLRICH, MINDALIGN)][0]["key"]
        boards.create_board(self.store, "Two", "test")
        self.call("POST", "/api/lists/two/ops", key=self.user_key, body={"ops": [{"op": "add", "paper": WOOLRICH}, {"op": "add", "paper": third, "at": "bottom"}]})
        status, body = self.call("POST", "/api/lists/two/ops", key=self.user_key, body={"ops": [
            {"op": "add", "paper": {"key": "ref-a", "title": "A"}, "if_absent": True, "at": 2},
            {"op": "add", "paper": {"key": "ref-b", "title": "B"}, "if_absent": True, "at": 3},
        ]})
        self.assertEqual(status, 200, body)
        self.assertEqual([i["key"] for i in body["list"]["doc"]["items"]], [WOOLRICH, "ref-a", "ref-b", third])

    def test_every_list_as_a_zip_and_back(self) -> None:
        import base64
        import io
        import zipfile

        self.call("POST", "/api/lists", key=self.user_key, body={"name": "Aim 1"})
        self.call("POST", "/api/lists", key=self.user_key, body={"name": "Aim/1"})
        self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": [{"op": "add", "paper": WOOLRICH}]})
        response = self.request("GET", "/api/lists/export.zip", "", self.user_key, None, None)
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            # Named after the lists; two that clean to one name are told apart.
            self.assertEqual(names[-2:], ["Aim 1.csv", "Aim 1 (2).csv"])
            self.assertIn(WOOLRICH, archive.read("Aim 1.csv").decode("utf-8"))
        # Read back for the import: the CSVs, in order, as text.
        packed = base64.b64encode(response.content).decode("ascii")
        status, body = self.call("POST", "/api/lists/unzip", key=self.user_key, body={"file": packed})
        self.assertEqual(status, 200)
        self.assertEqual([f["name"] for f in body["files"]], names)
        self.assertTrue(body["files"][-1]["text"].startswith("#,DOI_or_Key"))
        # Not a .zip, or one with no CSVs in it.
        self.assertEqual(self.call("POST", "/api/lists/unzip", key=self.user_key, body={"file": base64.b64encode(b"nope").decode()})[0], 400)
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as archive:
            archive.writestr("readme.txt", "hi")
        self.assertEqual(self.call("POST", "/api/lists/unzip", key=self.user_key, body={"file": base64.b64encode(empty.getvalue()).decode()})[0], 400)
        self.assertEqual(self.call("GET", "/api/lists/export.zip")[0], 401)

    def test_a_locked_list_refuses_changes(self) -> None:
        boards.create_board(self.store, "Frozen", "test")
        self.store.update_value("boards", "frozen", lambda record: record.update(locked=True))
        status, body = self.call("POST", "/api/lists/frozen/ops", key=self.user_key, body={"ops": [{"op": "add", "paper": WOOLRICH}]})
        self.assertEqual(status, 403)

    def test_the_library_is_a_read_only_list(self) -> None:
        # Every paper in Zotero, as a list: locked, built in, not stored.
        status, body = self.call("GET", "/api/lists/library", key=self.user_key)
        self.assertEqual(status, 200)
        view = body["list"]
        self.assertEqual((view["slug"], view["name"], view["locked"], view["builtin"], view["count"]), ("library", "Library", True, True, 3))
        self.assertEqual(len(view["papers"]), 3)
        self.assertIsNone(boards.get_board(self.store, "library"))
        self.assertEqual(self.call("GET", "/api/lists/library/rows", key=self.user_key)[1]["total"], 3)
        # It cannot be changed, and no list can take its slug.
        self.assertEqual(self.call("POST", "/api/lists/library/ops", key=self.user_key, body={"ops": [{"op": "remove", "rows": ["#1"]}]})[0], 403)
        self.assertEqual(self.call("POST", "/api/lists", key=self.user_key, body={"name": "Library"})[1]["list"]["slug"], "library-list")
        # Add: a paper copied from it onto another list, at a position.
        self.call("POST", "/api/lists", key=self.user_key, body={"name": "Aim 1"})
        self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": [{"op": "add", "paper": MINDALIGN}]})
        ops = [{"op": "import_list", "from": "library", "keys": [WOOLRICH], "at": "top", "existing": "skip"}]
        status, body = self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": ops})
        self.assertEqual(status, 200)
        self.assertEqual([i["key"] for i in body["list"]["doc"]["items"]], [WOOLRICH, MINDALIGN])
        # A paper is the same paper everywhere: what a list says about it, the
        # Library shows, its column coming with it.
        ops = [{"op": "column_add", "label": "Verdict"}, {"op": "set_cell", "row": WOOLRICH, "col": "Verdict", "value": "keep"},
               {"op": "set_cell", "row": WOOLRICH, "col": "Notes", "value": "key paper"}, {"op": "tag", "rows": [WOOLRICH], "add": ["fMRI"]}]
        self.assertEqual(self.call("POST", "/api/lists/aim-1/ops", key=self.user_key, body={"ops": ops})[0], 200)
        doc = self.call("GET", "/api/lists/library", key=self.user_key)[1]["list"]["doc"]
        row = next(i for i in doc["items"] if i["key"] == WOOLRICH)
        verdict = next(c["id"] for c in doc["columns"] if c["label"] == "Verdict")
        self.assertEqual((row["fields"]["notes"], row["fields"][verdict], row["tags"]), ("key paper", "keep", ["fMRI"]))
        self.assertEqual(doc["options"]["fold_cols"], [])
        # And Duplicate: a new list of all of it.
        status, body = self.call("POST", "/api/lists", key=self.user_key, body={"name": "Everything", "from": "library"})
        self.assertEqual((status, body["list"]["count"]), (200, 3))

    def test_legacy_import(self) -> None:
        old = self.root / "old"
        (old / "cache" / "sort-lists" / "aim-2").mkdir(parents=True)
        main = {"items": [{"key": WOOLRICH, "title": "T", "tags": ["b", "A"], "mods": ["fMRI"], "fields": {"notes": "n"}}], "vocab": {"tags": [{"name": "A", "color": "#123456"}]}}
        (old / "cache" / "sort.json").write_text(json.dumps(main))
        (old / "cache" / "sort-lists" / "aim-2" / "sort.json").write_text(json.dumps({"items": [{"key": MINDALIGN, "title": "M"}]}))
        (old / "cache" / "sort-lists" / "aim-2" / "meta.json").write_text(json.dumps({"name": "Aim 2"}))
        (old / "cache" / "sort-lists" / "aim-2" / "lock.json").write_text(json.dumps({"locked": True}))
        done = legacy.import_lists(self.store, old)
        self.assertEqual([(d.slug, d.name, d.rows, d.action) for d in done], [("main", "Main", 1, "created"), ("aim-2", "Aim 2", 1, "created")])
        main_list = boards.get_board(self.store, "main")
        self.assertEqual(main_list["doc"]["items"][0]["tags"], ["A", "b", "fMRI"])
        self.assertEqual(main_list["doc"]["vocab"]["tags"][0], {"name": "A", "color": "#123456"})
        self.assertTrue(boards.get_board(self.store, "aim-2")["locked"])
        self.assertEqual([d.action for d in legacy.import_lists(self.store, old)], ["skipped", "skipped"])
        self.assertEqual([d.action for d in legacy.import_lists(self.store, old, replace=True)], ["replaced", "replaced"])
        with self.assertRaises(legacy.LegacyError):
            legacy.import_lists(self.store, self.root / "nowhere")

    def test_mcp_tools(self) -> None:
        boards.create_board(self.store, "Agent", "test")

        def tool(name: str, arguments: dict, key: str) -> dict:
            status, body = self.call("POST", "/mcp", key=key, body={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
            self.assertEqual(status, 200)
            return body["result"]

        found = tool("search_library", {"q": "embeddings"}, self.user_key)["structuredContent"]
        self.assertEqual([p["key"] for p in found["papers"]], [MINDALIGN])
        result = tool("list_ops", {"slug": "agent", "ops": [{"op": "add", "paper": MINDALIGN}]}, self.user_key)
        self.assertEqual(result["structuredContent"]["rev"], 2)
        refused = tool("list_ops", {"slug": "agent", "ops": [{"op": "add", "paper": MINDALIGN}]}, self.user_key)
        self.assertTrue(refused["isError"])
        listing = tool("get_list", {"slug": "agent"}, self.user_key)["structuredContent"]["list"]
        self.assertEqual(listing["count"], 1)
