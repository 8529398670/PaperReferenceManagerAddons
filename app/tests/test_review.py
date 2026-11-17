"""The review screener (app/review/): its rules as data (load, validation,
signature), the screening and extraction, the service (save, reset,
overrides, dataset consensus), the content queue's review stage (only
candidates, redone when the rules change, kept per setup), and the admins'
routes and tools for setups."""
from __future__ import annotations

import copy
import importlib.util

import tempfile
import unittest
from pathlib import Path

from app.content import store as st
from app.core import db
from app.review import rules as R
from app.review import screen
from app.review.service import ReviewService
from app.tests.test_content import ROOT, ContentTest

DEFAULTS = ROOT / "config" / "review.yaml"
OLD_REVIEW = Path.home() / "WORKSPACE/PYTHON/PaperReferenceManagerAddons/src/review"

DECODER = """
We propose BrainFormer, a transformer encoder that decodes inner speech from fMRI.
## Methods
Functional MRI data were acquired on a 3T Siemens Prisma scanner. The BOLD signal was recorded with
TR = 2000 ms, TE = 30 ms, flip angle = 90 degrees and voxel size 2 x 2 x 2 mm. A total of 300 volumes per run.
Data were preprocessed with fMRIPrep and smoothed with a 6 mm FWHM kernel; the HRF was modelled per voxel.
Our model consists of 12 transformer layers with 8 attention heads and multi-head self-attention over voxel
tokens, followed by cross-attention to the stimulus embedding. The transformer encoder uses positional encoding.
We decode imagined speech and inner speech from the BOLD responses. The hidden dimension is 768.
We trained with AdamW, learning rate 1e-4, batch size 32, for 100 epochs. Each voxel time series was z-scored.
fMRI, fMRI, fMRI, BOLD, voxel, repetition time, echo-planar imaging, cortical surface, MNI space.
Participants also took part in the Natural Scenes Dataset (NSD) collection; NSD was acquired with TR = 1.6 s.
""" * 2

EEG = """
We record EEG with 64 electrodes and a MEG system. The EEG signal and MEG signal were filtered; electrode impedance
below 5 kOhm. EEG EEG EEG MEG MEG electrode electrode. We mention fMRI once in related work.
We propose a transformer encoder with multi-head self-attention to decode imagined speech.
"""


def defaults() -> dict:
    return R.read_yaml(DEFAULTS)


class RulesTest(unittest.TestCase):
    def test_defaults_load_and_sign(self) -> None:
        rules = R.load(defaults())
        self.assertEqual(len(rules.fields), 52)
        self.assertEqual(rules.signature, R.load(defaults()).signature)
        changed = defaults()
        changed["thresholds"]["full"]["fmri_full_min"]["value"] = 9
        self.assertNotEqual(R.load(changed).signature, rules.signature)

    def test_a_bad_pattern_is_named_by_where_it_is(self) -> None:
        data = defaults()
        data["vocab"]["attn_built"]["patterns"][2] = r"\bcross-?(attention"
        tr = next(f for f in data["extraction"]["fields"] if f["name"] == "TR")
        tr["patterns"].append("<<NOPE>>")
        with self.assertRaises(R.RulesError) as caught:
            R.load(data)
        paths = [p["path"] for p in caught.exception.problems]
        self.assertIn("vocab.attn_built.patterns[2]", paths)
        self.assertIn(f"extraction.fields[TR].patterns[{len(tr['patterns']) - 1}]", paths)

    def test_a_wrong_type_is_named_by_where_it_is(self) -> None:
        data = defaults()
        data["thresholds"]["full"]["fmri_full_min"]["value"] = "eight"
        with self.assertRaises(R.RulesError) as caught:
            R.load(data)
        self.assertEqual(caught.exception.problems[0]["path"], "thresholds.full.fmri_full_min.value")
        data = defaults()
        del data["thresholds"]["abstract"]["fmri_min"]
        with self.assertRaises(R.RulesError):
            R.load(data)

    def test_differences_name_the_changed_paths(self) -> None:
        data = defaults()
        data["tasks"][0]["priority"] = 2
        next(f for f in data["extraction"]["fields"] if f["name"] == "TE")["plausible"]["range"] = [5, 200]
        changed = R.differences(data, defaults())
        self.assertIn("tasks[inner/imagined speech].priority", changed)
        self.assertIn("extraction.fields[TE].plausible.range", changed)
        self.assertEqual(R.differences(defaults(), defaults()), [])


