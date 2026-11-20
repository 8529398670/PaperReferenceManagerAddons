"""Each user's own library (app/models/user_library.py, app/library/registry.py,
app/routes/account_library.py): stored sealed, never sent back, read instead
of the server's library by that user only, and counted by the shared content
queue without disturbing anyone else's papers."""
from __future__ import annotations

import json

from app.core import db, encryption
from app.library import remote as rl
from app.models import sealed, user_library, users
from app.tests.test_lists_routes import LibraryCase, WOOLRICH
from app.tests.test_remote_library import KEY, PDF, FakeServer, sample

URL = "https://zotero.example.com"


class UserLibraryCase(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        self.libraries = self.app.state.libraries
        # LibraryCase points app.state.library at the fake Zotero.
        self.libraries.server = self.app.state.library
        self.remote = FakeServer()
        sample(self.remote)
        self.libraries.remote_factory = lambda source: rl.Remote(source.url, source.key, source.name, opener=self.remote)
        self.libraries.host_ok = lambda url: True
        self.addCleanup(self.libraries.close)

    def connect(self, cookie: str, url: str = URL, key: str = KEY) -> tuple[int, dict]:
        return self.call("POST", "/api/account/library", cookie=cookie,
                         body={"url": url, "key": key, "library": "", "csrf_token": self.csrf(cookie)})

    def share_server(self, on: bool = True) -> None:
        """library.users_read_server, as if config.yaml said so."""
        from dataclasses import replace

        settings = self.libraries.settings
        current = settings.get()
        settings._current = replace(current, library=replace(current.library, users_read_server=on))

    def sync_user(self) -> None:
        service = self.libraries.for_user(users.get_user(self.store, self.user.id), start=False)
        self.assertIsNot(service, self.libraries.server)
        service._load_and_sync()


class StoringTest(UserLibraryCase):
    def test_saved_sealed_and_never_sent_back(self) -> None:
        status, body = self.connect(self.user_cookie)
        self.assertEqual(status, 200, body)
        self.assertEqual((body["own"], body["url"], body["key_set"]), (True, URL, True))
        status, me = self.call("GET", "/api/me", cookie=self.user_cookie)
        self.assertTrue(me["library"]["own"])
        self.assertNotIn(KEY, json.dumps(me))
        # Sealed inside the record, on top of the record's own encryption.
        raw = self.store.get(db.BUCKET_USERS, self.user.id)
        self.assertNotIn(KEY, json.dumps(raw))
        self.assertNotIn(URL, json.dumps(raw))
        # Someone else still reads the server's library.
        status, other = self.call("GET", "/api/me", cookie=self.admin_cookie)
        self.assertEqual((other["library"]["own"], other["library"]["url"]), (False, ""))

    def test_empty_key_keeps_the_stored_one(self) -> None:
        self.assertEqual(self.connect(self.user_cookie)[0], 200)
        status, body = self.connect(self.user_cookie, key="")
        self.assertEqual((status, body["key_set"]), (200, True))
        source = user_library.source_of(users.get_user(self.store, self.user.id), self.cfg.secret_key)
        self.assertEqual(source.key, KEY)

    def test_session_only_and_csrf(self) -> None:
        status, _ = self.call("POST", "/api/account/library", key=self.user_key, body={"url": URL, "key": KEY})
        self.assertNotEqual(status, 200)
        status, _ = self.call("POST", "/api/account/library", cookie=self.user_cookie, body={"url": URL, "key": KEY})
        self.assertEqual(status, 403)

    def test_bad_input_and_refusals_never_echo_the_key(self) -> None:
        for url, key in (("http://zotero.example.com", KEY), (URL, "not-a-key"), ("https://x.org?a=1", KEY)):
            status, body = self.connect(self.user_cookie, url=url, key=key)
            self.assertEqual(status, 400, (url, body))
            self.assertNotIn(KEY, json.dumps(body))
        self.remote.status = 401
        status, body = self.connect(self.user_cookie)
        self.assertEqual(status, 400)
        self.assertIn("refused the API key", body["error"])
        self.assertNotIn(KEY, json.dumps(body))
        self.assertNotIn("zotero.example.com", json.dumps(body))
        self.assertFalse(users.get_user(self.store, self.user.id).library_url)

    def test_private_addresses_are_refused_for_users_not_the_owner(self) -> None:
        self.libraries.host_ok = user_library.public_host
        status, body = self.connect(self.user_cookie, url="https://127.0.0.1:8443")
        self.assertEqual(status, 400)
        self.assertIn("public server", body["error"])
        status, body = self.connect(self.owner_cookie, url="https://127.0.0.1:8443")
        self.assertEqual(status, 200, body)

    def test_clear_goes_back_to_the_server_library(self) -> None:
        self.connect(self.user_cookie)
        self.sync_user()
        folder = self.libraries.folder(self.user.id)
        self.assertTrue(folder.is_dir())
        status, body = self.call("POST", "/api/account/library/clear", cookie=self.user_cookie,
                                 body={"csrf_token": self.csrf(self.user_cookie)})
        self.assertEqual((status, body["own"]), (200, False))
        self.assertFalse(folder.exists())
        self.assertIsNone(user_library.source_of(users.get_user(self.store, self.user.id), self.cfg.secret_key))

    def test_the_key_survives_a_key_rotation(self) -> None:
        self.connect(self.user_cookie)
        record = self.store.get(db.BUCKET_USERS, self.user.id)
        new_key = encryption.generate_key_hex()
        sealed.rekey_record(self.cfg.secret_key, new_key)(db.BUCKET_USERS, record)
        source = user_library.source_of(users.User.from_record(record), new_key)
        self.assertEqual((source.url, source.key), (URL, KEY))


class ReadingTest(UserLibraryCase):
    def test_each_user_reads_their_own_library(self) -> None:
        self.connect(self.user_cookie)
        self.sync_user()
        _, mine = self.call("GET", "/api/papers", cookie=self.user_cookie)
        _, server = self.call("GET", "/api/papers", cookie=self.admin_cookie)
        self.assertEqual(sorted(p["key"] for p in mine["papers"]), ["10.1000/ABC.1", "nodoi-zotero-ITEM0002"])
        self.assertEqual(server["status"]["papers"], 3)
        self.assertIn(WOOLRICH, [p["key"] for p in server["papers"]])
        # The built-in Library list is the reader's library too.
        _, mine = self.call("GET", "/api/lists/library", cookie=self.user_cookie)
        self.assertEqual(mine["list"]["count"], 2)
        _, server = self.call("GET", "/api/lists/library", cookie=self.admin_cookie)
        self.assertEqual(server["list"]["count"], 3)

    def test_a_server_paper_still_opens_but_never_another_users_pdf(self) -> None:
        self.connect(self.user_cookie)
        self.sync_user()
        # The server's paper (a shared list can hold it) opens for the user
        # only while the server's library is shared with users.
        self.assertEqual(self.call("GET", "/api/paper?key=" + WOOLRICH, cookie=self.user_cookie)[0], 404)
        self.share_server()
        self.assertEqual(self.call("GET", "/api/paper?key=" + WOOLRICH, cookie=self.user_cookie)[0], 200)
        # The user's paper does not open for someone else, nor its PDF.
        self.assertEqual(self.call("GET", "/api/paper?key=10.1000/ABC.1", cookie=self.admin_cookie)[0], 404)
        self.assertEqual(self.request("GET", "/api/paper/pdf?key=10.1000/ABC.1", cookie=self.admin_cookie).status_code, 404)
        # Its owner gets it, fetched from their server.
        response = self.request("GET", "/api/paper/pdf?key=10.1000/ABC.1", cookie=self.user_cookie)
        self.assertEqual((response.status_code, response.content), (200, PDF))

    def test_content_keeps_every_librarys_papers(self) -> None:
        self.connect(self.user_cookie)
        self.sync_user()
        content = self.app.state.content
        keys = {paper.key for paper in content.catalogue.all()}
        self.assertIn(WOOLRICH, keys)
        self.assertIn("10.1000/ABC.1", keys)
        # A user's paper is on demand, whatever the server's library is.
        self.assertTrue(content._on_demand("10.1000/ABC.1"))
        self.assertFalse(content._on_demand(WOOLRICH))
        content.reconcile()
        rows = content.files.rows()
        self.assertIn(("10.1000/ABC.1", "openalex"), rows)
        # Reconciling again changes nothing: the copies do not fight.
        self.assertEqual(content.reconcile(), 0)
        # Cleared: the paper's results are kept a while, not dropped.
        self.call("POST", "/api/account/library/clear", cookie=self.user_cookie, body={"csrf_token": self.csrf(self.user_cookie)})
        content.reconcile()
        self.assertIn(("10.1000/ABC.1", "openalex"), content.files.rows())


class WatcherTest(UserLibraryCase):
    def test_a_request_thread_starts_the_watcher_on_the_servers_loop(self) -> None:
        import asyncio
        import threading

        self.connect(self.user_cookie)
        user = users.get_user(self.store, self.user.id)

        async def run() -> bool:
            self.libraries._loop = asyncio.get_running_loop()
            # A route handler runs in a worker thread, with no event loop.
            thread = threading.Thread(target=self.libraries.for_user, args=(user,))
            thread.start()
            thread.join()
            await asyncio.sleep(0.05)
            service = self.libraries.own(user)
            running = service is not None and service.running
            if service is not None:
                await service.stop()
            return running

        self.assertTrue(asyncio.run(run()))


class PoolScopeTest(UserLibraryCase):
    def test_each_reader_sees_the_works_their_own_library_lacks(self) -> None:
        from app.content import pool as P
        from app.extras.searches import SavedSearches

        self.connect(self.user_cookie)
        self.sync_user()
        content = self.app.state.content
        pool = content.pool
        theirs = {"wid": "W1", "title": "Graph attention for proteins", "abstract": "A protein model."}
        ours = {"wid": "W2", "title": "Graph cuts for images", "abstract": "An image model."}
        pool.put_paper("10.1000/ABC.1", "s", [theirs], [])
        pool.put_paper(WOOLRICH, "s", [ours], [])

        _, mine = self.call("GET", "/api/missing", cookie=self.user_cookie)
        _, server = self.call("GET", "/api/missing", cookie=self.admin_cookie)
        self.assertEqual([w["wid"] for w in mine["works"]], ["W1"])
        self.assertEqual([w["wid"] for w in server["works"]], ["W2"])

        # The review's rows of the pool, per library.
        user_scope = ({"10.1000/ABC.1", "nodoi-zotero-ITEM0002"}, set(), set(), set())
        server_scope = ({WOOLRICH}, set(), set(), set())
        pool.review_store("sig", [(work_id, P.RV_IN, "", "") for work_id, _, _ in pool.review_due("sig", 10)])
        self.assertEqual([r["wid"] for r in pool.review_rows("sig", P.RV_IN, 10, user_scope)[0]], ["W1"])
        self.assertEqual(pool.review_tally("sig", server_scope)["total"], 1)
        # A work one library has is still missing for the other.
        pool.set_library({"W2"}, set(), set())
        self.assertEqual([r["wid"] for r in pool.review_rows("sig", P.RV_IN, 10, ({"10.1000/ABC.1"}, set(), set(), set()))[0]], ["W1"])

        # A saved search, run by each reader.
        searches = SavedSearches(self.store, content.catalogue, lambda: pool, set)
        search = {"id": "x", "name": "graphs", "query": "", "groups": [{"name": "g", "mode": "any", "terms": ["graph"], "required": True}]}
        rows, total, _ = searches.run_missing(search, scope=user_scope)
        self.assertEqual(([r["wid"] for r in rows], total), (["W1"], 1))
        rows, total, _ = searches.run_missing(search, scope=server_scope)
        self.assertEqual([r["wid"] for r in rows], ["W2"])


class LibrariesListTest(UserLibraryCase):
    def find(self, cookie: str, url: str = URL, key: str = KEY) -> tuple[int, dict]:
        return self.call("POST", "/api/account/library/libraries", cookie=cookie,
                         body={"url": url, "key": key, "csrf_token": self.csrf(cookie)})

    def test_lists_enabled_libraries_default_first(self) -> None:
        status, body = self.find(self.user_cookie)
        self.assertEqual(status, 200, body)
        self.assertEqual([(r["name"], r["primary"]) for r in body["libraries"]], [("me", True), ("work", False)])
        self.assertEqual(body["libraries"][1]["label"], "Lab profile")
        # Nothing is saved by looking.
        self.assertFalse(users.get_user(self.store, self.user.id).library_url)

    def test_empty_key_uses_the_stored_one(self) -> None:
        self.assertEqual(self.find(self.user_cookie, key="")[0], 400)
        self.connect(self.user_cookie)
        status, body = self.find(self.user_cookie, key="")
        self.assertEqual((status, len(body["libraries"])), (200, 2))

    def test_refusals_are_worded_and_never_echo(self) -> None:
        self.libraries.host_ok = user_library.public_host
        status, body = self.find(self.user_cookie, url="https://127.0.0.1:8443")
        self.assertEqual(status, 400)
        self.libraries.host_ok = lambda url: True
        for code, words in ((401, "refused the API key"), (404, "does not list WebDAV libraries")):
            self.remote.status = code
            status, body = self.find(self.user_cookie)
            self.assertEqual(status, 400)
            self.assertIn(words, body["error"])
            self.assertNotIn(KEY, json.dumps(body))
            self.assertNotIn("zotero.example.com", json.dumps(body))

    def test_session_only_and_csrf(self) -> None:
        status, _ = self.call("POST", "/api/account/library/libraries", key=self.user_key, body={"url": URL, "key": KEY})
        self.assertNotEqual(status, 200)
        status, _ = self.call("POST", "/api/account/library/libraries", cookie=self.user_cookie, body={"url": URL, "key": KEY})
        self.assertEqual(status, 403)


class ServerSharingTest(UserLibraryCase):
    def test_users_see_nothing_until_they_connect_unless_shared(self) -> None:
        # Off by default: a user with no library of their own sees no papers.
        _, me = self.call("GET", "/api/me", cookie=self.user_cookie)
        self.assertEqual((me["library"]["own"], me["library"]["server_allowed"], me["library"]["papers"]), (False, False, 0))
        _, papers = self.call("GET", "/api/papers", cookie=self.user_cookie)
        self.assertEqual(papers["papers"], [])
        self.assertIn("Account screen", papers["status"]["error"])
        self.assertEqual(self.call("GET", "/api/paper?key=" + WOOLRICH, cookie=self.user_cookie)[0], 404)
        _, listed = self.call("GET", "/api/lists/library", cookie=self.user_cookie)
        self.assertEqual(listed["list"]["count"], 0)
        # Admins always read it.
        _, admin = self.call("GET", "/api/me", cookie=self.admin_cookie)
        self.assertTrue(admin["library"]["server_allowed"])
        _, papers = self.call("GET", "/api/papers", cookie=self.admin_cookie)
        self.assertEqual(papers["status"]["papers"], 3)
        # Shared: the user reads it too.
        self.share_server()
        _, papers = self.call("GET", "/api/papers", cookie=self.user_cookie)
        self.assertEqual(papers["status"]["papers"], 3)
        # Connected: their own, either way.
        self.share_server(False)
        self.connect(self.user_cookie)
        self.sync_user()
        _, papers = self.call("GET", "/api/papers", cookie=self.user_cookie)
        self.assertEqual(len(papers["papers"]), 2)

    def test_the_missing_pool_is_empty_without_a_library(self) -> None:
        self.app.state.content.pool.put_paper(WOOLRICH, "s", [{"wid": "W2", "title": "Graph cuts", "abstract": ""}], [])
        _, server = self.call("GET", "/api/missing", cookie=self.admin_cookie)
        self.assertEqual([w["wid"] for w in server["works"]], ["W2"])
        _, mine = self.call("GET", "/api/missing", cookie=self.user_cookie)
        self.assertEqual(mine["works"], [])
