"""The library read from a ZoteroWebDAV server (app/library/remote.py),
against a fake server: the change feed, the attachment index and one file."""
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from typing import Any

from app.content.service import pdf_signature
from app.library import remote as rl
from app.library.catalogue import Catalogue
from app.search.index import Index

KEY = "testkeyid.secretvalue-never-shown"
PDF = b"%PDF-1.4 remote test"


class FakeServer:
    """GET only, like the real one; records every request."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.attachments: list[dict[str, Any]] = []
        self.requests: list[str] = []
        self.status = 200
        self.resync_once = False
        self.fail: Exception | None = None
        self.webdav: list[dict[str, Any]] = [
            {"id": 7, "name": "work", "label": "Lab profile", "primary": False, "enabled": True},
            {"id": 3, "name": "me", "primary": True, "enabled": True},
            {"id": 9, "name": "off", "primary": False, "enabled": False},
        ]

    def add(self, record: dict[str, Any]) -> None:
        record["rev"] = len(self.records) + 1
        self.records.append(record)

    def __call__(self, request: Any, timeout: int) -> tuple[int, dict[str, str], bytes]:
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") == "Bearer " + KEY
        self.requests.append(request.full_url)
        if self.fail is not None:
            raise self.fail
        if self.status != 200:
            return self.status, {}, b""
        parts = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path == "/api/library/changes":
            since, limit = int(query["since"]), int(query["limit"])
            if self.resync_once and since > 0:
                self.resync_once = False
                return 200, {}, json.dumps({"records": [], "rev": since, "more": False, "full_resync": True}).encode()
            newer = [r for r in self.records if r["rev"] > since]
            page = newer[:limit]
            rev = page[-1]["rev"] if page else since
            return 200, {}, json.dumps({"records": page, "rev": rev, "more": len(newer) > limit, "full_resync": False}).encode()
        if parts.path == "/api/library/attachments":
            offset, limit = int(query.get("offset") or 0), int(query["limit"])
            rows = self.attachments[offset:offset + limit]
            following = offset + len(rows) if offset + len(rows) < len(self.attachments) else 0
            return 200, {}, json.dumps({"attachments": rows, "next": following, "total": len(self.attachments)}).encode()
        if parts.path == "/api/webdav/libraries":
            return 200, {}, json.dumps({"libraries": self.webdav, "max_libraries": 0}).encode()
        if parts.path.endswith("/file"):
            return 200, {"content-type": "application/pdf"}, PDF
        return 404, {}, b""


def item(key: str, title: str, **data: Any) -> dict[str, Any]:
    body = {"key": key, "itemType": "journalArticle", "title": title, **data}
    return {"kind": "item", "key": key, "updated_at": "2026-11-19T07:09:49.5Z", "data": body}


def sample(server: FakeServer) -> None:
    server.add({"kind": "collection", "key": "COLL0001", "data": {"key": "COLL0001", "name": "EEG"}})
    server.add(item(
        "ITEM0001", "Decoding inner speech", DOI="https://doi.org/10.1000/ABC.1", date="2024/08/27",
        publicationTitle="NeuroImage", abstractNote="An abstract.",
        creators=[{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}, {"creatorType": "author", "name": "The Lab"}],
        tags=[{"tag": "eeg"}, {"tag": "eeg"}], collections=["COLL0001"],
    ))
    server.add(item("ITEM0002", "No DOI here"))
    server.add({"kind": "item", "key": "ATTA0001", "updated_at": "", "data": {
        "key": "ATTA0001", "itemType": "attachment", "parentItem": "ITEM0001", "linkMode": "imported_file",
        "contentType": "application/pdf", "filename": "../Lovelace 2024.pdf",
    }})
    # A snapshot and a linked file: neither is a PDF on the server.
    server.add({"kind": "item", "key": "ATTA0002", "updated_at": "", "data": {
        "key": "ATTA0002", "itemType": "attachment", "parentItem": "ITEM0001", "linkMode": "imported_url",
        "contentType": "text/html", "filename": "snap.html",
    }})
    server.add({"kind": "item", "key": "ATTA0003", "updated_at": "", "data": {
        "key": "ATTA0003", "itemType": "attachment", "parentItem": "ITEM0002", "linkMode": "linked_file",
        "contentType": "application/pdf", "filename": "x.pdf",
    }})
    server.add({"kind": "item", "key": "NOTE0001", "updated_at": "", "data": {"key": "NOTE0001", "itemType": "note", "parentItem": "ITEM0001"}})
    server.attachments = [
        {"key": "ATTA0001", "md5": "0123456789abcdef0123456789abcdef", "mtime": 1, "has_zip": True, "has_prop": True},
        {"key": "ATTA0002", "md5": "ffff", "mtime": 1, "has_zip": True, "has_prop": True},
    ]


class RemoteLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / "cache"
        self.server = FakeServer()
        sample(self.server)

    def library(self) -> rl.RemoteLibrary:
        lib = rl.RemoteLibrary(rl.Remote("https://zotero.example.com/", KEY, opener=self.server), self.cache, poll_seconds=30)
        return lib

    def test_read_builds_items_like_the_local_reader(self) -> None:
        lib = self.library()
        self.assertIsNotNone(lib.stamp())
        items = lib.read()
        self.assertEqual(sorted(items), ["10.1000/ABC.1", "nodoi-zotero-ITEM0002"])
        paper = items["10.1000/ABC.1"]
        self.assertEqual(paper.zkey, "ITEM0001")
        self.assertEqual(paper.year, 2024)
        self.assertEqual(paper.journal, "NeuroImage")
        self.assertEqual(paper.authors, ["Ada Lovelace", "The Lab"])
        self.assertEqual(paper.tags, ["eeg"])
        self.assertEqual(paper.collections, ["EEG"])
        self.assertEqual(paper.date_added, "2026-11-19 07:09:49")
        self.assertEqual(paper.fulltext_files, [])
        self.assertEqual(len(paper.pdfs), 1)
        pdf = Path(paper.pdfs[0])
        self.assertEqual(pdf.name, "Lovelace 2024.pdf")
        self.assertEqual(rl.attachment_of(pdf), "ATTA0001")
        self.assertIn("0123456789abcdef0123456789abcdef", pdf.parts)
        self.assertEqual(items["nodoi-zotero-ITEM0002"].pdfs, [])
        self.assertEqual(set(paper.to_dict()), set(items["nodoi-zotero-ITEM0002"].to_dict()))

    def test_polls_only_every_poll_seconds_and_picks_up_changes(self) -> None:
        lib = self.library()
        now = [1000.0]
        lib.clock = lambda: now[0]
        first = lib.stamp()
        asked = len(self.server.requests)
        self.assertEqual(lib.stamp(), first)
        self.assertEqual(len(self.server.requests), asked)
        self.server.add(item("ITEM0003", "A new paper"))
        self.server.add({"kind": "item", "key": "ITEM0002", "deleted": True})
        now[0] += 31
        self.assertNotEqual(lib.stamp(), first)
        self.assertTrue(any("since=7" in url for url in self.server.requests))
        self.assertEqual(sorted(lib.read()), ["10.1000/ABC.1", "nodoi-zotero-ITEM0003"])

    def test_restart_reuses_the_mirror(self) -> None:
        self.library().stamp()
        self.server.requests.clear()
        lib = self.library()
        lib.stamp()
        self.assertTrue(any("since=7" in url for url in self.server.requests))
        self.assertFalse(any("since=0" in url for url in self.server.requests))
        self.assertEqual(len(lib.read()), 2)
        self.assertEqual(oct((self.cache / rl.MIRROR_FILE).stat().st_mode & 0o777), "0o600")

    def test_full_resync_starts_over(self) -> None:
        lib = self.library()
        lib.stamp()
        self.server.resync_once = True
        lib.poll_now()
        lib.stamp()
        self.assertTrue(any("since=0" in url for url in self.server.requests[-4:]))
        self.assertEqual(len(lib.read()), 2)

    def test_a_mirror_of_another_server_is_not_used(self) -> None:
        self.library().stamp()
        other = rl.RemoteLibrary(rl.Remote("https://other.example.com", KEY, opener=self.server), self.cache)
        self.server.requests.clear()
        other.stamp()
        self.assertTrue(any("since=0" in url for url in self.server.requests))

    def test_ensure_pdf_downloads_once(self) -> None:
        lib = self.library()
        lib.stamp()
        path = Path(lib.read()["10.1000/ABC.1"].pdfs[0])
        self.assertFalse(path.exists())
        self.assertEqual(lib.ensure_pdf(path), path)
        self.assertEqual(path.read_bytes(), PDF)
        asked = len(self.server.requests)
        self.assertEqual(lib.ensure_pdf(path), path)
        self.assertEqual(len(self.server.requests), asked)
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])  # no temp file left
        # Never a path outside the library's own files.
        self.assertIsNone(lib.ensure_pdf("/etc/passwd"))

    def test_signature_does_not_change_when_the_file_arrives(self) -> None:
        lib = self.library()
        lib.stamp()
        record = {"pdfs": lib.read()["10.1000/ABC.1"].pdfs}
        before = pdf_signature(record)
        lib.ensure_pdf(record["pdfs"][0])
        self.assertEqual(pdf_signature(record), before)

    def test_errors_never_carry_the_key_or_address(self) -> None:
        for status, fail in ((401, None), (500, None), (200, OSError("connection refused to https://zotero.example.com"))):
            with self.subTest(status=status, fail=fail):
                server = FakeServer()
                server.status, server.fail = status, fail
                lib = rl.RemoteLibrary(rl.Remote("https://zotero.example.com", KEY, opener=server), self.cache / str(status))
                self.assertIsNone(lib.stamp())
                self.assertTrue(lib.error)
                self.assertNotIn(KEY, lib.error)
                self.assertNotIn("zotero.example.com", lib.error)

    def test_offline_keeps_the_last_copy(self) -> None:
        lib = self.library()
        lib.stamp()
        self.server.fail = OSError("down")
        lib.poll_now()
        self.assertIsNotNone(lib.stamp())
        self.assertIn("could not be reached", lib.error)
        self.assertEqual(len(lib.read()), 2)

    def test_catalogue_reads_a_remote_library(self) -> None:
        lib = self.library()
        index = Index(self.cache / "search.db")
        self.addCleanup(index.close)
        catalogue = Catalogue(lib, index)
        catalogue.sync()
        self.assertEqual(catalogue.status.error, "")
        self.assertIsNotNone(catalogue.find("10.1000/ABC.1"))

    def test_safe_name_stays_one_component(self) -> None:
        for raw in ("../../etc/passwd", "a/b\\c.pdf", "", ".hidden.pdf", "x" * 400 + ".pdf"):
            with self.subTest(raw=raw[:20]):
                name = rl.safe_name(raw)
                self.assertTrue(name)
                self.assertNotIn("/", name)
                self.assertFalse(name.startswith("."))
                self.assertLessEqual(len(name), 180)


if __name__ == "__main__":
    unittest.main()


class OnDemandTest(unittest.TestCase):
    """Switching a library from local to remote redoes nothing: what was made
    from the local text is kept, and work that needs a PDF waits until its
    paper is opened."""

    def setUp(self) -> None:
        from app.content.service import ContentService
        from app.core import db
        from app.library.zotero import Library
        from app.tests.zotero_fixture import sample as zotero_sample

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = self.root = Path(directory.name)
        zotero_sample(root / "Zotero")
        self.index = Index(root / "cache" / "search.db")
        self.addCleanup(self.index.close)
        self.store = db.open_store(root / "app.db", "k" * 64, False)
        vocab = root / "modalities.yaml"
        vocab.write_text((Path(__file__).resolve().parents[2] / "config" / "modalities.yaml").read_text())

        class Settings:
            openalex_enabled = False
            openalex_api_key = ""
            # These tests are about the papers nobody opened (on demand);
            # test_every_paper_runs_by_default turns it off.
            process_on_open = True

        self.settings = Settings

        def service(library: Any) -> ContentService:
            catalogue = Catalogue(library, self.index)
            catalogue.load()
            catalogue.sync()
            content = ContentService(root / "papers", root / "cache" / "search.db", catalogue, self.store, vocab, lambda: Settings())
            self.addCleanup(content.close)
            return content

        self.service = service
        self.local = service(Library(root / "Zotero", root / "cache"))
        self.local.reconcile()
        while self.local.step("local"):
            pass
        # The same two papers with a DOI, on a server.
        server = FakeServer()
        for n, (doi, title) in enumerate((("10.1006/nimg.2001.0931", "Temporal Autocorrelation in Univariate Linear Modeling of FMRI Data"),
                                          ("10.48550/arXiv.2606.20696", "MindAlign: Decoding Inner Speech from fMRI Signals"))):
            server.add(item(f"REMT000{n}", title, DOI=doi))
            server.add({"kind": "item", "key": f"RATT000{n}", "updated_at": "", "data": {
                "key": f"RATT000{n}", "itemType": "attachment", "parentItem": f"REMT000{n}", "linkMode": "imported_file",
                "contentType": "application/pdf", "filename": "paper.pdf"}})
            server.attachments.append({"key": f"RATT000{n}", "md5": f"{n}" * 32, "mtime": 1, "has_zip": True, "has_prop": True})
        self.remote_library = rl.RemoteLibrary(rl.Remote("https://zotero.example.com", KEY, opener=server), root / "cache")

    def states(self, content: Any, key: str) -> dict[str, str]:
        return {stage: task["state"] for stage, task in content.files.of(key).items()}

    def test_switching_to_remote_redoes_nothing(self) -> None:
        from app.content import store as st

        doi = "10.48550/arXiv.2606.20696"
        before = self.states(self.local, doi)
        self.assertEqual(before[st.METHODS], st.DONE)
        self.assertEqual(before[st.FIGURES], st.PENDING)  # no worker in tests
        had_text = self.local.catalogue.get(doi).has_text
        self.assertTrue(had_text)

        remote = self.service(self.remote_library)
        self.assertTrue(remote.on_demand)
        remote.reconcile()
        while remote.step("local"):
            pass
        after = self.states(remote, doi)
        for stage in st.LOCAL:
            if stage in before:
                self.assertEqual(after[stage], before[stage], stage)
        self.assertEqual(after[st.FIGURES], st.HELD)
        self.assertNotIn(st.OCR, after)
        # The search text from the local library is kept.
        self.assertTrue(remote.catalogue.get(doi).has_text)
        self.assertEqual(remote.files.counts()[st.METHODS][st.PENDING], 0)

        # Opening the paper starts its PDF work, and only its.
        remote.open(doi)
        remote.reconcile()
        opened = self.states(remote, doi)
        self.assertEqual(opened[st.FIGURES], st.PENDING)
        self.assertEqual(opened[st.METHODS], st.DONE)  # made from the local text: kept
        other = self.states(remote, "10.1006/nimg.2001.0931")
        self.assertEqual(other[st.FIGURES], st.HELD)
        task = remote.files.claim((st.FIGURES,), "worker")
        self.assertEqual(task["key"], doi)
        self.assertEqual(rl.attachment_of(task["input"]["pdf"]), "RATT0001")
        # Remembered across a restart.
        self.assertIn(doi, self.service(self.remote_library).demanded)

    def test_switching_back_to_local_redoes_nothing(self) -> None:
        """The index remembers the remote PDF paths; a restart in local mode
        must not queue from them before it has read the local library."""
        from app.content import store as st
        from app.content.service import ContentService
        from app.library.zotero import Library

        doi = "10.48550/arXiv.2606.20696"
        before = self.states(self.local, doi)
        remote = self.service(self.remote_library)
        remote.reconcile()

        catalogue = Catalogue(Library(self.root / "Zotero", self.root / "cache"), self.index)
        catalogue.load()
        self.assertTrue(rl.is_remote_path(catalogue.get(doi).record["pdfs"][0]))

        class Settings:
            openalex_enabled = False
            openalex_api_key = ""

        content = ContentService(self.root / "papers", self.root / "cache" / "search.db", catalogue, self.store,
                                 self.root / "modalities.yaml", lambda: Settings())
        self.addCleanup(content.close)
        self.assertEqual(content.reconcile(), 0)
        catalogue.sync()
        content.reconcile()
        after = self.states(content, doi)
        for stage in st.LOCAL:
            if stage in before:
                self.assertEqual(after[stage], before[stage], stage)

    def test_a_paper_missing_on_the_server_is_kept(self) -> None:
        """The no-DOI paper is not on the server (its key differs there): it
        goes out of sight but keeps its index entry and results, and
        switching back finds them, with nothing redone."""
        from app.content import store as st
        from app.library.catalogue import VANISHED_KEEP_SECONDS
        from app.library.zotero import Library

        nodoi = next(p.key for p in self.local.catalogue.all() if p.key.startswith("nodoi-"))
        before = self.states(self.local, nodoi)
        self.assertEqual(before[st.METHODS], st.DONE)

        remote = self.service(self.remote_library)
        remote.reconcile()
        self.assertIsNone(remote.catalogue.get(nodoi))
        self.assertIn(nodoi, remote.catalogue.vanished())
        kept = self.states(remote, nodoi)
        self.assertEqual(kept[st.METHODS], st.DONE)
        self.assertFalse({st.PENDING, st.FAILED} & set(kept.values()), kept)
        self.assertTrue(remote.files.dir(nodoi).is_dir())
        self.assertNotIn(nodoi, {p.key for p in remote.catalogue.search("orsted").rows})
        while remote.step("local"):
            pass
        task = remote.files.claim((st.FIGURES,), "worker")
        self.assertTrue(task is None or task["key"] != nodoi)

        # Back to the local library: as it was.
        local = self.service(Library(self.root / "Zotero", self.root / "cache"))
        self.assertEqual(local.catalogue.vanished(), set())
        paper = local.catalogue.get(nodoi)
        self.assertIsNotNone(paper)
        self.assertIn(nodoi, {p.key for p in local.catalogue.search("orsted").rows})
        local.reconcile()
        after = self.states(local, nodoi)
        self.assertEqual(after, before)

        # Gone for longer than the keep: dropped for good.
        remote = self.service(self.remote_library)
        remote.reconcile()
        paper = remote.catalogue._vanished[nodoi]
        paper.record["_vanished"] -= VANISHED_KEEP_SECONDS + 1
        remote.catalogue.sync(force=True)
        remote.reconcile()
        self.assertNotIn(nodoi, remote.catalogue.vanished())
        self.assertEqual(self.states(remote, nodoi), {})
        self.assertFalse(any(remote.files.dir(nodoi).glob("*")))

    def test_a_paper_new_on_the_server_waits_until_opened(self) -> None:
        from app.content import store as st

        self.remote_library.remote.opener.add(item("NEWP0001", "Brand new", DOI="10.1000/new.1"))
        self.remote_library.remote.opener.add({"kind": "item", "key": "NATT0001", "updated_at": "", "data": {
            "key": "NATT0001", "itemType": "attachment", "parentItem": "NEWP0001", "linkMode": "imported_file",
            "contentType": "application/pdf", "filename": "new.pdf"}})
        self.remote_library.remote.opener.attachments.append({"key": "NATT0001", "md5": "a" * 32, "mtime": 1, "has_zip": True, "has_prop": True})
        remote = self.service(self.remote_library)
        remote.reconcile()
        self.assertEqual(set(self.states(remote, "10.1000/new.1")), {st.OPENALEX})
        remote.open("10.1000/new.1")
        remote.reconcile()
        states = self.states(remote, "10.1000/new.1")
        self.assertEqual(states[st.FIGURES], st.PENDING)
        self.assertEqual(states[st.OCR], st.PENDING)
        self.assertNotIn(st.METHODS, states)  # waits for the text the worker reads
        # The OCR (text layer) arrives: the text stages run from it.
        remote.files.claim((st.OCR,), "worker")
        folder = remote.files.dir("10.1000/new.1")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ocr.txt").write_text("We recorded EEG from twelve participants. Code at https://github.com/example/new.")
        remote.files.finish("10.1000/new.1", st.OCR, self.states_sig(remote, "10.1000/new.1", st.OCR), st.DONE, {"chars": 80})
        remote.watch()
        remote.reconcile()
        while remote.step("local"):
            pass
        self.assertEqual(self.states(remote, "10.1000/new.1")[st.METHODS], st.DONE)

    def states_sig(self, content: Any, key: str, stage: str) -> str:
        return content.files.rows()[(key, stage)][1]

    def test_every_paper_runs_by_default(self) -> None:
        """library.process_on_open off (the default): every paper's PDF work
        is queued as it arrives, opened or not, and what the local library's
        text already made is still kept, never redone."""
        from app.content import store as st

        self.settings.process_on_open = False
        remote = self.service(self.remote_library)
        remote.reconcile()
        for doi in ("10.48550/arXiv.2606.20696", "10.1006/nimg.2001.0931"):
            states = self.states(remote, doi)
            self.assertEqual(states[st.FIGURES], st.PENDING, doi)
            self.assertEqual(states[st.METHODS], st.DONE, doi)
            self.assertNotIn(st.OCR, states)  # its text stages are done
        self.assertEqual(remote.files.counts()[st.METHODS][st.PENDING], 0)
        # Turned on again: what nobody opened waits.
        self.settings.process_on_open = True
        remote.reconcile()
        self.assertEqual(self.states(remote, "10.1006/nimg.2001.0931")[st.FIGURES], st.HELD)

    def test_back_to_local_releases_what_was_held(self) -> None:
        from app.content import store as st

        remote = self.service(self.remote_library)
        remote.reconcile()
        self.assertEqual(self.states(remote, "10.1006/nimg.2001.0931")[st.FIGURES], st.HELD)
        local = self.service(__import__("app.library.zotero", fromlist=["Library"]).Library(self.root / "Zotero", self.root / "cache"))
        local.reconcile()
        self.assertEqual(self.states(local, "10.1006/nimg.2001.0931")[st.FIGURES], st.PENDING)


class NewerServer(FakeServer):
    """A server with GET /api/library/snapshot, files_stamp, attachments?since=
    and changes?wait= (ZoteroWebDAV's newer library API)."""

    def __init__(self) -> None:
        super().__init__()
        self.files_stamp = 1000
        self.waited: list[str] = []

    def touch_file(self, row: dict[str, Any]) -> None:
        self.files_stamp += 1
        row["updated_at"] = f"2026-11-19T08:00:{self.files_stamp % 60:02d}Z"
        self.attachments = [r for r in self.attachments if r["key"] != row["key"]] + [row]

    def __call__(self, request: Any, timeout: int) -> tuple[int, dict[str, str], bytes]:
        import gzip as gz

        parts = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path == "/api/library/snapshot":
            self.requests.append(request.full_url)
            assert request.get_header("Accept-encoding") == "gzip"
            live = {}
            for record in self.records:
                live[(record["kind"], record["key"])] = record
            body = {
                "rev": len(self.records), "files_stamp": self.files_stamp,
                "items": [r for r in live.values() if r["kind"] == "item" and not r.get("deleted")],
                "collections": [r for r in live.values() if r["kind"] == "collection" and not r.get("deleted")],
                "attachments": self.attachments,
            }
            return 200, {"content-encoding": "gzip"}, gz.compress(json.dumps(body).encode())
        if "wait" in query:
            self.waited.append(query["wait"])
        status, headers, body = super().__call__(request, timeout)
        if status == 200 and parts.path in ("/api/library/changes", "/api/library/attachments"):
            data = json.loads(body)
            data["files_stamp"] = self.files_stamp
            if parts.path == "/api/library/attachments" and query.get("since"):
                data["attachments"] = [r for r in self.attachments if r.get("updated_at", "") > query["since"]]
            body = json.dumps(data).encode()
        return status, headers, body


class NewerServerTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / "cache"
        self.server = NewerServer()
        sample(self.server)
        for row in self.server.attachments:
            row["updated_at"] = "2026-11-19T07:00:00Z"

    def library(self) -> rl.RemoteLibrary:
        return rl.RemoteLibrary(rl.Remote("https://zotero.example.com", KEY, opener=self.server), self.cache)

    def test_first_look_is_one_snapshot(self) -> None:
        lib = self.library()
        lib.stamp()
        self.assertEqual(len(self.server.requests), 1)
        self.assertIn("/api/library/snapshot", self.server.requests[0])
        self.assertEqual(sorted(lib.read()), ["10.1000/ABC.1", "nodoi-zotero-ITEM0002"])
        self.assertEqual(len(lib.read()["10.1000/ABC.1"].pdfs), 1)

    def test_keeps_up_by_waiting_and_asks_only_for_changed_files(self) -> None:
        lib = self.library()
        lib.stamp()  # the snapshot, which says the server can wait
        self.server.requests.clear()
        lib.stamp()
        self.assertEqual(self.server.waited[-1], str(rl.WAIT_SECONDS))
        self.assertTrue(all("/api/library/attachments" not in url for url in self.server.requests))  # nothing changed

        # A file arrives for ITEM0002's attachment: only it is fetched.
        self.server.add({"kind": "item", "key": "ATTA0009", "updated_at": "", "data": {
            "key": "ATTA0009", "itemType": "attachment", "parentItem": "ITEM0002", "linkMode": "imported_file",
            "contentType": "application/pdf", "filename": "new.pdf"}})
        self.server.touch_file({"key": "ATTA0009", "md5": "9" * 32, "mtime": 2, "has_zip": True, "has_prop": True})
        self.server.requests.clear()
        lib.stamp()
        since = [url for url in self.server.requests if "/api/library/attachments" in url]
        self.assertEqual(len(since), 1)
        self.assertIn("since=", since[0])
        self.assertEqual(len(lib.read()["nodoi-zotero-ITEM0002"].pdfs), 1)
        # The other attachment is still known.
        self.assertEqual(len(lib.read()["10.1000/ABC.1"].pdfs), 1)

    def test_restart_reads_changes_not_the_snapshot(self) -> None:
        self.library().stamp()
        self.server.requests.clear()
        self.library().stamp()
        self.assertFalse(any("/snapshot" in url for url in self.server.requests))


class OnDemandOpenTest(OnDemandTest):
    def test_opening_a_finished_paper_skips_its_ocr(self) -> None:
        from app.content import store as st

        doi = "10.48550/arXiv.2606.20696"
        remote = self.service(self.remote_library)
        remote.reconcile()
        # Held from before the switch, as on a real library.
        remote.files.want([(doi, st.OCR, "pdf:old", "", 0.0, {"pdf": "x"})])
        remote.files.hold(st.LOCAL + st.HEAVY, set())
        self.assertEqual(self.states(remote, doi)[st.OCR], st.HELD)
        remote.open(doi)
        remote.reconcile()
        states = self.states(remote, doi)
        self.assertEqual(states[st.FIGURES], st.PENDING)
        self.assertEqual(states[st.OCR], st.HELD)  # its text stages are done
