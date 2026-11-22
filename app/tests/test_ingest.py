"""Adding papers (app/library/ingest.py, app/routes/ingest.py): what the
Zotero plugin sends goes to the caller's own library, else the server's for
admins only, parents first, files in pieces, and never names the library's
address or key."""
from __future__ import annotations

import json
import urllib.parse
from dataclasses import replace
from typing import Any

from app.library import ingest
from app.library import remote as rl
from app.library.service import LibraryService
from app.models import api_keys, users
from app.tests.test_remote_library import KEY, FakeServer, sample
from app.tests.test_user_library import URL, UserLibraryCase

PDF_BYTES = b"%PDF-1.4 tiny"


class WritableServer(FakeServer):
    """The fake ZoteroWebDAV, taking the writes the plugin's papers make."""

    def __init__(self) -> None:
        super().__init__()
        self.posts: list[tuple[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.post_status: list[int] = []

    def __call__(self, request: Any, timeout: int) -> tuple[int, dict[str, str], bytes]:
        if request.get_method() == "GET":
            return super().__call__(request, timeout)
        assert request.get_header("Authorization") == "Bearer " + KEY
        self.requests.append(request.full_url)
        if self.post_status:
            status = self.post_status.pop(0)
            if status != 200:
                return status, {}, b""
        parts = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path in (ingest.ITEMS_PATH, ingest.COLLECTIONS_PATH):
            body = json.loads(request.data)
            self.posts.append((parts.path, body))
            field, kind = ("item_key", "item") if parts.path == ingest.ITEMS_PATH else ("collection_key", "collection")
            results = []
            for index, entry in enumerate(body["items"]):
                if entry["data"].get("title") == "refuse me":
                    results.append({"index": index, "ok": False, "status": 400, "error": "data must be a JSON object"})
                    continue
                self.add({"kind": kind, "key": entry[field], "updated_at": "2026-11-22T10:00:00Z", "data": entry["data"]})
                results.append({"index": index, "ok": True, "reply": {"key": entry[field], "rev": 1, "changed": True}})
            return 200, {}, json.dumps({"done": len(results), "failed": 0, "results": results}).encode()
        if parts.path == ingest.UPLOAD_PATH:
            key = query["key"]
            if not any(r["key"] == key for r in self.records):
                return 404, {}, b""
            self.posts.append((parts.path, dict(query)))
            held = self.files.get(key, b"") if int(query["offset"]) else b""
            held += request.data
            self.files[key] = held
            done = len(held) == int(query["size"])
            if done:
                self.attachments.append({"key": key, "zip": True, "prop": True, "md5": "abc", "mtime": 1})
            return 200, {}, json.dumps({"received": len(held), "done": done}).encode()
        return 404, {}, b""


def paper(key: str = "NEWPAPR1", **data: Any) -> dict[str, Any]:
    return {"key": key, "data": {"key": key, "version": 12, "itemType": "journalArticle", "title": "A new paper",
                                 "DOI": "10.1000/new.1", "collections": ["COLLNEW1"], **data}}


def pdf(key: str = "NEWATT01", parent: str = "NEWPAPR1") -> dict[str, Any]:
    return {"key": key, "data": {"key": key, "itemType": "attachment", "parentItem": parent, "linkMode": "imported_url",
                                 "contentType": "application/pdf", "filename": "new.pdf"}}


class IngestCase(UserLibraryCase):
    def setUp(self) -> None:
        super().setUp()
        self.remote = WritableServer()
        sample(self.remote)
        # A key of the plain user's own, and one for an admin.
        self.mine, _ = api_keys.issue_api_key(self.store, self.user.id, "plugin", users.ROLE_USER, 3600)

    def send(self, key: str, items: list | None = None, collections: list | None = None) -> tuple[int, Any]:
        return self.call("POST", "/api/ingest/items", key=key, body={"items": items or [], "collections": collections or []})

    def piece(self, key: str, data: bytes, size: int, offset: int = 0, attach: str = "NEWATT01") -> Any:
        query = urllib.parse.urlencode({"key": attach, "filename": "new.pdf", "size": size, "offset": offset, "mtime": 5})
        return self.client.post("/api/ingest/file?" + query, content=data,
                                headers={"authorization": "Bearer " + key, "content-type": "application/octet-stream"})

    def use_remote_server_library(self) -> None:
        """The server's library on the fake ZoteroWebDAV (library.source remote)."""
        self.set_config(library=replace(self.holder.get().library, source="remote"))
        library = rl.RemoteLibrary(rl.Remote("https://server.example.org", KEY, "", opener=self.remote), self.root / "server-remote")
        service = LibraryService(self.holder.get(), library=library, index_path=self.root / "server-remote" / "search.db")
        self.addCleanup(service.close)
        self.libraries.server = service


class TargetTest(IngestCase):
    def test_own_library_first(self) -> None:
        self.assertEqual(self.connect(self.user_cookie)[0], 200)
        status, body = self.call("GET", "/api/ingest/target", key=self.mine)
        self.assertEqual((status, body["writable"], body["kind"]), (200, True, "own"), body)
        self.assertEqual(body["chunk_bytes"], ingest.UPLOAD_PIECE)
        self.assertNotIn("example", json.dumps(body))

    def test_plain_user_without_own_library_is_refused(self) -> None:
        self.use_remote_server_library()
        status, body = self.call("GET", "/api/ingest/target", key=self.mine)
        self.assertEqual((status, body["writable"]), (200, False))
        self.assertIn("Account screen", body["reason"])
        status, body = self.send(self.mine, [paper()])
        self.assertEqual(status, 403, body)
        # An admin's user-scoped key is a user too.
        self.assertEqual(self.send(self.user_key, [paper()])[0], 403)
        self.assertEqual(self.remote.posts, [])

    def test_admin_writes_the_remote_server_library(self) -> None:
        self.use_remote_server_library()
        status, body = self.call("GET", "/api/ingest/target", key=self.admin_key)
        self.assertEqual((body["writable"], body["kind"]), (True, "server"), body)
        status, body = self.send(self.admin_key, [paper()])
        self.assertEqual((status, body["stored"], body["failed"]), (200, 1, 0), body)

    def test_a_local_server_library_cannot_be_written(self) -> None:
        # LibraryCase's server library is a local Zotero folder.
        status, body = self.send(self.admin_key, [paper()])
        self.assertEqual(status, 409)
        self.assertIn("only reads", body["error"])

    def test_signed_in_only(self) -> None:
        self.assertEqual(self.call("GET", "/api/ingest/target")[0], 401)
        self.assertEqual(self.send("", [paper()])[0], 401)


class StoreTest(IngestCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.connect(self.user_cookie)[0], 200)

    def test_parents_first_collections_before_items(self) -> None:
        collections = [{"key": "COLLNEW2", "data": {"key": "COLLNEW2", "name": "Sub", "parentCollection": "COLLNEW1"}},
                       {"key": "COLLNEW1", "data": {"key": "COLLNEW1", "name": "Top", "parentCollection": False}}]
        status, body = self.send(self.mine, [pdf(), paper()], collections)
        self.assertEqual((status, body["stored"]), (200, 4), body)
        self.assertEqual([(r["kind"], r["key"]) for r in body["results"]],
                         [("collection", "COLLNEW1"), ("collection", "COLLNEW2"), ("item", "NEWPAPR1"), ("item", "NEWATT01")])
        (first, sent_collections), (second, sent_items) = self.remote.posts
        self.assertEqual((first, second), (ingest.COLLECTIONS_PATH, ingest.ITEMS_PATH))
        self.assertEqual([e["item_key"] for e in sent_items["items"]], ["NEWPAPR1", "NEWATT01"])
        # Zotero's own version number stays home.
        self.assertNotIn("version", sent_items["items"][0]["data"])

    def test_the_paper_shows_up_after_the_next_look(self) -> None:
        self.sync_user()
        self.send(self.mine, [paper()])
        self.sync_user()
        _, mine = self.call("GET", "/api/papers", cookie=self.user_cookie)
        self.assertIn("10.1000/new.1", [p["key"] for p in mine["papers"]])

    def test_one_refused_item_does_not_stop_the_rest(self) -> None:
        status, body = self.send(self.mine, [paper(), paper("NEWPAPR2", title="refuse me")])
        self.assertEqual((status, body["stored"], body["failed"]), (200, 1, 1))
        self.assertEqual(body["results"][1]["error"], "data must be a JSON object")

    def test_bad_input(self) -> None:
        for items in ([{"key": "bad", "data": {"itemType": "book"}}],
                      [{"key": "NEWPAPR1", "data": {"key": "OTHERKEY", "itemType": "book"}}],
                      [{"key": "NEWPAPR1", "data": {"title": "no type"}}],
                      [{"key": "NEWPAPR1", "data": "not json"}],
                      [paper()] * (ingest.MAX_ITEMS + 1)):
            status, body = self.send(self.mine, items)
            self.assertEqual(status, 400, (items[:1], body))
        self.assertEqual(self.send(self.mine, [])[0], 400)
        self.assertEqual(self.remote.posts, [])

    def test_batches_of_a_hundred(self) -> None:
        items = [paper(f"BATCH{n:03d}") for n in range(150)]
        status, body = self.send(self.mine, items)
        self.assertEqual((status, body["stored"]), (200, 150))
        self.assertEqual([len(b["items"]) for _, b in self.remote.posts], [100, 50])

    def test_a_proxy_hiccup_is_retried_once(self) -> None:
        self.remote.post_status = [502]
        self.assertEqual(self.send(self.mine, [paper()])[1]["stored"], 1)
        self.remote.post_status = [401]
        status, body = self.send(self.mine, [paper()])
        self.assertEqual(status, 424)
        self.assertIn("refused the API key", body["error"])
        self.assertNotIn(KEY, json.dumps(body))
        self.assertNotIn(URL, json.dumps(body))


class FileTest(IngestCase):
    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.connect(self.user_cookie)[0], 200)

    def test_file_in_pieces(self) -> None:
        self.send(self.mine, [paper(), pdf()])
        response = self.piece(self.mine, PDF_BYTES, len(PDF_BYTES))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"received": len(PDF_BYTES), "done": True})
        self.assertEqual(self.remote.files["NEWATT01"], PDF_BYTES)
        self.assertEqual(self.remote.posts[-1][1]["filename"], "new.pdf")

    def test_two_pieces(self) -> None:
        self.send(self.mine, [paper(), pdf()])
        size = ingest.UPLOAD_PIECE + 3
        first = self.piece(self.mine, b"a" * ingest.UPLOAD_PIECE, size)
        self.assertEqual(first.json(), {"received": ingest.UPLOAD_PIECE, "done": False})
        last = self.piece(self.mine, b"bbb", size, offset=ingest.UPLOAD_PIECE)
        self.assertEqual(last.json()["done"], True)

    def test_attachment_must_be_stored_first(self) -> None:
        response = self.piece(self.mine, PDF_BYTES, len(PDF_BYTES))
        self.assertEqual(response.status_code, 404)
        self.assertIn("send its item first", response.json()["error"])

    def test_piece_checks(self) -> None:
        self.send(self.mine, [paper(), pdf()])
        self.assertEqual(self.piece(self.mine, PDF_BYTES, len(PDF_BYTES) + 1).status_code, 400)  # short last piece
        self.assertEqual(self.piece(self.mine, PDF_BYTES, len(PDF_BYTES), offset=7).status_code, 400)
        self.assertEqual(self.piece(self.mine, PDF_BYTES, len(PDF_BYTES), attach="bad").status_code, 400)
        self.assertEqual(self.piece(self.mine, b"x" * (ingest.UPLOAD_PIECE + 1), ingest.UPLOAD_PIECE * 2).status_code, 413)

    def test_plain_user_without_own_library(self) -> None:
        other, _ = api_keys.issue_api_key(self.store, self.admin.id, "u", users.ROLE_USER, 3600)
        self.assertEqual(self.piece(other, PDF_BYTES, len(PDF_BYTES)).status_code, 403)


class OrderTest(IngestCase):
    def test_parents_first_handles_loops(self) -> None:
        records = {"AAAAAAAA": {"parentItem": "BBBBBBBB"}, "BBBBBBBB": {"parentItem": "AAAAAAAA"}, "CCCCCCCC": {}}
        self.assertEqual(sorted(k for k, _ in ingest._parents_first(records, "parentItem")), ["AAAAAAAA", "BBBBBBBB", "CCCCCCCC"])
