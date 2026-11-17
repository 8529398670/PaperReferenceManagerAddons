"""GitHub / OSF / record enrichment: URL parsing, the method vocabulary's
false-positive guards, the caching rules (what is cached, what waits),
OCR repair tiers, and converting the old prma's caches. No network: a fake
fetch answers from a table."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.content import enrich
from app.content.enrich import Enricher, FetchResult, github_repo, methods_in, osf_guid, record_target


def ok(value: Any, headers: dict[str, str] | None = None) -> FetchResult:
    return FetchResult(200, headers or {}, json.dumps(value).encode("utf-8"))


def status(code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> FetchResult:
    return FetchResult(code, headers or {}, body)


class FakeFetch:
    """url -> FetchResult (or a list of them, served in order). Records every call."""

    def __init__(self, table: dict[str, Any]) -> None:
        self.table = table
        self.calls: list[tuple[str, dict[str, str], bytes | None]] = []

    def __call__(self, url: str, headers: dict[str, str] | None = None, data: bytes | None = None, method: str | None = None) -> FetchResult:
        self.calls.append((url, dict(headers or {}), data))
        answer = self.table.get(url)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if answer is None:
            return FetchResult(0, {}, b"", "no route in the fake")
        return answer

    def urls(self) -> list[str]:
        return [c[0] for c in self.calls]


def repo_meta(owner: str, repo: str, **extra: Any) -> dict[str, Any]:
    return {
        "full_name": f"{owner}/{repo}", "html_url": f"https://github.com/{owner}/{repo}", "description": "A toolbox",
        "stargazers_count": 12, "language": "Python", "topics": ["neuroscience"], "pushed_at": "2025-01-01T00:00:00Z",
        "archived": False, **extra,
    }


def readme(text: str) -> FetchResult:
    return ok({"content": base64.b64encode(text.encode("utf-8")).decode("ascii"), "encoding": "base64"})


GH = enrich.GITHUB_API


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "_enrich"
        self.keys = ["ghp_test", "osf_test"]
        self.now = [1_000_000.0]

    def enricher(self, table: dict[str, Any]) -> tuple[Enricher, FakeFetch]:
        fake = FakeFetch(table)
        e = Enricher(self.root, lambda: (self.keys[0], self.keys[1]), fetch=fake)
        e.clock = lambda: self.now[0]
        return e, fake


class TestGithubRepo(unittest.TestCase):
    def test_shapes(self) -> None:
        cases = {
            "https://github.com/ANTsX/ANTs": ("ANTsX", "ANTs"),
            "http://www.github.com/ANTsX/ANTs/": ("ANTsX", "ANTs"),
            "github.com/ANTsX/ANTs": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs.git": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs/tree/main/Scripts": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs/blob/master/README.md#install": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs).": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs,": ("ANTsX", "ANTs"),
            "https://github.com/ANTsX/ANTs?tab=readme": ("ANTsX", "ANTs"),
            "https://github.com/u/Surfa…": ("u", "Surfa"),
            "https://github.com/u/Surfa%E2%80%A6": ("u", "Surfa"),
            "https://github.com/nipy/nipype.git).": ("nipy", "nipype"),
            "https://github.com/a-b/my_repo.v2": ("a-b", "my_repo.v2"),
            "https://raw.githubusercontent.com/nipy/nipype/master/setup.py": ("nipy", "nipype"),
            "https://codeload.github.com/nipy/nipype/zip/master": ("nipy", "nipype"),
            "https://api.github.com/repos/nipy/nipype": ("nipy", "nipype"),
            "https://bold5000-dataset.github.io/website/": ("bold5000-dataset", "website"),
            "https://kelseyhan.github.io/": ("kelseyhan", "kelseyhan.github.io"),
            "https://kelseyhan.github.io/index.html": ("kelseyhan", "kelseyhan.github.io"),
        }
        for url, want in cases.items():
            with self.subTest(url=url):
                self.assertEqual(github_repo(url), want)

    def test_not_repos(self) -> None:
        for url in (
            "", "https://github.com", "https://github.com/", "https://github.com/ANTsX", "https://github.com/orgs/nipy/repositories",
            "https://gist.github.com/someone/abc123", "https://github.com/features/actions", "https://github.com/topics/fmri",
            "https://gitlab.com/a/b", "https://example.com/github.com/a/b", "https://github.com/search?q=x",
            "https://notgithub.com/a/b", "https://github.com/a/..",
        ):
            with self.subTest(url=url):
                self.assertIsNone(github_repo(url))


class TestOsfGuid(unittest.TestCase):
    def test_shapes(self) -> None:
        cases = {
            "https://osf.io/crwz7/": "crwz7",
            "osf.io/crwz7": "crwz7",
            "https://www.osf.io/CRWZ7": "crwz7",
            "https://osf.io/crwz7/wiki/home/": "crwz7",
            "https://osf.io/crwz7/files/osfstorage": "crwz7",
            "https://osf.io/crwz7/overview).": "crwz7",
            "https://osf.io/crwz7/?view_only=abc123": "crwz7",
            "https://osf.io/project/crwz7/": "crwz7",
            "https://osf.io/download/abcd5/": "abcd5",
            "https://osf.io/preprints/psyarxiv/abcd5_v2": "abcd5",
            "https://doi.org/10.17605/OSF.IO/CRWZ7": "crwz7",
            "https://dx.doi.org/10.17605/osf.io/crwz7": "crwz7",
        }
        for url, want in cases.items():
            with self.subTest(url=url):
                self.assertEqual(osf_guid(url), want)

    def test_not_guids(self) -> None:
        for url in ("https://osf.io/", "https://osf.io/dashboard", "https://osf.io/search/", "https://osf.io/abcdefgh/",
                    "https://doi.org/10.5281/zenodo.123", "https://github.com/a/b", "https://osf.io/wiki/"):
            with self.subTest(url=url):
                self.assertIsNone(osf_guid(url))


class TestRecordTarget(unittest.TestCase):
    def test_targets(self) -> None:
        cases = {
            "https://zenodo.org/records/1234567": "zenodo:1234567",
            "https://zenodo.org/record/1234567#.Xyz": "zenodo:1234567",
            "https://doi.org/10.5281/zenodo.1234567": "zenodo:1234567",
            "https://figshare.com/articles/dataset/My_data/7654321": "figshare:7654321",
            "https://figshare.com/articles/7654321": "figshare:7654321",
            "https://doi.org/10.6084/m9.figshare.7654321.v2": "figshare:7654321",
            "https://openneuro.org/datasets/ds003020": "openneuro:ds003020",
            "https://openneuro.org/datasets/ds003020/versions/1.0.0).": "openneuro:ds003020",
            "https://doi.org/10.18112/openneuro.ds002685.v1.0.1": "openneuro:ds002685",
            "https://osf.io/crwz7/": "osf:crwz7",
            "https://doi.org/10.17605/OSF.IO/CRWZ7": "osf:crwz7",
            "https://neurovault.org/collections/1234/": "page:https://neurovault.org/collections/1234/",
            "https://datadryad.org/stash/dataset/doi:10.5061/dryad.abc#x": "page:https://datadryad.org/stash/dataset/doi:10.5061/dryad.abc",
            "physionet.org/content/eegmmidb/1.0.0/": "page:https://physionet.org/content/eegmmidb/1.0.0/",
        }
        for url, want in cases.items():
            with self.subTest(url=url):
                self.assertEqual(record_target(url), want)

    def test_not_describable(self) -> None:
        for url in ("", "ftp://example.org/x", "mailto:a@b.org", "https://zenodo.org/search?q=fmri", "https://openneuro.org/",
                    "https://osf.io/dashboard", "not a url"):
            with self.subTest(url=url):
                self.assertIsNone(record_target(url))


class TestMethods(unittest.TestCase):
    def test_finds(self) -> None:
        self.assertEqual(methods_in("Preprocessed with fMRIPrep; rs-fMRI and EEG data"), ["fMRI", "EEG"])
        self.assertEqual(methods_in("topics: eeg meg fnirs"), ["EEG", "fNIRS", "MEG"])
        self.assertEqual(methods_in("Positron emission tomography and PET/MR"), ["PET"])
        self.assertEqual(methods_in("functional magnetic resonance imaging"), ["fMRI"])
        self.assertEqual(methods_in("electrocorticography grids (ECoG)"), ["ECoG"])
        self.assertEqual(methods_in("surface electromyography, sEMG"), ["EMG"])
        self.assertEqual(methods_in("load eeg_data.npy"), ["EEG"])
        self.assertEqual(methods_in("MNE-Python: MEG and EEG analysis"), ["EEG", "MEG"])

    def test_false_positives(self) -> None:
        for text in (
            "my pet project", "a dataset of pet images", "Pets and petting", "Thanks to Meg for the figures",
            "SEMGroup and AEMG are not EMG", "the EEGs-like codec", "datasets and petabytes", "MRI only, structural",
            "PETER wrote this", "omega", "", "fmriprepare",
        ):
            with self.subTest(text=text):
                found = methods_in(text)
                if text == "SEMGroup and AEMG are not EMG":
                    self.assertEqual(found, ["EMG"])  # only the whole word at the end
                else:
                    self.assertEqual(found, [])


class TestRepairMatch(unittest.TestCase):
    names = ["A-SIMPLE-TO-START", "Surface_projection", "braindecode", "braindecode.github.io", "neuro_toolbox", "other"]

    def test_tiers(self) -> None:
        self.assertEqual(enrich.best_repo_match("ASIMPLE-TOSTART", self.names), ("A-SIMPLE-TO-START", "exact", 1.0))
        self.assertEqual(enrich.best_repo_match("Surfa", self.names), ("Surface_projection", "prefix", 0.97))
        self.assertEqual(enrich.best_repo_match("brainde", self.names), ("braindecode", "prefix", 0.92))
        best = enrich.best_repo_match("neuro_toolbix", self.names)
        self.assertEqual(best[:2], ("neuro_toolbox", "fuzzy"))
        self.assertGreaterEqual(best[2], 0.9)
        self.assertIsNone(enrich.best_repo_match("completely-different", self.names))
        self.assertIsNone(enrich.best_repo_match("ab", self.names))


class TestGithubStep(Base):
    def test_fetch_and_cache(self) -> None:
        e, fake = self.enricher({
            f"{GH}/repos/nipy/nipype": ok(repo_meta("nipy", "nipype")),
            f"{GH}/repos/nipy/nipype/readme": readme("# nipype\nWorkflows for fMRI and EEG pipelines."),
        })
        self.assertIsNone(e.github("nipy", "nipype"))
        self.assertEqual(e.step([("github", "nipy/nipype")]), "github nipy/nipype")
        rec = e.github("NIPY", "Nipype")  # case-insensitive
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["methods"], ["fMRI", "EEG"])
        self.assertEqual(rec["stars"], 12)
        self.assertEqual(rec["updated"], "2025-01-01T00:00:00Z")
        self.assertNotIn("readme", rec)
        self.assertGreater(rec["readme_chars"], 10)
        self.assertIn("fMRI", e.readme("nipy", "nipype"))
        self.assertEqual(fake.calls[0][1]["Authorization"], "Bearer ghp_test")
        # Cached: nothing left to do, no new request.
        self.assertIsNone(e.step([("github", "nipy/nipype")]))
        self.assertEqual(len(fake.calls), 2)
        # The files: one JSON + the README, no temp files left behind.
        names = sorted(p.name for p in (self.root / "github").iterdir())
        self.assertEqual(len(names), 2)
        self.assertTrue(any(n.endswith(".readme.md") for n in names))

    def test_404_cached_500_not(self) -> None:
        e, fake = self.enricher({
            f"{GH}/repos/a/gone": status(404),
            f"{GH}/repos/b/flaky": [status(502), ok(repo_meta("b", "flaky")), ],
            f"{GH}/repos/b/flaky/readme": status(404),
            f"{GH}/users/a/repos?per_page=100&sort=updated&page=1": ok([]),
        })
        e.step([("github", "a/gone")])
        self.assertEqual(e.github("a", "gone")["status"], "not_found")
        out = e.step([("github", "b/flaky")])
        self.assertIn("will retry", out)
        self.assertIsNone(e.github("b", "flaky"))
        # Backed off: the next step skips it (and the 404's repair goes instead).
        self.assertEqual(e.step([("github", "b/flaky")]), None)
        self.now[0] += enrich.BACKOFF_FIRST + 1
        self.assertEqual(e.step([("github", "b/flaky")]), "github b/flaky")
        rec = e.github("b", "flaky")
        self.assertEqual((rec["status"], rec["readme_chars"], rec["methods"]), ("ok", 0, []))

    def test_backoff_doubles_and_moves_on(self) -> None:
        e, fake = self.enricher({
            f"{GH}/repos/b/down": status(503),
            f"{GH}/repos/c/fine": ok(repo_meta("c", "fine")),
            f"{GH}/repos/c/fine/readme": status(404),
        })
        wanted = [("github", "b/down"), ("github", "c/fine")]
        self.assertIn("b/down", e.step(wanted))
        self.assertEqual(e.step(wanted), "github c/fine")
        self.assertIsNone(e.step(wanted))
        self.now[0] += enrich.BACKOFF_FIRST + 1
        self.assertIn("will retry", e.step(wanted))
        self.now[0] += enrich.BACKOFF_FIRST + 1  # second failure waits twice as long
        self.assertIsNone(e.step(wanted))
        self.now[0] += enrich.BACKOFF_FIRST
        self.assertIn("will retry", e.step(wanted))

    def test_network_error_and_readme_failure_not_cached(self) -> None:
        e, fake = self.enricher({
            f"{GH}/repos/a/r": ok(repo_meta("a", "r")),
            f"{GH}/repos/a/r/readme": [status(500), readme("EEG")],
        })
        self.assertIn("will retry", e.step([("github", "a/r")]))
        self.assertIsNone(e.github("a", "r"))
        self.now[0] += enrich.BACKOFF_FIRST + 1
        e.step([("github", "a/r")])
        self.assertEqual(e.github("a", "r")["methods"], ["EEG"])
        e2, _ = self.enricher({})  # no routes at all: status 0
        self.assertIn("will retry", e2.step([("github", "x/y")]))
        self.assertIsNone(e2.github("x", "y"))

    def test_rate_limit_pauses_github(self) -> None:
        reset = str(int(self.now[0] + 600))
        e, fake = self.enricher({
            f"{GH}/repos/a/one": status(403, b'{"message":"API rate limit exceeded"}', {"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset}),
            f"{GH}/repos/a/two": ok(repo_meta("a", "two")),
            f"{GH}/repos/a/two/readme": status(404),
            f"{GH}/repos/a/one/readme": status(404),
            "https://example.org/x": FetchResult(200, {"content-type": "text/html"}, b"<title>X</title>"),
        })
        wanted = [("github", "a/one"), ("github", "a/two"), ("record", "page:https://example.org/x")]
        self.assertIn("rate limited", e.step(wanted))
        self.assertIsNone(e.github("a", "one"))
        # Every GitHub item waits; other kinds go on.
        self.assertEqual(e.step(wanted), "record page:https://example.org/x")
        self.assertEqual(len([u for u in fake.urls() if u.startswith(GH)]), 1)
        self.now[0] += 602
        fake.table[f"{GH}/repos/a/one"] = ok(repo_meta("a", "one"))
        self.assertEqual(e.step(wanted), "github a/one")

    def test_remaining_zero_on_success_pauses_after(self) -> None:
        reset = str(int(self.now[0] + 300))
        e, fake = self.enricher({
            f"{GH}/repos/a/one": ok(repo_meta("a", "one"), {"x-ratelimit-remaining": "1", "x-ratelimit-reset": reset}),
            f"{GH}/repos/a/one/readme": FetchResult(404, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset}),
            f"{GH}/repos/a/two": ok(repo_meta("a", "two")),
        })
        self.assertEqual(e.step([("github", "a/one"), ("github", "a/two")]), "github a/one")
        self.assertIsNone(e.step([("github", "a/two")]))

    def test_no_token_skips(self) -> None:
        self.keys[0] = ""
        self.keys[1] = ""
        e, fake = self.enricher({f"{GH}/repos/a/b": ok(repo_meta("a", "b"))})
        self.assertIsNone(e.step([("github", "a/b"), ("osf", "crwz7")]))
        self.assertEqual(fake.calls, [])
        self.assertIsNone(e.github("a", "b"))
        # The key arrives later (read live): it goes.
        self.keys[0] = "ghp_new"
        fake.table[f"{GH}/repos/a/b/readme"] = status(404)
        self.assertEqual(e.step([("github", "a/b")]), "github a/b")
        self.assertEqual(fake.calls[0][1]["Authorization"], "Bearer ghp_new")

    def test_bad_key_waits(self) -> None:
        e, fake = self.enricher({f"{GH}/repos/a/b": status(401)})
        self.assertIn("key refused", e.step([("github", "a/b")]))
        self.assertIsNone(e.github("a", "b"))
        self.assertIsNone(e.step([("github", "a/b"), ("github", "c/d")]))
        self.assertEqual(len(fake.calls), 1)

    def test_repair_tiers(self) -> None:
        listing = ok([{"name": n} for n in ("A-SIMPLE-TO-START", "Surface_projection", "neuro_toolbox", "unrelated")])
        table: dict[str, Any] = {f"{GH}/users/lab/repos?per_page=100&sort=updated&page=1": listing}
        for bad in ("ASIMPLE-TOSTART", "Surfa", "neuro_toolbix", "zzzzzzzz"):
            table[f"{GH}/repos/lab/{bad}"] = status(404)
        for good in ("A-SIMPLE-TO-START", "Surface_projection", "neuro_toolbox"):
            table[f"{GH}/repos/lab/{good}"] = ok(repo_meta("lab", good))
            table[f"{GH}/repos/lab/{good}/readme"] = readme("fMRI")
        e, fake = self.enricher(table)
        wanted = [("github", f"lab/{b}") for b in ("ASIMPLE-TOSTART", "Surfa", "neuro_toolbix", "zzzzzzzz")]
        done = []
        while (out := e.step(wanted)) is not None:
            done.append(out)
            self.assertLess(len(done), 20)
        self.assertIn("repair lab/Surfa", done)
        self.assertIn("github lab/Surface_projection (repaired)", done)
        fix = e.repair("lab", "ASIMPLE-TOSTART")
        self.assertEqual((fix["tier"], fix["confidence"], fix["url"]), ("exact", 1.0, "https://github.com/lab/A-SIMPLE-TO-START"))
        self.assertEqual(fix["original"], "https://github.com/lab/ASIMPLE-TOSTART")
        self.assertEqual(e.repair("lab", "Surfa")["tier"], "prefix")
        self.assertEqual(e.repair("lab", "neuro_toolbix")["tier"], "fuzzy")
        self.assertEqual(e.repair("lab", "zzzzzzzz")["tier"], "none")
        self.assertEqual(e.github("lab", "Surface_projection")["methods"], ["fMRI"])
        self.assertEqual(e.effective_repo("lab", "Surfa"), ("lab", "Surface_projection"))
        # The owner was listed once for all four.
        self.assertEqual(sum(1 for u in fake.urls() if "/users/lab/repos" in u), 1)
        self.assertIsNone(e.repair("lab", "never-tried"))

    def test_repair_owner_gone_and_transient(self) -> None:
        e, fake = self.enricher({
            f"{GH}/repos/ghost/x": status(404),
            f"{GH}/users/ghost/repos?per_page=100&sort=updated&page=1": [status(500), status(404)],
        })
        e.step([("github", "ghost/x")])
        self.assertIn("will retry", e.step([("github", "ghost/x")]))
        self.assertIsNone(e.repair("ghost", "x"))
        self.now[0] += enrich.BACKOFF_FIRST + 1
        self.assertEqual(e.step([("github", "ghost/x")]), "repair ghost/x")
        self.assertEqual(e.repair("ghost", "x")["tier"], "none")
        self.assertFalse(e.repair("ghost", "x")["owner_found"])


class TestOsfStep(Base):
    def test_node_with_wiki(self) -> None:
        api = enrich.OSF_API
        e, fake = self.enricher({
            f"{api}/guids/crwz7/": ok({"data": {"type": "nodes", "attributes": {"title": "Decoder &amp; meaning", "description": "Data", "category": "project", "tags": ["language"]}}}),
            f"{api}/nodes/crwz7/wikis/": ok({"data": [{"id": "w1", "attributes": {"name": "Other"}}, {"id": "w2", "attributes": {"name": "home"}, "links": {"download": "https://osf.io/wiki/w2/content"}}]}),
            "https://osf.io/wiki/w2/content": FetchResult(200, {"content-type": "text/markdown; charset=utf-8"}, "We used fMRI and MEG.".encode()),
        })
        self.assertEqual(e.step([("osf", "CRWZ7")]), "osf crwz7")
        rec = e.osf("crwz7")
        self.assertEqual((rec["status"], rec["title"], rec["category"]), ("ok", "Decoder & meaning", "project"))
        self.assertEqual(rec["methods"], ["fMRI", "MEG"])
        self.assertEqual(e.wiki("crwz7"), "We used fMRI and MEG.")
        self.assertEqual(fake.calls[0][1]["Authorization"], "Bearer osf_test")

    def test_preprint_404_403(self) -> None:
        api = enrich.OSF_API
        e, fake = self.enricher({
            f"{api}/guids/pre01/": ok({"data": {"type": "preprints", "attributes": {"title": "An EEG preprint", "description": ""}}}),
            f"{api}/guids/gone1/": status(410),
            f"{api}/guids/priv1/": status(403),
            f"{api}/guids/busy1/": status(429, headers={"retry-after": "30"}),
        })
        for guid in ("pre01", "gone1", "priv1", "busy1"):
            e.step([("osf", guid)])
        self.assertEqual(e.osf("pre01")["methods"], ["EEG"])
        self.assertEqual(e.osf("gone1")["status"], "not_found")
        self.assertEqual(e.osf("priv1")["status"], "forbidden")
        self.assertIsNone(e.osf("busy1"))
        self.assertEqual(len(fake.calls), 4)  # the preprint has no wiki to ask for
        self.now[0] += 31
        fake.table[f"{api}/guids/busy1/"] = status(404)
        self.assertEqual(e.step([("osf", "busy1")]), "osf busy1")


class TestRecordStep(Base):
    def test_archives(self) -> None:
        e, fake = self.enricher({
            "https://zenodo.org/api/records/123": ok({"metadata": {"title": "Code and data", "description": "<p>Scripts for the <b>EEG</b> study.</p>"}}),
            "https://api.figshare.com/v2/articles/77": ok({"title": "Figures", "description": "All figures", "url_public_html": "https://figshare.com/articles/x/77"}),
            "https://openneuro.org/crn/graphql": [
                ok({"data": {"dataset": {"draft": {"description": {"Name": "Story listening"}, "readme": "## Story listening\n\nSubjects [listened](http://x) to *stories*."}}}}),
                ok({"errors": [{"message": "Dataset ds999999 does not exist."}], "data": {"dataset": None}}),
            ],
            f"{enrich.OSF_API}/guids/crwz7/": ok({"data": {"attributes": {"title": "Universal decoder", "description": "Sentences"}}}),
            "https://neurovault.org/collections/1/": FetchResult(200, {"content-type": "text/html; charset=utf-8"},
                b'<html><head><title>NeuroVault: Faces</title><meta content="Face maps" name="description"></head></html>'),
            "https://example.org/missing": FetchResult(200, {"content-type": "text/html"}, b"<title>Page Not Found</title>"),
            "https://example.org/osf": FetchResult(200, {"content-type": "text/html"}, b"<title>OSF</title>"),
            "https://example.org/dead": status(404),
            "https://example.org/teapot": status(403),
        })
        targets = ["zenodo:123", "figshare:77", "openneuro:ds003020", "openneuro:ds999999", "osf:crwz7", "page:https://neurovault.org/collections/1/",
                   "page:https://example.org/missing", "page:https://example.org/osf", "page:https://example.org/dead", "page:https://example.org/teapot"]
        while e.step([("record", t) for t in targets]):
            pass
        self.assertEqual(e.record("zenodo:123")["description"], "Scripts for the EEG study.")
        self.assertEqual(e.record("zenodo:123")["url"], "https://zenodo.org/records/123")
        self.assertEqual(e.record("figshare:77")["title"], "Figures")
        on = e.record("openneuro:ds003020")
        self.assertEqual((on["title"], on["description"]), ("Story listening", "Subjects listened to stories."))
        self.assertEqual(e.record("openneuro:ds999999")["status"], "not_found")
        self.assertEqual(e.record("osf:crwz7")["title"], "Universal decoder")
        nv = e.record("page:https://neurovault.org/collections/1/")
        self.assertEqual((nv["title"], nv["description"]), ("NeuroVault: Faces", "Face maps"))
        self.assertEqual(e.record("page:https://example.org/missing")["status"], "not_found")
        self.assertEqual((e.record("page:https://example.org/osf")["status"], e.record("page:https://example.org/osf")["title"]), ("ok", ""))
        self.assertEqual(e.record("page:https://example.org/dead")["status"], "not_found")
        self.assertEqual(e.record("page:https://example.org/teapot")["status"], "http_403")
        # Records need no key.
        self.keys[:] = ["", ""]
        e2, fake2 = self.enricher({"https://zenodo.org/api/records/9": ok({"metadata": {"title": "T"}})})
        self.assertEqual(e2.step([("record", "zenodo:9")]), "record zenodo:9")

    def test_transient_records_wait_per_host(self) -> None:
        e, fake = self.enricher({
            "https://zenodo.org/api/records/1": status(503),
            "https://zenodo.org/api/records/2": ok({"metadata": {"title": "Two"}}),
            "https://openneuro.org/crn/graphql": ok({"errors": [{"message": "fetch failed"}]}),
            "https://example.org/a": FetchResult(200, {"content-type": "text/html"}, b"<title>A page</title>"),
        })
        wanted = [("record", "zenodo:1"), ("record", "zenodo:2"), ("record", "openneuro:ds000001"), ("record", "page:https://example.org/a")]
        self.assertIn("will retry", e.step(wanted))
        self.assertIn("openneuro", e.step(wanted))  # zenodo:2 waits with its host
        self.assertIsNone(e.record("openneuro:ds000001"))
        self.assertEqual(e.step(wanted), "record page:https://example.org/a")
        self.assertIsNone(e.step(wanted))
        self.now[0] += enrich.BACKOFF_FIRST + 1
        fake.table["https://zenodo.org/api/records/1"] = status(404)
        self.assertEqual(e.step(wanted), "record zenodo:1")
        self.assertEqual(e.step(wanted), "record zenodo:2")


class TestCacheReaders(Base):
    def test_mtime_invalidation(self) -> None:
        e, _ = self.enricher({})
        e2, _ = self.enricher({})  # a second reader on the same folder
        path = e._record_path("zenodo:5")
        enrich._write_json(path, {"status": "ok", "title": "One"})
        self.assertEqual(e2.record("zenodo:5")["title"], "One")
        import os
        enrich._write_json(path, {"status": "ok", "title": "Two"})
        os.utime(path, ns=(path.stat().st_mtime_ns + 1_000_000, path.stat().st_mtime_ns + 1_000_000))
        self.assertEqual(e2.record("zenodo:5")["title"], "Two")
        path.unlink()
        self.assertIsNone(e2.record("zenodo:5"))


class TestSeedLegacy(Base):
    def make_legacy(self) -> Path:
        legacy = Path(self.tmp.name) / "legacy"
        files = {
            "github/ANTsX__ANTs.json": {
                "owner": "ANTsX", "repo": "ANTs", "url": "https://github.com/ANTsX/ANTs", "fetched_at": "2026-07-01T14:41:55+00:00",
                "status": "ok", "full_name": "ANTsX/ANTs", "description": "Advanced Normalization Tools", "topics": ["neuroimaging"],
                "language": "C++", "stars": 1480, "homepage": "", "pushed_at": "2026-07-01T00:04:25Z", "archived": False,
                "readme": "ANTs registers fMRI and PET images.", "readme_status": "ok",
            },
            "github/lab__skil_.json": {
                "owner": "lab", "repo": "skil_", "url": "https://github.com/lab/skil_", "fetched_at": "2026-07-01T14:46:20+00:00",
                "status": "not_found", "readme": "", "readme_status": "skip",
                "resolve": {"matched": True, "repo": "skil_at_school", "url": "https://github.com/lab/skil_at_school", "score": 97.0, "method": "prefix", "at": "2026-07-01T14:47:50+00:00"},
            },
            "github/lab__nothing.json": {
                "owner": "lab", "repo": "nothing", "url": "https://github.com/lab/nothing", "fetched_at": "x", "status": "not_found",
                "readme": "", "readme_status": "skip", "resolve": {"matched": False, "at": "2026-07-01T14:47:50+00:00"},
            },
            "github/lab__flaky.json": {"owner": "lab", "repo": "flaky", "status": "ok", "readme": "", "readme_status": "error"},
            "github/lab__err.json": {"owner": "lab", "repo": "err", "status": "http_502", "readme": "", "readme_status": "skip"},
            "osf/284wc.json": {
                "guid": "284wc", "url": "https://osf.io/284wc/", "fetched_at": "2026-07-01T14:48:14+00:00", "status": "ok", "type": "preprints",
                "title": "Phantom vision", "description": "Aphantasia and illusions.", "category": "", "tags": [], "date_created": "2024",
                "date_modified": "2025-08-29", "public": True, "readme": "", "readme_status": "na",
            },
            "osf/crwz7.json": {
                "guid": "crwz7", "status": "ok", "type": "nodes", "title": "Decoder", "description": "", "category": "project",
                "tags": [], "readme": "Recorded with MEG.", "readme_status": "ok",
            },
            "osf/priv1.json": {"guid": "priv1", "status": "forbidden", "readme": "", "readme_status": "skip"},
            "datasets/aaa.json": {"url": "https://openneuro.org/datasets/ds003020", "title": "Story data", "via": "openneuro graphql", "http": 200, "fetched_at": "2026-07-01"},
            "datasets/bbb.json": {"url": "https://example.org/dead", "title": "", "via": "page title", "http": 404, "fetched_at": "2026-07-01"},
        }
        for name, value in files.items():
            path = legacy / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
        return legacy

    def test_seed(self) -> None:
        legacy = self.make_legacy()
        e, fake = self.enricher({})
        counts = e.seed_legacy(legacy)
        self.assertEqual(counts, {"github": 3, "repairs": 2, "osf": 3, "records": 2, "skipped": 2})
        ants = e.github("antsx", "ants")
        self.assertEqual((ants["status"], ants["stars"], ants["updated"], ants["methods"]), ("ok", 1480, "2026-07-01T00:04:25Z", ["fMRI", "PET"]))
        self.assertEqual(e.readme("ANTsX", "ANTs"), "ANTs registers fMRI and PET images.")
        self.assertEqual(e.github("lab", "skil_")["status"], "not_found")
        fix = e.repair("lab", "skil_")
        self.assertEqual((fix["tier"], fix["confidence"], fix["repo"]), ("prefix", 0.97, "skil_at_school"))
        self.assertEqual(e.repair("lab", "nothing")["tier"], "none")
        self.assertIsNone(e.github("lab", "flaky"))
        self.assertIsNone(e.github("lab", "err"))
        self.assertEqual(e.osf("crwz7")["methods"], ["MEG"])
        self.assertEqual(e.wiki("crwz7"), "Recorded with MEG.")
        self.assertEqual(e.osf("priv1")["status"], "forbidden")
        self.assertEqual(e.record("openneuro:ds003020")["title"], "Story data")
        self.assertEqual(e.record("page:https://example.org/dead")["status"], "not_found")
        # Once: a second run converts nothing.
        again = e.seed_legacy(legacy)
        self.assertEqual((again["github"], again["repairs"], again["osf"], again["records"]), (0, 0, 0, 0))
        # Seeded items are not refetched; the flaky one and the repaired repo are.
        wanted = [("github", "ANTsX/ANTs"), ("github", "lab/skil_"), ("github", "lab/flaky")]
        fake.table[f"{GH}/repos/lab/skil_at_school"] = ok(repo_meta("lab", "skil_at_school"))
        fake.table[f"{GH}/repos/lab/skil_at_school/readme"] = status(404)
        fake.table[f"{GH}/repos/lab/flaky"] = ok(repo_meta("lab", "flaky"))
        fake.table[f"{GH}/repos/lab/flaky/readme"] = status(404)
        done = []
        while (out := e.step(wanted)) is not None:
            done.append(out)
        self.assertEqual(done, ["github lab/skil_at_school (repaired)", "github lab/flaky"])

    def test_missing_folders(self) -> None:
        e, _ = self.enricher({})
        self.assertEqual(e.seed_legacy(Path(self.tmp.name) / "nowhere"), {"github": 0, "repairs": 0, "osf": 0, "records": 0, "skipped": 0})


if __name__ == "__main__":
    unittest.main()
