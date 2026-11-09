"""Phase 2 of the lists: every op the board engine takes, run against a real
list through POST /ops, and the read, history, lock, citation, reference and
recently-added routes."""
from __future__ import annotations

import base64
import io
import zipfile
from datetime import datetime, timezone

from app.boards import store as boards
from app.tests.test_lists_routes import MINDALIGN, WOOLRICH, LibraryCase

NODOI_TITLE = "A paper with no DOI about Ørsted and naïve café models"


class ListOpsTest(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        boards.create_board(self.store, "Ops", "test")
        self.ops([
            {"op": "add", "paper": WOOLRICH},
            {"op": "add", "paper": MINDALIGN},
            {"op": "add", "paper": NODOI_TITLE},
        ])

    def ops(self, batch: list, status: int = 200, slug: str = "ops", **extra) -> dict:
        code, body = self.call("POST", f"/api/lists/{slug}/ops", key=self.user_key, body={"ops": batch, **extra})
        self.assertEqual(code, status, body)
        return body

    def doc(self, slug: str = "ops") -> dict:
        return self.call("GET", f"/api/lists/{slug}", key=self.user_key)[1]["list"]["doc"]

    def order(self) -> list[str]:
        return [row["key"] for row in self.doc()["items"]]

    def label_of(self, cid: str) -> str:
        return next(c["label"] for c in self.doc()["columns"] if c["id"] == cid)

    # -- sort, update, options ------------------------------------------------------

    def test_sort(self) -> None:
        nodoi = self.order()[2]
        self.ops([{"op": "sort", "by": "year"}])
        self.assertEqual(self.order(), [MINDALIGN, nodoi, WOOLRICH])
        self.ops([{"op": "sort", "by": "year_asc"}])
        self.assertEqual(self.order(), [WOOLRICH, nodoi, MINDALIGN])  # 2020 < 2026; none sorts as 9999
        self.ops([{"op": "update", "row": nodoi, "year": ""}])
        self.ops([{"op": "sort", "by": "year_asc"}])
        self.assertEqual(self.order(), [WOOLRICH, MINDALIGN, nodoi])
        self.ops([{"op": "sort", "by": "title"}])
        self.assertEqual(self.order(), [nodoi, MINDALIGN, WOOLRICH])
        # tags: same tag set together, in order of first appearance; untagged last.
        self.ops([{"op": "tag", "rows": [WOOLRICH], "add": ["b"]}, {"op": "tag", "rows": [nodoi], "add": ["b"]}])
        self.ops([{"op": "sort", "by": "tags"}])
        self.assertEqual(self.order(), [nodoi, WOOLRICH, MINDALIGN])
        # cites needs OpenAlex (phase 4): every row counts 0, so the order holds.
        self.ops([{"op": "sort", "by": "cites"}])
        self.assertEqual(self.order(), [nodoi, WOOLRICH, MINDALIGN])
        self.ops([{"op": "sort", "by": "added"}])
        self.ops([{"op": "sort", "by": "nope"}], status=400)

    def test_update(self) -> None:
        body = self.ops([{"op": "update", "row": "#1", "title": "New", "year": "1999", "journal": "J"}])
        row = self.doc()["items"][0]
        self.assertEqual((row["title"], row["year"], row["journal"]), ("New", 1999, "J"))
        self.assertEqual(body["results"][0]["updated"], ["title", "year", "journal"])
        self.ops([{"op": "update", "row": "#1", "year": None}])
        self.assertIsNone(self.doc()["items"][0]["year"])
        self.ops([{"op": "update", "row": "#1", "year": "soon"}], status=400)
        self.ops([{"op": "update", "row": "#1"}], status=400)

    def test_options(self) -> None:
        self.ops([{"op": "options", "auto_move": True, "add_where": "top", "cite_style": "the-journal-of-neuroscience", "sync": "one-way"}])
        options = self.doc()["options"]
        self.assertEqual((options["auto_move"], options["add_where"], options["cite_style"], options["sync"]), (True, "top", "the-journal-of-neuroscience", "one-way"))
        self.ops([{"op": "options", "add_where": "middle"}], status=400)
        self.ops([{"op": "options", "sync": "sideways"}], status=400)
        # Only a style this server can render.
        self.ops([{"op": "options", "cite_style": "../../etc/passwd"}], status=400)

    def test_auto_move_and_add_where(self) -> None:
        self.ops([{"op": "options", "auto_move": True}, {"op": "tag", "rows": ["#1"], "add": ["x"]}])
        # Tagging #3 like #1 slides it to just after #1.
        third = self.order()[2]
        self.ops([{"op": "tag", "row": "#3", "add": ["x"]}])
        self.assertEqual(self.order()[1], third)

    # -- columns -------------------------------------------------------------

    def test_columns(self) -> None:
        body = self.ops([{"op": "column_add", "label": "Method"}])
        cid = body["results"][0]["col"]["id"] if "col" in body["results"][0] else next(c["id"] for c in self.doc()["columns"] if c["label"] == "Method")
        self.ops([{"op": "column_add", "label": "method"}], status=400)  # unique case-insensitively
        for reserved in ("#", "Title", "Tags", "DOI", "Cite", "Modality", "Year", "Authors"):
            self.ops([{"op": "column_add", "label": reserved}], status=400)
        self.ops([{"op": "column_rename", "col": "Method", "label": "Decoder"}])
        self.assertEqual(self.label_of(cid), "Decoder")
        self.ops([{"op": "column_move", "col": "Decoder", "to": 1}])
        self.assertEqual(self.doc()["columns"][0]["id"], cid)
        self.ops([{"op": "column_fold", "col": "Decoder", "folded": True}])
        self.assertIn(cid, self.doc()["options"]["fold_cols"])
        self.ops([{"op": "set_cell", "row": "#1", "col": "Decoder", "value": "CNN"}])
        self.ops([{"op": "column_delete", "col": "Decoder"}])
        doc = self.doc()
        self.assertNotIn(cid, [c["id"] for c in doc["columns"]])
        self.assertIn(cid, doc["options"]["dropped_cols"])
        # At most 16.
        free = 16 - len(doc["columns"])
        self.ops([{"op": "column_add", "label": f"c{n}"} for n in range(free)])
        self.ops([{"op": "column_add", "label": "one too many"}], status=400)
        # Never the last one.
        cols = self.doc()["columns"]
        self.ops([{"op": "column_delete", "col": c["label"]} for c in cols[:-1]])
        self.ops([{"op": "column_delete", "col": cols[-1]["label"]}], status=400)

    def test_set_cell_modes(self) -> None:
        def cell() -> str:
            return self.doc()["items"][0]["fields"].get("notes", "")

        self.ops([{"op": "set_cell", "row": "#1", "col": "Notes", "value": "a"}])
        self.ops([{"op": "set_cell", "row": "#1", "col": "Notes", "value": "b", "mode": "append"}])
        self.assertEqual(cell(), "a\nb")
        self.ops([{"op": "set_cell", "row": "#1", "col": "Notes", "value": "z", "mode": "prepend"}])
        self.assertEqual(cell(), "z\na\nb")
        self.ops([{"op": "set_cell", "row": "#1", "col": "Notes", "value": "no", "mode": "fill"}])
        self.assertEqual(cell(), "z\na\nb")

    # -- tags --------------------------------------------------------------------

    def test_tags(self) -> None:
        self.ops([
            {"op": "tag", "rows": ["#1", "#2"], "add": ["fMRI"]},
            {"op": "tag", "row": "#3", "add": ["EEG"]},
            {"op": "tag_create", "name": "MEG", "color": "#cfe0fb"},
        ])
        self.ops([{"op": "tag_order", "names": ["MEG", "EEG"]}])
        self.assertEqual([t["name"] for t in self.doc()["vocab"]["tags"]], ["MEG", "EEG", "fMRI"])
        self.ops([{"op": "tag_color", "name": "fMRI", "color": "#ffffff"}, {"op": "tag_color", "name": "MEG", "color": ""}])
        colors = {t["name"]: t["color"] for t in self.doc()["vocab"]["tags"]}
        self.assertEqual((colors["fMRI"], colors["MEG"]), ("#ffffff", ""))
        self.ops([{"op": "tag_color", "name": "fMRI", "color": "red"}], status=400)
        # Renaming onto an existing tag merges the two.
        body = self.ops([{"op": "tag_rename", "from": "EEG", "to": "fMRI"}])
        self.assertTrue(body["results"][0].get("merged"))
        self.assertEqual([row["tags"] for row in self.doc()["items"]], [["fMRI"]] * 3)
        self.ops([{"op": "tag_delete", "name": "fMRI"}])
        doc = self.doc()
        self.assertEqual([row["tags"] for row in doc["items"]], [[]] * 3)
        self.assertNotIn("fMRI", [t["name"] for t in doc["vocab"]["tags"]])
        # auto_tag needs modality stamps (phase 4): a no-op until then.
        self.ops([{"op": "auto_tag"}])
        self.assertEqual([row["tags"] for row in self.doc()["items"]], [[]] * 3)

    # -- the read routes -----------------------------------------------------------

    def test_rows_and_csv(self) -> None:
        self.ops([{"op": "tag", "rows": ["#1"], "add": ["fMRI"]}, {"op": "set_cell", "row": "#2", "col": "Notes", "value": "line one\nline two"}])
        status, body = self.call("GET", "/api/lists/ops/rows?tags=fmri&match=none", key=self.user_key)
        self.assertEqual((status, [r["pos"] for r in body["rows"]]), (200, [2, 3]))
        self.assertEqual(body["rows"][0]["cells"]["Notes"], "line one\nline two")
        self.assertEqual(self.call("GET", "/api/lists/ops/rows?q=prewhitening", key=self.user_key)[1]["total"], 0)  # titles, not full text
        self.assertEqual(self.call("GET", "/api/lists/ops/rows?q=mindalign", key=self.user_key)[1]["total"], 1)
        self.assertEqual(self.call("GET", "/api/lists/ops/rows?match=some", key=self.user_key)[0], 400)
        self.assertEqual(self.call("GET", "/api/lists/ops/rows?limit=501", key=self.user_key)[0], 400)
        self.assertEqual(self.call("GET", "/api/lists/nope/rows", key=self.user_key)[0], 404)

        response = self.request("GET", "/api/lists/ops/export.csv", key=self.user_key)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿#,DOI_or_Key,Cite,Title,Year,Tags,Notes,"))
        lines = text.splitlines()
        self.assertIn("(Woolrich and Ripley, 2001)", lines[1])
        self.assertIn("line one; line two", lines[2])
        # Only the filtered rows, keeping their real numbers.
        lines = self.request("GET", "/api/lists/ops/export.csv?keys=" + MINDALIGN, key=self.user_key).content.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("2," + MINDALIGN))

    # -- history, restore, lock ---------------------------------------------------

    def test_history_and_restore(self) -> None:
        self.ops([{"op": "remove", "rows": ["#1"]}])
        status, body = self.call("GET", "/api/lists/ops/history", key=self.user_key)
        self.assertEqual(status, 200)
        self.assertEqual([(v["rev"], v["rows"]) for v in body["versions"]], [(2, 3), (1, 0)])
        status, body = self.call("GET", "/api/lists/ops/history/2", key=self.user_key)
        self.assertEqual(len(body["version"]["doc"]["items"]), 3)
        self.assertEqual(self.call("GET", "/api/lists/ops/history/9", key=self.user_key)[0], 404)

        token = self.csrf(self.user_cookie)
        self.assertEqual(self.call("POST", "/api/lists/ops/restore", cookie=self.user_cookie, body={"rev": 2})[0], 403)
        status, body = self.call("POST", "/api/lists/ops/restore", cookie=self.user_cookie, body={"rev": 2, "csrf_token": token})
        self.assertEqual((status, body["rev"], body["list"]["count"]), (200, 4, 3))
        # The restore is itself a version, so it can be undone the same way.
        status, body = self.call("POST", "/api/lists/ops/restore", key=self.user_key, body={"rev": 3})
        self.assertEqual((body["rev"], body["list"]["count"]), (5, 2))
        self.assertEqual(self.call("POST", "/api/lists/ops/restore", key=self.user_key, body={"rev": "3"})[0], 400)

    def test_lock(self) -> None:
        status, body = self.call("POST", "/api/lists/ops/lock", key=self.user_key, body={"locked": True})
        self.assertEqual((status, body["list"]["locked"]), (200, True))
        self.ops([{"op": "remove", "rows": ["#1"]}], status=403)
        self.ops([{"op": "remove", "rows": ["#1"]}], dry_run=True)  # a dry run still works
        self.assertEqual(self.call("POST", "/api/lists/ops/restore", key=self.user_key, body={"rev": 1})[0], 403)
        self.assertEqual(self.call("POST", "/api/lists/ops/lock", key=self.user_key, body={"locked": "no"})[0], 400)
        self.call("POST", "/api/lists/ops/lock", key=self.user_key, body={"locked": False})
        self.ops([{"op": "remove", "rows": ["#1"]}])
        self.assertEqual(self.call("POST", "/api/lists/nope/lock", key=self.user_key, body={"locked": True})[0], 404)

    # -- citations -----------------------------------------------------------------

    def test_cite(self) -> None:
        status, body = self.call("POST", "/api/cite", key=self.user_key, body={"keys": [WOOLRICH, MINDALIGN, "nodoi-zotero-ITEM0004", "10.1/none"]})
        self.assertEqual((status, body["style"]), (200, "the-journal-of-neuroscience"))
        cites = body["cites"]
        self.assertEqual(cites[WOOLRICH]["intext"], "(Woolrich and Ripley, 2001)")
        self.assertTrue(cites[WOOLRICH]["full"].startswith("Woolrich M, Ripley B (2001) Temporal"))
        self.assertEqual(cites[MINDALIGN]["intext"], "(Liu, 2026)")
        # No author and no editor: no citation, never "(Anon, n.d.)".
        self.assertEqual(cites["nodoi-zotero-ITEM0004"], {"intext": "", "full": ""})
        self.assertEqual(cites["10.1/none"]["intext"], "")
        # A style that is not one of ours falls back to the default.
        body = self.call("POST", "/api/cite", key=self.user_key, body={"keys": [WOOLRICH], "style": "../x"})[1]
        self.assertEqual(body["style"], "the-journal-of-neuroscience")
        styles = self.call("GET", "/api/cite/styles", key=self.user_key)[1]
        self.assertEqual([(s["id"], s["ok"]) for s in styles["styles"]], [("the-journal-of-neuroscience", True)])

    # -- reference lists and the shelf ---------------------------------------------

    REFS = (
        "1. Woolrich MW, Ripley BD. Temporal autocorrelation in univariate linear modeling of FMRI data. "
        "NeuroImage. 2001;14(6):1370-86. doi:10.1006/nimg.2001.0931\n"
        "2. Liu M. MindAlign: decoding inner speech from fMRI signals. arXiv. 2026.\n"
        "3. Smith J, Jones K. A study nobody has heard of. J Unknown. 2019;3:1-2.\n"
    )

    def test_refs_parse(self) -> None:
        status, body = self.call("POST", "/api/refs/parse", key=self.user_key, body={"text": self.REFS})
        self.assertEqual(status, 200)
        refs = body["refs"]
        self.assertEqual([(r["key"], r["matched"], r["in_library"]) for r in refs], [
            (WOOLRICH, "doi", True),
            (MINDALIGN, "title", True),
            ("ref-a-study-nobody-has-heard-of", "", False),
        ])
        # A .docx is read server-side; a PDF is refused, saying what to do.
        docx = io.BytesIO()
        with zipfile.ZipFile(docx, "w") as z:
            paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in self.REFS.splitlines())
            z.writestr("word/document.xml", f'<w:document xmlns:w="w"><w:body>{paragraphs}</w:body></w:document>')
        status, body = self.call("POST", "/api/refs/parse", key=self.user_key, body={"file": base64.b64encode(docx.getvalue()).decode()})
        self.assertEqual((status, len(body["refs"])), (200, 3))
        status, body = self.call("POST", "/api/refs/parse", key=self.user_key, body={"file": base64.b64encode(b"%PDF-1.4 x").decode()})
        self.assertEqual(status, 400)
        self.assertIn("PDF", body["error"])
        self.assertEqual(self.call("POST", "/api/refs/parse", key=self.user_key, body={})[0], 400)

    def test_stage_then_add(self) -> None:
        boards.create_board(self.store, "Shelf", "test")
        self.ops([{"op": "add", "paper": WOOLRICH}], slug="shelf")
        body = self.ops([{"op": "stage", "text": self.REFS}], slug="shelf")
        result = body["results"][0]
        # Only what's new is taken: Woolrich is already on the list.
        self.assertEqual((result["read"], result["staged"], result["on_list"]), (3, 2, 1))
        # Pasting the same list again brings nothing new.
        result = self.ops([{"op": "stage", "text": self.REFS}], slug="shelf")["results"][0]
        self.assertEqual((result["staged"], result["on_shelf"]), (0, 2))
        doc = self.doc("shelf")
        self.assertEqual([r["key"] for r in doc["staging"]], [MINDALIGN, "ref-a-study-nobody-has-heard-of"])
        self.ops([{"op": "stage_drop", "rows": ["ref-a-study-nobody-has-heard-of"]}], slug="shelf")
        self.ops([{"op": "stage_add", "all": True, "at": "top"}], slug="shelf")
        doc = self.doc("shelf")
        self.assertEqual(([r["key"] for r in doc["items"]], doc["staging"]), ([MINDALIGN, WOOLRICH], []))

    # -- recently added -------------------------------------------------------------

    def test_recently_added(self) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.zotero.add("Saved a moment ago", doi="10.5555/fresh", added=now)
        self.zotero.add("Saved a moment ago too", doi="10.5555/fresh2", added=now)
        self.app.state.library.catalogue.sync(force=True)
        self.ops([{"op": "add", "paper": "10.5555/fresh2"}])
        status, body = self.call("GET", "/api/papers/recent?days=7&not_on=ops", key=self.user_key)
        self.assertEqual((status, [p["key"] for p in body["papers"]]), (200, ["10.5555/fresh"]))
        self.assertEqual(self.call("GET", "/api/papers/recent?days=7", key=self.user_key)[1]["total"], 2)
        self.assertEqual(self.call("GET", "/api/papers/recent?days=0", key=self.user_key)[0], 400)
        self.assertEqual(self.call("GET", "/api/papers/recent?not_on=nope", key=self.user_key)[0], 404)

    # -- the schema and MCP ---------------------------------------------------------

    def test_schema_and_mcp_history(self) -> None:
        schema = self.call("GET", "/api/lists/schema", key=self.user_key)[1]
        for name in ("sort", "update", "options", "column_add", "column_rename", "column_delete", "column_move", "column_fold",
                     "tag_delete", "tag_rename", "tag_order", "auto_tag", "stage", "stage_add", "stage_drop", "set_cell"):
            self.assertIn(name, schema["ops"])
            self.assertTrue(schema["ops"][name]["does"])
        self.assertIn("GET /api/lists/<slug>/history", schema["endpoints"])
        self.assertNotIn("/api/sort", str(schema["endpoints"]))

        self.ops([{"op": "remove", "rows": ["#1"]}])
        status, body = self.call("POST", "/mcp", key=self.user_key, body={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_history", "arguments": {"slug": "ops"}}})
        self.assertEqual([v["rev"] for v in body["result"]["structuredContent"]["versions"]], [2, 1])
