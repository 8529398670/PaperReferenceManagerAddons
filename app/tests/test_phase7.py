"""Phase 7: saved searches, missing.xlsx, the research-log check, the crawl,
LLM summaries and the Google Sheets mirror (app/extras/, app/boards/
sheetsync.py), and their routes."""
from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.boards import sheetmirror, sheetsync
from app.boards import store as boards
from app.boards.service import BoardService
from app.content.pool import Pool
from app.core import db
from app.extras import crawl as cr
from app.extras import llm, logcheck, xlsx
from app.extras import searches as ss
from app.extras import summaries as sm
from app.library.catalogue import Catalogue
from app.library.zotero import Library
from app.search.index import Index
from app.tests.zotero_fixture import sample

ROOT = Path(__file__).resolve().parents[2]


def work(wid: str, title: str, abstract: str = "", cited_by: int = 1, doi: str = "") -> dict[str, Any]:
    return {"wid": wid, "title": title, "abstract": abstract, "year": 2024, "cited_by": cited_by, "doi": doi,
            "authors": [["A1", "Ada Lovelace", ""]], "journal": "J"}


class LibraryCase(unittest.TestCase):
    """The fixture library (three papers) with its index and a pool."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.zotero = sample(self.root / "Zotero")
        self.index = Index(self.root / "cache" / "search.db")
        self.addCleanup(self.index.close)
        self.catalogue = Catalogue(Library(self.root / "Zotero", self.root / "cache"), self.index)
        self.catalogue.sync()
        self.pool = Pool(self.root / "cache" / "search.db")
        self.addCleanup(self.pool.close)
        self.store = db.open_store(self.root / "app.db", "k" * 64, False)
        self.mind = next(p.key for p in self.catalogue.all() if p.record["title"].startswith("MindAlign"))
        self.temporal = next(p.key for p in self.catalogue.all() if p.record["title"].startswith("Temporal"))
        self.pool.put_paper(self.mind, "s1", [
            work("W10", "Decoding inner speech with transformers", "We decode imagined speech from fMRI."),
            work("W11", "Rest EEG rhythms", "Alpha rhythms at rest."),
        ], [work("W20", "Inner speech decoding with fMRI, a follow-up", "fMRI and imagined speech again.", cited_by=50)])
        self.saved = ss.SavedSearches(self.store, self.catalogue, lambda: self.pool, set)


# -- saved searches ---------------------------------------------------------------------------

class SearchesTest(LibraryCase):
    def test_groups_combine(self) -> None:
        search = ss.clean({"name": "Inner", "groups": [
            {"name": "INNER", "mode": "any", "terms": ["inner speech", "imagined speech"]},
            {"name": "FMRI", "mode": "any", "terms": ["fmri"]},
            {"name": "NOT_EEG", "mode": "none", "terms": ["eeg"]},
        ]})
        keys, tally = self.saved.run_library(search)
        # MindAlign's full text mentions EEG; the Temporal paper's says inner
        # speech (and fMRI is in its title).
        self.assertEqual(keys, [self.temporal])
        self.assertEqual(tally["INNER"], 2)
        rows, total, tally = self.saved.run_missing(search)
        self.assertEqual([r["wid"] for r in rows], ["W20", "W10"])
        self.assertEqual(total, 2)
        self.assertEqual(tally["NOT_EEG"], 2)

    def test_at_least_and_query(self) -> None:
        search = ss.clean({"name": "Wide", "query": "decoding", "groups": [
            {"name": "A", "mode": "any", "terms": ["transformer"], "required": False},
            {"name": "B", "mode": "any", "terms": ["imagined"], "required": False},
            {"name": "TWO", "mode": "at_least", "n": 2, "of": ["A", "B"]},
        ]})
        rows, _, _ = self.saved.run_missing(search)
        self.assertEqual([r["wid"] for r in rows], ["W10"])
        keys, _ = self.saved.run_library(search)
        self.assertEqual(keys, [self.mind])

    def test_problems_say_where(self) -> None:
        with self.assertRaises(ss.SearchError) as caught:
            ss.clean({"name": "", "groups": [{"name": "bad name", "mode": "any", "terms": []},
                                             {"name": "X", "mode": "at_least", "n": 3, "of": ["Y"]}]})
        where = {p["where"] for p in caught.exception.problems}
        self.assertTrue({"name", "groups[0].name", "groups[0].terms", "groups[1].n", "groups[1].of"} <= where, where)
        with self.assertRaises(ss.SearchError):
            ss.clean({"name": "loop", "groups": [{"name": "A", "mode": "at_least", "n": 1, "of": ["B"]},
                                                  {"name": "B", "mode": "at_least", "n": 1, "of": ["A"]}]})

    def test_saved_and_found_by_name(self) -> None:
        one = self.saved.save({"name": "Inner", "query": "inner speech"}, "me")
        self.assertEqual(self.saved.find("inner")["id"], one["id"])
        with self.assertRaises(ss.SearchError):
            self.saved.save({"name": "INNER", "query": "x"}, "me")
        self.saved.save({"name": "Inner", "query": "imagined"}, "me", one["id"])
        self.assertEqual(self.saved.get(one["id"])["query"], "imagined")
        self.assertEqual(ss.keywords(self.saved.get(one["id"])), ["imagined"])

    def test_old_files_translate_without_running(self) -> None:
        source = '''
import os
def search():
    A = any_of("inner speech", "covert speech")
    B = combine_or(any_of("fmri"), any_of("bold", threshold=100))
    C = any_of("eeg")
    NOT_C = lambda h: not C(h)
    return [
        ("plain", A),
        ("both", combine_and(A, B, NOT_C)),
        ("wide", combine_and(B, at_least(1, A, C))),
        ("bad", lambda h: os.system("x")),
    ]
'''
        found, problems = ss.translate_legacy(source, "t")
        self.assertEqual([s["name"] for s in found], ["plain", "both", "wide"])
        self.assertEqual(len(problems), 1)
        both = {g["name"]: g for g in found[1]["groups"]}
        self.assertEqual(both["B"]["terms"], ["fmri", "bold"])
        self.assertEqual(both["NOT_C"]["mode"], "none")
        self.assertFalse(both["C"]["required"])
        for search in found:
            ss.clean(search)

    def test_the_real_old_files_all_translate(self) -> None:
        folder = Path.home() / "WORKSPACE/PYTHON/PaperReferenceManagerAddons/searches"
        if not folder.is_dir():
            self.skipTest("the old repo is not on this machine")
        count, problems = ss.import_legacy(self.saved, folder, "test")
        self.assertEqual(problems, [])
        self.assertGreater(count, 30)


# -- missing.xlsx ---------------------------------------------------------------------------

class MissingWorkbookTest(LibraryCase):
    def test_sheets(self) -> None:
        from openpyxl import load_workbook

        self.saved.save({"name": "Inner", "query": "inner speech"}, "me")
        data = xlsx.missing_workbook(self.pool, self.saved, {"W11"}, "https://proxy.example/{doi}", top=10)
        book = load_workbook(io.BytesIO(data))
        self.assertEqual(book.sheetnames, ["Top 10 by connections", "Top 10 newest", "Top 10 cited-by", "Top 1 authors", "Inner"])
        top = book["Top 10 by connections"]
        self.assertEqual([c.value for c in top[1]][:3], ["Connections", "Title", "Year"])
        titles = [row[1].value for row in top.iter_rows(min_row=2)]
        self.assertNotIn("Rest EEG rhythms", titles)
        self.assertEqual(len(titles), 2)
        self.assertEqual(book["Top 10 cited-by"]["B2"].value, "Inner speech decoding with fMRI, a follow-up")
        self.assertEqual(book["Top 10 by connections"]["H2"].hyperlink.target.startswith("https://openalex.org/W"), True)


# -- the research-log check ------------------------------------------------------------------

LOG = """# 03SEP2026