class ScreenTest(unittest.TestCase):
    rules = R.load(defaults())

    def test_an_fmri_transformer_decoder_is_included_with_its_why(self) -> None:
        result = screen.screen_paper(self.rules, "BrainFormer: decoding inner speech from fMRI", "We decode inner speech from fMRI.", DECODER, DECODER)
        verdict = result["verdict"]
        self.assertTrue(verdict["include"], verdict["why"])
        self.assertEqual(verdict["task_category"], "inner/imagined speech")
        self.assertEqual(verdict["priority"], 1)
        self.assertTrue(all(test["pass"] for test in verdict["why"]))
        self.assertEqual(result["model_name"], "BrainFormer")
        fields = result["fields"]
        self.assertEqual(fields["TR"]["values"][0], "2000 ms")
        self.assertEqual(fields["N_Transformer_Layers"]["values"], ["12 layers"])
        self.assertEqual(fields["N_Attention_Heads"]["values"], ["8 heads"])
        self.assertIn("TR = 2000 ms", next(iter(fields["TR"]["evidence"].values())))
        self.assertIn("NSD (Natural Scenes Dataset)", result["datasets"])
        self.assertIn("TR", result["mined"]["NSD (Natural Scenes Dataset)"])

    def test_an_eeg_paper_is_out_for_its_modality(self) -> None:
        verdict = screen.classify(self.rules, "EEG speech decoding", "", EEG, EEG)
        self.assertFalse(verdict["include"])
        self.assertEqual(verdict["reason_code"], "not_fmri")

    def test_implausible_values_are_dropped(self) -> None:
        fields = screen.extract(self.rules, "We used TR = 2000 ms and TE = 565 ms on the scanner.")
        self.assertEqual(fields["TR"]["values"], ["2000 ms"])
        self.assertEqual(fields["TE"]["values"], [])
        self.assertEqual(fields["TE"]["dropped"], ["565 ms"])

    def test_a_threshold_change_moves_the_verdict(self) -> None:
        data = defaults()
        data["thresholds"]["full"]["fmri_full_min"]["value"] = 10_000
        strict = R.load(data)
        verdict = screen.classify(strict, "BrainFormer", "", DECODER, DECODER)
        self.assertEqual(verdict["reason_code"], "not_fmri")

    def test_the_abstract_screen(self) -> None:
        verdict = screen.classify_abstract(self.rules, "Decoding inner speech from fMRI with a transformer",
                                           "We decode inner speech from fMRI with a vision transformer.")
        self.assertTrue(verdict["include"], verdict["why"])
        verdict = screen.classify_abstract(self.rules, "A deep model of speech", "We decode speech from fMRI with a deep network.")
        self.assertEqual(verdict["reason_code"], "no_attention_abstract")
        self.assertEqual(screen.near_miss(verdict), "attention")

    @unittest.skipUnless((OLD_REVIEW / "classify.py").is_file(), "the old prma is not on this machine")
    def test_same_answers_as_the_old_screener(self) -> None:
        def load(name: str):
            spec = importlib.util.spec_from_file_location("old_review_" + name, OLD_REVIEW / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        C, E = load("classify"), load("extract")
        for title, text in (("BrainFormer: inner speech", DECODER), ("EEG speech", EEG)):
            old = C.classify(title, text[:2500], text, text, [], [])
            new = screen.classify(self.rules, title, text[:2500], text, text)
            self.assertEqual((old["include"], old["exclusion_reason"], old["task_category"], old["attention_role"]),
                             (new["include"], new["reason"], new["task_category"], new["attention_role"]))
            old_fields = {}
            for block in (E.ARCH_PATTERNS, E.ACQ_PATTERNS, E.PREPROC_PATTERNS):
                old_fields.update({k: v.values for k, v in E.extract_block(text, block).items() if v})
            self.assertEqual(old_fields, {k: v["values"] for k, v in screen.extract(self.rules, text).items() if v["values"]})


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = db.open_store(Path(directory.name) / "app.db", "k" * 64, False)
        self.files = st.ContentStore(Path(directory.name) / "papers")
        self.addCleanup(self.files.close)
        self.review = ReviewService(self.store, DEFAULTS, self.files)

    def test_save_and_reset(self) -> None:
        before = self.review.signature
        data = copy.deepcopy(self.review.rules.data)
        data["thresholds"]["full"]["decoding_min"]["value"] = 3
        self.review.save(data, "Owner")
        self.assertNotEqual(self.review.signature, before)
        snap = ReviewService(self.store, DEFAULTS, self.files).snapshot()
        self.assertTrue(snap["edited"])
        self.assertEqual(snap["changed"], ["thresholds.full.decoding_min.value"])
        self.review.reset()
        self.assertEqual(self.review.signature, before)
        self.assertIsNone(self.store.get(db.BUCKET_REVIEW_RULES, "rules"))

    def test_saving_bad_rules_saves_nothing(self) -> None:
        data = copy.deepcopy(self.review.rules.data)
        data["survey_title"]["pattern"] = "(unclosed"
        with self.assertRaises(R.RulesError):
            self.review.save(data, "Owner")
        self.assertIsNone(self.store.get(db.BUCKET_REVIEW_RULES, "rules"))

    def test_saving_the_defaults_keeps_no_copy(self) -> None:
        self.review.save(copy.deepcopy(self.review.rules.data), "Owner")
        self.assertIsNone(self.store.get(db.BUCKET_REVIEW_RULES, "rules"))

    def test_setups_copy_save_use_and_delete(self) -> None:
        from app.review.service import SetupError

        default_sig = self.review.signature
        setup = self.review.create("Loose", "Owner", "fewer words", "default")
        self.assertEqual(setup, "loose")
        self.assertEqual(self.review.setups()[1]["signature"], default_sig)
        self.review.save_setup(setup, "Agent", changes=[{"path": "thresholds.full.decoding_min.value", "value": 1}])
        self.assertEqual(self.review.signature, default_sig)  # not in use: nothing moves
        self.review.activate(setup)
        self.assertNotEqual(self.review.signature, default_sig)
        # A new service reads the same setup in use.
        again = ReviewService(self.store, DEFAULTS, self.files)
        self.assertEqual((again.active, again.signature), (setup, self.review.signature))
        self.assertEqual(again.view(setup)["changed"], ["thresholds.full.decoding_min.value"])
        with self.assertRaises(SetupError):
            self.review.delete(setup)
        with self.assertRaises(SetupError):
            self.review.save_setup("default", "Owner", name="Other")
        self.review.activate("default")
        self.assertEqual(self.review.signature, default_sig)
        self.assertEqual(len(self.review.signatures()), 2)
        self.review.delete(setup)
        self.assertEqual([s["id"] for s in self.review.setups()], ["default"])
        self.assertEqual(self.review.signatures(), {default_sig})

    def test_a_setup_in_use_that_no_longer_loads_falls_back(self) -> None:
        setup = self.review.create("Old", "Owner")
        self.review.activate(setup)
        record = self.store.get(db.BUCKET_REVIEW_RULES, "setup:" + setup)
        del record["rules"]["thresholds"]["full"]["fmri_full_min"]
        self.store.put(db.BUCKET_REVIEW_RULES, "setup:" + setup, record)
        again = ReviewService(self.store, DEFAULTS, self.files)
        self.assertEqual(again.active, "default")
        self.assertIn("no longer loads", again.problem)

    def test_changes_paths(self) -> None:
        data = defaults()
        out = R.apply_changes(data, [
            {"path": "extraction.fields[TR].patterns[0]", "value": r"\bTR\s*=\s*(?P<v><<NUM>>)\s*s"},
            {"path": "datasets[+]", "value": {"name": "Mine", "aliases": ["MINE"]}},
            {"path": "tasks[0]", "remove": True},
        ])
        self.assertEqual(out["datasets"][-1]["name"], "Mine")
        self.assertEqual(len(out["tasks"]), len(data["tasks"]) - 1)
        R.load(out)
        for bad in ({"path": "datasets[Nope].name", "value": "x"}, {"path": "a..b", "value": 1}, {"path": "vocab"}):
            with self.assertRaises(R.RulesError):
                R.apply_changes(data, [bad])

    def test_overrides_win_and_consensus_fills_blanks(self) -> None:
        n = self.review.import_overrides({"_README": "notes", "10.1/abc": {"Model_Name": "BolT", "N_Attention_Heads": "40 heads"}})
        self.assertEqual(n, 1)
        self.assertEqual(self.review.import_overrides({"10.1/abc": {"Model_Name": "Other"}}), 0)
        # Two papers state NSD's TR; a third uses NSD and does not say.
        for key in ("p1", "p2"):
            result = {"mined": {"NSD (Natural Scenes Dataset)": {"TR": ["1.6 s"]}}}
            self.files.write(key, "review.json", result)
            self.files.settle(key, "review", "s", st.DONE, {})
        silent = screen.screen_paper(self.review.rules, "Silent", "", "We use the Natural Scenes Dataset (NSD). NSD NSD.", "NSD and NSD again.")
        shown = self.review.present(silent, self.review.override_for("p3", "10.1/ABC"), self.review.consensus())
        self.assertEqual(shown["model_name"], "BolT")
        self.assertTrue(shown["curated"])
        self.assertEqual(shown["fields"]["N_Attention_Heads"]["source"], "curated")
        self.assertEqual(shown["fields"]["TR"]["value"], "1.6 s")
        self.assertEqual(shown["fields"]["TR"]["source"], "dataset")
        self.assertEqual(shown["fields"]["TR"]["dataset_papers"], 2)
        # A paper re-screened without the mention leaves the consensus.
        self.review.screened("p2", {"mined": {}})
        self.assertEqual(self.review.consensus(), [])


class ReviewStageTest(ContentTest):
    def setUp(self) -> None:
        super().setUp()
        self.review = ReviewService(self.store, DEFAULTS, self.content.files)
        self.wanted: set[str] = set()
        self.review.candidates_fn = lambda: set(self.wanted)
        self.content.review = self.review

    def test_only_candidates_are_screened_and_rules_redo_them(self) -> None:
        key = self.key("MindAlign")
        self.content.reconcile()
        self.drain("local")
        self.assertEqual(self.content.files.counts()["review"]["done"], 0)
        self.wanted.add(key)
        self.review.candidates_changed()
        self.content.reconcile()
        self.drain("local")
        self.assertEqual(self.content.files.counts()["review"]["done"], 1)
        result = self.content.files.read(key, "review.json")
        self.assertEqual(result["rules"], self.review.signature)
        self.assertIn("verdict", result)
        # A saved change re-queues the candidate, and only it.
        data = copy.deepcopy(self.review.rules.data)
        data["thresholds"]["full"]["decoding_min"]["value"] = 7
        self.review.save(data, "Owner")
        self.assertEqual(self.content.reconcile(), 1)
        self.drain("local")
        self.assertEqual(self.content.files.read(key, "review.json")["rules"], self.review.signature)
        # Off every list: the review goes.
        self.wanted.clear()
        self.review.candidates_changed()
        self.content.reconcile()
        self.assertIsNone(self.content.files.read(key, "review.json"))
        self.assertEqual(self.content.files.counts()["review"]["done"], 0)


    def test_swapping_back_takes_the_kept_result(self) -> None:
        key = self.key("MindAlign")
        self.wanted.add(key)
        self.review.candidates_changed()
        self.content.reconcile()
        self.drain("local")
        first = self.review.signature
        runs = []
        real = self.review.screen
        self.review.screen = lambda *a, **k: runs.append(1) or real(*a, **k)
        setup = self.review.create("Other", "Owner")
        self.review.save_setup(setup, "Owner", changes=[{"path": "thresholds.full.decoding_min.value", "value": 7}])
        self.review.activate(setup)
        self.content.reconcile()
        self.drain("local")
        self.assertEqual(len(runs), 1)
        self.assertTrue((self.content.files.dir(key) / f"review@{first}.json").is_file())
        # Back to the default: taken from what was kept, nothing screened.
        self.review.activate("default")
        self.assertEqual(self.content.reconcile(), 1)
        self.assertEqual(self.drain("local"), 0)
        self.assertEqual(len(runs), 1)
        self.assertEqual(self.content.files.read(key, "review.json")["rules"], first)
        self.assertEqual(self.content.files.counts()["review"]["done"], 1)
        # And forward again, to the other setup.
        self.review.activate(setup)
        self.content.reconcile()
        self.assertEqual(self.drain("local"), 0)
        self.assertEqual(len(runs), 1)
        # A deleted setup's kept results go the next time the paper is kept.
        self.review.activate("default")
        self.content.reconcile()
        self.review.delete(setup)
        self.content._keep_review(key, "rules:" + first + "#x", {"rules": first}, {})
        self.assertEqual(sorted(p.name for p in self.content.files.dir(key).glob("review@*")), [f"review@{first}.json"])


try:
    from starlette.testclient import TestClient
except (ImportError, RuntimeError):  # Starlette raises RuntimeError without httpx
    TestClient = None


@unittest.skipIf(TestClient is None, "needs httpx2 (pip install httpx2)")
class ReviewRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        from app.tests.test_settings_routes import SettingsRoutesTest

        helper = SettingsRoutesTest("test_settings_are_the_owners_alone")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper

    def call(self, method: str, path: str, who: str = "owner", body: dict | None = None) -> tuple[int, dict]:
        cookie = self.helper.owner if who == "owner" else self.helper.other
        if body is not None and method == "POST":
            body = dict(body, csrf_token=self.helper.csrf if who == "owner" else "")
        return self.helper.call(method, path, cookie=cookie, body=body)

    def key_call(self, method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict]:
        return self.helper.call(method, path, key=key, body=body)

    def test_admins_and_admin_keys_only(self) -> None:
        from app.models import api_keys, users

        store = self.helper.client.app.state.store
        plain = users.create_user(store, "Plain", users.ROLE_USER)
        user_key, _ = api_keys.issue_api_key(store, plain.id, "plain", users.ROLE_USER, 3600)
        self.assertIn(self.key_call("GET", "/api/review/setups", user_key)[0], (403, 404))
        status, listing = self.key_call("GET", "/api/review/setups", self.helper.key)
        self.assertEqual(status, 200)
        self.assertEqual([s["id"] for s in listing["setups"]], ["default"])
        self.assertEqual(listing["in_use"], "default")
        self.assertEqual(self.call("GET", "/api/review/setups", who="other")[0], 200)
        status, view = self.call("GET", "/api/review/setups/default")
        self.assertEqual(status, 200)
        self.assertFalse(view["edited"])
        self.assertEqual(view["changed"], [])
        self.assertEqual(self.call("GET", "/api/review/setups/nope")[0], 404)

    def test_check_save_test_and_reset(self) -> None:
        view = self.call("GET", "/api/review/setups/default")[1]
        rules = view["rules"]
        rules["vocab"]["ours"]["patterns"][0] = "(broken"
        status, check = self.call("POST", "/api/review/check", body={"rules": rules})
        self.assertEqual(status, 200)
        self.assertEqual(check["problems"][0]["path"], "vocab.ours.patterns[0]")
        status, refused = self.call("POST", "/api/review/setups/default", body={"rules": rules})
        self.assertEqual(status, 400)
        self.assertEqual(refused["error"], "invalid_review_rules")
        rules["vocab"]["ours"]["patterns"][0] = r"\bwe propose\b"
        status, tested = self.call("POST", "/api/review/test", body={"rules": rules, "title": "BrainFormer: inner speech", "text": DECODER})
        self.assertEqual(status, 200)
        self.assertTrue(tested["result"]["verdict"]["include"])
        status, saved = self.call("POST", "/api/review/setups/default", body={"rules": rules, "base_signature": view["signature"]})
        self.assertEqual(status, 200)
        self.assertTrue(saved["edited"])
        self.assertIn("vocab.ours.patterns", saved["changed"])
        # Saved again from the old signature: someone else got there first.
        status, moved = self.call("POST", "/api/review/setups/default", body={"rules": rules, "base_signature": view["signature"]})
        self.assertEqual((status, moved["error"]), (409, "review_rules_moved"))
        status, reset = self.call("POST", "/api/review/setups/default/reset", body={})
        self.assertEqual(status, 200)
        self.assertFalse(reset["edited"])

    def test_setups_by_api_key(self) -> None:
        key = self.helper.key
        status, made = self.key_call("POST", "/api/review/setups", key, {
            "name": "Strict decoding", "description": "Two decoding hits",
            "changes": [{"path": "thresholds.full.decoding_min.value", "value": 9}],
        })
        self.assertEqual(status, 201, made)
        setup = made["setup"]["id"]
        self.assertEqual(setup, "strict-decoding")
        self.assertEqual(made["setup"]["based_on"], "default")
        self.assertEqual(made["changed"], ["thresholds.full.decoding_min.value"])
        self.assertFalse(made["setup"]["active"])
        self.assertEqual(self.key_call("POST", "/api/review/setups", key, {"name": "strict DECODING"})[0], 409)
        status, bad = self.key_call("POST", f"/api/review/setups/{setup}", key, {"changes": [{"path": "vocab.nope.patterns", "value": []}]})
        self.assertEqual((status, bad["error"]), (400, "invalid_review_rules"))
        self.assertEqual(bad["problems"][0]["path"], "vocab.nope.patterns")
        status, renamed = self.key_call("POST", f"/api/review/setups/{setup}", key, {"name": "Stricter", "changes": [
            {"path": "vocab.ours.patterns[+]", "value": r"\bthe present work\b"}]})
        self.assertEqual(status, 200, renamed)
        self.assertEqual((renamed["setup"]["id"], renamed["setup"]["name"]), (setup, "Stricter"))
        status, tested = self.key_call("POST", "/api/review/test", key, {"setup": setup, "title": "BrainFormer", "text": DECODER})
        self.assertEqual(status, 200)
        status, used = self.key_call("POST", f"/api/review/setups/{setup}/activate", key, {})
        self.assertEqual(status, 200)
        self.assertEqual(used["in_use"], setup)
        self.assertEqual(self.key_call("POST", f"/api/review/setups/{setup}/delete", key, {})[1]["error"], "review_setup_in_use")
        self.assertEqual(self.key_call("POST", "/api/review/setups/default/delete", key, {})[1]["error"], "review_default_kept")
        self.assertEqual(self.key_call("POST", f"/api/review/setups/{setup}/reset", key, {})[0], 409)
        self.assertEqual(self.key_call("GET", "/api/review/progress", key)[1]["in_use"], setup)
        self.key_call("POST", "/api/review/setups/default/activate", key, {})
        status, left = self.key_call("POST", f"/api/review/setups/{setup}/delete", key, {})
        self.assertEqual(status, 200)
        self.assertEqual([s["id"] for s in left["setups"]], ["default"])

    def test_guide_and_mcp(self) -> None:
        status, guide = self.key_call("GET", "/api/review/guide", self.helper.key)
        self.assertEqual(status, 200)
        self.assertIn("[+]", guide["change_paths"])
        self.assertIn("$defs", guide["schema"])
        status, reply = self.key_call("POST", "/mcp", self.helper.key, {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "create_screener_setup", "arguments": {"name": "From MCP", "activate": True}},
        })
        self.assertEqual(status, 200)
        self.assertFalse(reply["result"].get("isError"), reply)
        self.assertEqual(self.key_call("GET", "/api/review/setups", self.helper.key)[1]["in_use"], "from-mcp")

    def test_export_is_yaml_that_loads(self) -> None:
        response = self.helper.client.get("/api/review/setups/default/export", headers={"cookie": self.helper.owner})
        self.assertEqual(response.status_code, 200)
        import yaml

        self.assertEqual(R.load(yaml.safe_load(response.text)).signature, R.load(defaults()).signature)

    def test_overrides(self) -> None:
        status, reply = self.call("POST", "/api/review/overrides", body={"key": "10.1/x", "fields": {"Model_Name": "X"}})
        self.assertEqual(status, 200)
        self.assertEqual(reply["overrides"], {"10.1/x": {"Model_Name": "X"}})
        self.call("POST", "/api/review/overrides", body={"key": "10.1/x", "fields": {}})
        self.assertEqual(self.call("GET", "/api/review/overrides")[1]["overrides"], {})

if __name__ == "__main__":
    unittest.main()