Naturalistic semantic mapping

[https://www.biorxiv.org/content/10.1101/2026.01.02.123456v1.full](https://www.biorxiv.org/content/10.1101/2026.01.02.123456v1.full)

&nbsp;

MindAlign: Decoding Inner Speech from fMRI Signals

https://arxiv.org/abs/2606.20696 doi 10.9999/preprint.1

&nbsp;

\tA note, not a paper

&nbsp;

# 04SEP2026

**Naturalistic semantic mapping**

https://direct.mit.edu/jocn/article/doi/10.1162/jocn_a_02087/118023/Title

&nbsp;
"""


class LogCheckTest(LibraryCase):
    def test_extract_and_check(self) -> None:
        papers, lines = logcheck.extract(LOG)
        self.assertEqual(len(papers), 3)
        self.assertEqual(papers[0]["doi"], "10.1101/2026.01.02.123456")
        self.assertEqual(papers[0]["date"], "03SEP2026")
        self.assertEqual(papers[2]["doi"], "10.1162/jocn_a_02087")
        result = logcheck.run(LOG, "log.md", self.catalogue.match)
        self.assertEqual(result["unique"], 2)
        by_title = {p["title"]: p for p in result["papers"]}
        semantic = by_title["Naturalistic semantic mapping"]
        self.assertEqual(semantic["mentions"], 2)
        self.assertEqual(semantic["found"], "")
        mind = by_title["MindAlign: Decoding Inner Speech from fMRI Signals"]
        # Its DOI is a preprint's; the title finds it.
        self.assertTrue(mind["recovered"])
        self.assertEqual(mind["key"], self.mind)
        self.assertEqual((result["missing"], result["recovered"]), (1, 1))
        self.assertIn("## Missing", result["report"])
        self.assertIn("## Found by title only", result["report"])

    def test_list_only(self) -> None:
        result = logcheck.run(LOG, "log.md", None)
        self.assertNotIn("missing", result)
        self.assertEqual(result["extracted"], 3)


# -- the crawl -------------------------------------------------------------------------------

class FakeClient:
    """OpenAlex for the crawl: works by id, their references, their citers."""

    def __init__(self) -> None:
        self.calls = 0
        self.works_by: dict[str, dict[str, Any]] = {}
        self.refs: dict[str, list[str]] = {}
        self.citers: dict[str, list[str]] = {}

    def work_with_refs(self, wid: str) -> tuple[dict[str, Any], list[str]]:
        self.calls += 1
        return self.works_by[wid], self.refs.get(wid, [])

    def works(self, wids: list[str]) -> list[dict[str, Any]]:
        self.calls += 1
        return [self.works_by[w] for w in wids if w in self.works_by]

    def citing_top(self, wid: str) -> list[dict[str, Any]]:
        self.calls += 1
        return [self.works_by[w] for w in self.citers.get(wid, [])]


class CrawlTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = cr.Cache(Path(directory.name))
        self.client = FakeClient()
        for wid, title in (("W2", "Inner speech decoding"), ("W3", "Covert speech fMRI decoding"), ("W4", "Cooking"),
                           ("W5", "Imagined speech and inner speech review")):
            self.client.works_by[wid] = work(wid, title)
        self.client.refs["W2"] = ["W3", "W4"]
        self.client.citers["W2"] = ["W5"]

    def run_crawl(self, **settings: Any) -> dict[str, Any]:
        seed = ("lib1", "W1", work("W1", "Inner speech in the scanner", "fMRI decoding"))
        crawl = cr.Crawl(cr.Settings(**settings), ["inner speech", "decoding", "fmri", "covert speech"], [seed],
                         lambda key: ([self.client.works_by["W2"]], []), self.client, self.cache,
                         lambda w: w.get("wid") == "W5")
        return crawl.run()

    def test_walks_both_ways_and_reports_novel(self) -> None:
        found = self.run_crawl(min_novel_hits=2)
        self.assertEqual(found["seeds"], 1)
        novel = {r["wid"]: r for r in found["novel_rows"]}
        # W5 is in the library; W4 matches nothing.
        self.assertEqual(set(novel), {"W2", "W3"})
        self.assertEqual(novel["W3"]["from"], "W2")
        self.assertEqual(novel["W3"]["how"], "cites")
        self.assertEqual(novel["W2"]["from_key"], "lib1")
        self.assertEqual(novel["W3"]["depth"], 2)
        self.assertGreater(found["api_used"], 0)

    def test_cache_makes_a_second_run_free(self) -> None:
        self.run_crawl()
        used = self.client.calls
        again = self.run_crawl()
        self.assertEqual(self.client.calls, used)
        self.assertEqual(again["api_used"], 0)

    def test_budget_and_depth(self) -> None:
        shallow = self.run_crawl(max_depth=1)
        self.assertEqual({r["wid"] for r in shallow["visited_rows"]}, {"W1", "W2"})
        self.assertEqual(self.client.calls, 0)
        broke = self.run_crawl(api_budget=0)
        self.assertEqual(broke["api_used"], 0)

    def test_hits_are_phrases_with_a_prefix(self) -> None:
        self.assertEqual(cr.hits_in("decoders of inner speeches", ["decod", "inner speech", "speech"]), 3)
        self.assertEqual(cr.hits_in("encoding", ["coding"]), 0)


# -- LLM summaries ---------------------------------------------------------------------------

class LlmTest(unittest.TestCase):
    def settings(self, **values: str) -> SimpleNamespace:
        base = {"provider": "", "anthropic_api_key": "", "openai_api_key": "", "gemini_api_key": "", "model": ""}
        base.update(values)
        return SimpleNamespace(**base)

    def test_choose(self) -> None:
        self.assertIsNone(llm.choose(self.settings()))
        choice = llm.choose(self.settings(openai_api_key="o", gemini_api_key="g"))
        self.assertEqual((choice.provider, choice.model), ("openai", "gpt-5.4-nano"))
        choice = llm.choose(self.settings(openai_api_key="o", anthropic_api_key="a"))
        self.assertEqual((choice.provider, choice.model), ("claude", "claude-opus-5-5"))
        self.assertIsNone(llm.choose(self.settings(provider="gemini", openai_api_key="o")))

    def test_each_provider_is_asked_its_own_way(self) -> None:
        sent: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        answers = {
            "claude": {"content": [{"type": "text", "text": "HASHTAGS: #a #b\nSUMMARY:\nIt works."}]},
            "openai": {"choices": [{"message": {"content": "HASHTAGS: #a\nSUMMARY:\nIt works."}}]},
            "gemini": {"candidates": [{"content": {"parts": [{"text": "SUMMARY: It works."}]}}]},
        }
        for provider in llm.PROVIDERS:
            def poster(url: str, headers: dict[str, str], body: bytes, provider: str = provider) -> tuple[int, dict[str, str], bytes]:
                sent.append((url, headers, json.loads(body)))
                return 200, {}, json.dumps(answers[provider]).encode()

            client = llm.Client(llm.Choice(provider, llm.DEFAULT_MODELS[provider], "KEY"), poster)
            self.assertEqual(llm.parse_answer(client.complete("sys", "user"))["summary"], "It works.")
        self.assertEqual(sent[0][1]["x-api-key"], "KEY")
        self.assertEqual(sent[0][2]["system"], "sys")
        self.assertEqual(sent[1][1]["authorization"], "Bearer KEY")
        self.assertIn("gemini-2.5-flash:generateContent", sent[2][0])
        self.assertNotIn("KEY", sent[2][0])

    def test_retries_then_refuses(self) -> None:
        tries = []

        def poster(url: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
            tries.append(1)
            if len(tries) < 3:
                return 529, {"retry-after": "1"}, b""
            return 400, {}, b'{"error": {"message": "bad model"}}'

        client = llm.Client(llm.Choice("claude", "x", "k"), poster)
        client.sleep = lambda seconds: None
        with self.assertRaises(llm.LlmError) as caught:
            client.complete("s", "u")
        self.assertIn("bad model", str(caught.exception))
        self.assertEqual(len(tries), 3)

    def test_prompt_files(self) -> None:
        system, user = llm.parse_prompt((ROOT / "config" / "llm-prompts" / "methods.txt").read_text())
        filled = llm.fill(user, "T", "10.1/x", "Methods", "the text {not a placeholder}")
        self.assertIn("Paper title: T", filled)
        self.assertIn("{not a placeholder}", filled)
        self.assertIsNone(llm.parse_prompt("no markers"))
        self.assertEqual(llm.parse_answer("just prose"), {"hashtags": "", "summary": "just prose"})

    def test_clip_keeps_both_ends(self) -> None:
        text = "A" * 500_000 + "Z" * 500_000
        clipped, cut = llm.clip(text, "openai")
        self.assertTrue(cut)
        self.assertTrue(clipped.startswith("A") and clipped.endswith("Z"))
        self.assertLess(len(clipped), 400_000)


class FakeModel:
    def __init__(self, choice: llm.Choice) -> None:
        self.choice = choice

    def complete(self, system: str, user: str) -> str:
        assert "MindAlign" in user
        return "HASHTAGS: #fMRI #InnerSpeech\nSUMMARY:\n**Study design.**\n- Imagined sentences.\n\n**Participants.**\n- Some."


class SummariesTest(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        settings = SimpleNamespace(provider="", anthropic_api_key="a", openai_api_key="", gemini_api_key="", model="")
        content = SimpleNamespace(files=SimpleNamespace(read=lambda key, name: {"sections": [
            {"key": "methods", "heading": "Methods", "text": "Participants imagined sentences."},
            {"key": "references", "heading": "References", "text": "[1] Someone."},
        ]}), oa_abstract=lambda key: "")
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.service = sm.Summaries(self.store, self.catalogue, content, ROOT / "config" / "llm-prompts",
                                    ROOT / "config" / "rollup-extra-columns.yaml", lambda: settings,
                                    lambda name, data: self.events.append((name, data)))
        self.service.client_factory = FakeModel

    def test_section_text(self) -> None:
        self.assertEqual(self.service.section_text(self.mind, "methods"), "Participants imagined sentences.")
        self.assertNotIn("Someone", self.service.section_text(self.mind, "all"))
        self.assertIn("transformer", self.service.section_text(self.mind, "abstract"))

    def test_queue_one_at_a_time_then_rollup(self) -> None:
        answer = self.service.request([self.mind, "nope"], ["methods"], False, "me")
        self.assertEqual(answer, {"queued": 1, "kept": 0, "unknown": 1})
        self.assertEqual(self.service.of_paper(self.mind)["methods"]["state"], "queued")
        self.service.start()
        self.addCleanup(self.service.stop)
        deadline = time.time() + 5
        while not self.service.get(self.mind, "methods") and time.time() < deadline:
            time.sleep(0.02)
        kept = self.service.get(self.mind, "methods")
        self.assertEqual(kept["hashtags"], "#fMRI #InnerSpeech")
        self.assertEqual(kept["provider"], "claude")
        self.assertEqual(self.service.request([self.mind], ["methods"], False, "me")["kept"], 1)
        rollup = self.service.rollup("methods")
        self.assertEqual(rollup["columns"], ["Study design", "Participants"])
        self.assertEqual(rollup["rows"][0]["parts"]["Participants"], "- Some.")
        self.assertEqual(rollup["hashtags"], [["#fmri", 1], ["#innerspeech", 1]])
        self.assertIn("fMRI task", rollup["extra"])
        self.assertIn(("summary", {"key": self.mind, "section": "methods", "state": "done", "error": ""}), self.events)

    def test_no_text_fails_that_one(self) -> None:
        with self.assertRaises(ValueError):
            self.service.summarize_one(self.mind, "future", "me")

    def test_old_summaries_come_in(self) -> None:
        folder = self.root / "summaries" / "methods"
        folder.mkdir(parents=True)
        doi = self.catalogue.get(self.mind).record["doi"]
        (folder / "x.md").write_text(f"# Methods — MindAlign\n\n**DOI:** [{doi}](https://doi.org/{doi})\n**Provider:** openai\n"
                                     "**Model:** gpt-4o\n\n**Hashtags:** #a #b\n\n## Summary\n\n**Study design.**\n- x\n")
        (folder / "y.md").write_text("**DOI:** [10.0/none](https://doi.org/10.0/none)\n\n## Summary\n\ntext\n")
        self.assertEqual(sm.import_legacy(self.service, self.root / "summaries", "me"), (1, 0, 1))
        self.assertEqual(self.service.get(self.mind, "methods")["model"], "gpt-4o")
        self.assertEqual(sm.import_legacy(self.service, self.root / "summaries", "me"), (0, 1, 1))

    def test_snippets(self) -> None:
        spec = {"keywords": ["fmri task"], "regex_re": [], "context_chars": 100, "max_snippets": 2}
        self.assertEqual(sm.keyword_hits("a subscanner, a scanner.", ["scanner"]), [(16, 23)])
        filler = "Nothing to see in this sentence at all. " * 6
        text = "First sentence here. The fMRI task was a block design. " + filler + "Another fMRI task appears. " + filler + "A third fMRI task."
        found = sm.snippets_of(text, spec)
        self.assertEqual(len(found), 2)
        self.assertIn("The fMRI task was a block design.", found[0])
        self.assertIn("Another fMRI task", found[1])


# -- the Google Sheets mirror ----------------------------------------------------------------

class FakeSheets:
    def __init__(self) -> None:
        self.grids: dict[str, list[list[Any]]] = {}
        self.tab = {"title": "List", "rows": 0, "cols": 0}
        self.calls: list[str] = []
        self.gone = False

    def create(self, title: str, tab: str) -> tuple[str, int]:
        self.calls.append("create " + title)
        self.grids["S1"] = []
        return "S1", 7

    def tabs(self, sid: str) -> dict[int, dict[str, Any]]:
        if self.gone:
            raise sheetsync.GoogleError(404, "gone")
        return {7: dict(self.tab)}

    def batch(self, sid: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        for request in requests:
            grid = (request.get("updateSheetProperties") or {}).get("properties", {}).get("gridProperties", {})
            if "rowCount" in grid:
                self.tab.update(rows=grid["rowCount"], cols=grid["columnCount"])
        return {}

    def read(self, sid: str, tab: str) -> list[list[Any]]:
        return json.loads(json.dumps(self.grids[sid]))

    def write(self, sid: str, tab: str, rows: list[list[Any]]) -> dict[str, Any]:
        self.calls.append("write")
        self.grids[sid] = rows
        return {}

    def share(self, sid: str, email: str) -> dict[str, Any]:
        return {}

    def move(self, sid: str, folder: str) -> dict[str, Any]:
        return {}


class SheetSyncTest(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        self.boards = BoardService(self.store, self.catalogue)
        record = boards.create_board(self.store, "Reading", "me")
        self.slug = record["slug"]
        boards.apply_ops(self.store, self.slug, [{"op": "add", "paper": self.mind}, {"op": "add", "paper": self.temporal}],
                         self.boards.ctx(), "me")
        self.cfg = SimpleNamespace(enabled=True, client_id="c", client_secret="s", refresh_token="r", quota_project="",
                                   default_mode="one-way", push_delay=5, poll_seconds=30, max_remove=25, share_with=[],
                                   folder_id="", title_prefix="Sort – ")
        self.google = FakeSheets()
        self.sync = sheetsync.SheetSync(self.boards, lambda: self.cfg, self.google)
        self.boards.listeners.append(self.sync.heard)

    def doc(self) -> dict[str, Any]:
        return boards.get_board(self.store, self.slug)["doc"]

    def test_one_way_pushes_the_list(self) -> None:
        self.sync.configure(self.slug, "one-way")
        self.sync.sync(self.slug, True)
        self.assertEqual(self.google.calls[:2], ["create Sort – Reading", "write"])
        grid = self.google.grids["S1"]
        self.assertEqual(grid[0][:8], ["Key", "#", "DOI", "Title", "Year", "Authors", "Journal", "Tags"])
        self.assertEqual(grid[1][0], self.mind)
        self.assertEqual(len(grid), 2 + 1 + sheetmirror.SPARE_ROWS)
        status = self.sync.status(self.slug)
        self.assertTrue(status["url"].endswith("/S1"))
        self.assertTrue(status["last_push"])
        # Nothing changed: no second write.
        self.sync.sync(self.slug, True)
        self.assertEqual(self.google.calls.count("write"), 1)

    def test_a_change_schedules_a_push(self) -> None:
        self.sync.configure(self.slug, "one-way")
        self.sync._due.clear()
        self.boards.changed(self.slug, 9, "me")
        self.assertIn(self.slug, self.sync._due)

    def test_two_way_reads_edits_back(self) -> None:
        self.sync.configure(self.slug, "two-way")
        self.sync.sync(self.slug, True)
        grid = self.google.grids["S1"]
        header = grid[0]
        grid[1][header.index("Tags")] = "great, fmri"
        grid[1][header.index("Notes")] = "read it"
        grid[1], grid[2] = grid[2], grid[1]
        self.sync.sync(self.slug, False)
        items = self.doc()["items"]
        self.assertEqual([i["key"] for i in items], [self.temporal, self.mind])
        mind = items[1]
        self.assertEqual(sorted(mind["tags"]), ["fmri", "great"])
        self.assertEqual(mind["fields"]["notes"], "read it")
        self.assertEqual(boards.get_board(self.store, self.slug)["updated_by"], sheetsync.BY)
        # The push after it writes the list back.
        self.assertEqual(self.google.calls.count("write"), 2)

    def test_too_many_removed_is_refused(self) -> None:
        self.cfg.max_remove = 1
        self.sync.configure(self.slug, "two-way")
        self.sync.sync(self.slug, True)
        grid = self.google.grids["S1"]
        self.google.grids["S1"] = [grid[0]]
        self.sync.sync(self.slug, False)
        self.assertEqual(len(self.doc()["items"]), 2)
        status = self.sync.status(self.slug)
        self.assertTrue(status["refused"])
        self.assertIn("max_remove", status["error"])

    def test_locked_waits(self) -> None:
        self.sync.configure(self.slug, "two-way")
        self.sync.sync(self.slug, True)
        boards.set_locked(self.store, self.slug, True, "me")
        self.google.grids["S1"][1][3] = "A new title"
        self.sync.sync(self.slug, False)
        self.assertIn("view-only", self.sync.status(self.slug)["note"])
        self.assertNotEqual(self.doc()["items"][0]["title"], "A new title")

    def test_rename_moves_the_mirror_and_a_gone_sheet_switches_off(self) -> None:
        self.sync.configure(self.slug, "one-way")
        self.sync.sync(self.slug, True)
        record = boards.rename_board(self.store, self.slug, "Renamed", "me")
        self.boards.changed(record["slug"], record["rev"], "me", renamed_from=self.slug)
        self.assertEqual(self.sync.state(record["slug"])["spreadsheet_id"], "S1")
        self.assertEqual(self.sync.state(self.slug), {"mode": "off"})
        self.google.gone = True
        self.sync.sync(record["slug"], True)
        self.assertEqual(self.sync.status(record["slug"])["mode"], "off")


# -- the routes --------------------------------------------------------------------------------

try:
    from app.tests.route_support import RoutesTestCase
except unittest.SkipTest:  # pragma: no cover -- without httpx2
    RoutesTestCase = None  # type: ignore[assignment,misc]

if RoutesTestCase is not None:

    class Phase7RoutesTest(RoutesTestCase):
        def test_searches_round_trip(self) -> None:
            headers = {"Authorization": f"Bearer {self.user_key}"}
            bad = self.client.post("/api/searches", json={"name": "x", "groups": [{"name": "1", "mode": "any", "terms": []}]}, headers=headers)
            self.assertEqual(bad.status_code, 400)
            self.assertTrue(bad.json()["problems"])
            made = self.client.post("/api/searches", json={"name": "Inner", "query": "inner speech"}, headers=headers)
            self.assertEqual(made.status_code, 201, made.text)
            sid = made.json()["search"]["id"]
            run = self.client.get("/api/searches/Inner/run?pool=both", headers=headers)
            self.assertEqual(run.status_code, 200, run.text)
            self.assertEqual(run.json()["missing_total"], 0)
            tried = self.client.post("/api/searches/try", json={"query": "speech", "groups": []}, headers=headers)
            self.assertEqual(tried.status_code, 200, tried.text)
            export = self.client.get(f"/api/searches/{sid}/export?format=md", headers=headers)
            self.assertEqual(export.status_code, 200)
            self.assertIn("# Inner", export.text)
            self.assertEqual(self.client.get(f"/api/searches/{sid}/export", headers=headers).headers["content-type"], xlsx.XLSX)
            gone = self.client.post(f"/api/searches/{sid}/delete", headers=headers)
            self.assertEqual(self.client.get("/api/searches", headers=headers).json()["searches"], [])
            back = self.client.post("/api/searches/restore", json={"search": gone.json()["search"]}, headers=headers)
            self.assertEqual(back.status_code, 200, back.text)
            self.assertEqual([s["id"] for s in self.client.get("/api/searches", headers=headers).json()["searches"]], [sid])

        def test_the_rest_answer(self) -> None:
            headers = {"Authorization": f"Bearer {self.user_key}"}
            self.assertEqual(self.client.get("/api/missing/export.xlsx", headers=headers).status_code, 200)
            check = self.client.post("/api/research-log/check", json={"text": LOG}, headers=headers)
            self.assertEqual(check.status_code, 200, check.text)
            self.assertEqual(check.json()["unique"], 2)
            status = self.client.get("/api/crawl", headers=headers)
            self.assertEqual(status.status_code, 200, status.text)
            self.assertFalse(status.json()["status"]["running"])
            self.assertEqual(self.client.post("/api/crawl", json={"search": "nope"}, headers=headers).status_code, 404)
            summaries = self.client.get("/api/summaries/status", headers=headers)
            self.assertEqual(summaries.status_code, 200, summaries.text)
            self.assertEqual(summaries.json()["provider"], "")
            self.assertEqual(self.client.post("/api/summaries", json={"keys": ["x"], "sections": ["methods"]}, headers=headers).status_code, 409)
            self.assertEqual(self.client.get("/api/summaries/rollup?section=methods", headers=headers).json()["rows"], [])
            slug = boards.create_board(self.store, "Reading", "me")["slug"]
            sheet = self.client.get(f"/api/lists/{slug}/sheet", headers=headers)
            self.assertEqual(sheet.status_code, 200, sheet.text)
            self.assertFalse(sheet.json()["sheet"]["available"])
            self.assertEqual(self.client.post(f"/api/lists/{slug}/sheet", json={"mode": "one-way"}, headers=headers).status_code, 409)
            self.assertEqual(self.client.get("/api/lists/nope/sheet", headers=headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
