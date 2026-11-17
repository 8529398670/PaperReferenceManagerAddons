"""Per-paper content from plain text: modality tagging, section splitting,
the bibliography cut, code / data links and named datasets. Against a small
fake paper laid out the way Zotero's .zotero-ft-cache lays one out."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.content import links, modalities, sections

REPO = Path(__file__).resolve().parents[2]

PAPER = """1
Journal of Imaginary Neuroscience 12 (2024) 1-9
Decoding inner speech from brain
activity with transformers
A. Author, B. Author
Abstract
We decode inner speech from fMRI recordings using a transformer model.
1. Introduction
Inner speech has been studied with many methods. Prior work used EEG and
MEG (Smith et al., 2019). Code is available at https://github.com/kelseyhan-
lab/inner-speech.
Journal of Imaginary Neuroscience 12 (2024) 1-9
2
2. Materials and Methods
2.1 Participants
Twenty healthy adults took part. All gave informed consent.
2.2 Stimuli
Stimuli were presented on a screen. We used the Human Connectome Project
(HCP) preprocessing pipeline and HCP data. Data are on OpenNeuro (ds000123).
Figure 1. Overview of the decoding pipeline.
Scanning used a 3T scanner (see github.com/kelseyhan-lab/inner-speech).
3. Results
Decoding accuracy was above chance.
Journal of Imaginary Neuroscience 12 (2024) 1-9
3
4. Discussion
Our results extend earlier electroencephalo-
graphy work.
References
1. Smith, J. et al. Natural Scenes Dataset (NSD). Nature 1, 1-2 (2020).
2. Jones, K. NSD revisited: the NSD dataset again. doi:10.1000/xyz (2021).
"""


def _vocab_file(directory: Path, text: str) -> Path:
    path = directory / "modalities.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class ModalitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.vocab = modalities.load_vocab(REPO / "config" / "modalities.yaml")

    def test_shipped_file_matches_default(self) -> None:
        self.assertEqual(self.vocab.entries, list(modalities.DEFAULT))

    def test_whole_word_label(self) -> None:
        self.assertEqual(modalities.scan(self.vocab, "We share the dataset publicly."), [])
        self.assertEqual(modalities.scan(self.vocab, "Measured with PET and fmri."), ["fMRI", "PET"])

    def test_phrase_stems(self) -> None:
        self.assertEqual(modalities.scan(self.vocab, "Electroencephalographic and electrocorticography data"), ["EEG", "ECoG"])
        self.assertEqual(modalities.count(self.vocab, "EEG, EEG and electroencephalogram"), {"EEG": 3})

    def test_vocab_order(self) -> None:
        self.assertEqual(modalities.scan(self.vocab, "MEG then EEG then fMRI"), ["fMRI", "EEG", "MEG"])
        self.assertEqual(modalities.order(self.vocab, {"PET", "fMRI"}), ["fMRI", "PET"])

    def test_signature_follows_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _vocab_file(Path(d), "modalities:\n  - label: EEG\n    phrases: electroencephalogra\n  - MEG\n")
            first = modalities.load_vocab(path)
            self.assertEqual(first.labels, ["EEG", "MEG"])
            self.assertEqual(first.entries, [("EEG", ("electroencephalogra",)), ("MEG", ())])
            path.write_text("modalities:\n  - MEG\n  - EEG\n", encoding="utf-8")
            second = modalities.load_vocab(path)
            self.assertNotEqual(first.signature, second.signature)
            self.assertEqual(second.labels, ["MEG", "EEG"])

    def test_broken_file_falls_back_once(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _vocab_file(Path(d), "modalities: [ {label: '' } ]\n")
            out = io.StringIO()
            with redirect_stdout(out):
                a = modalities.load_vocab(path)
                b = modalities.load_vocab(path)
                missing = modalities.load_vocab(Path(d) / "nope.yaml")
            self.assertEqual(a.labels, [label for label, _ in modalities.DEFAULT])
            self.assertEqual(a.signature, b.signature)
            self.assertEqual(a.signature, missing.signature)
            self.assertEqual(out.getvalue().count(str(path)), 1)

    def test_tag_reads_title_abstract_methods(self) -> None:
        used, inferred = modalities.tag(self.vocab, "An MEG study", "", "", "EEG " * 20)
        self.assertEqual((used, inferred), (["MEG"], False))

    def test_methods_with_nothing_is_an_answer(self) -> None:
        self.assertEqual(modalities.tag(self.vocab, "", "Brain responses.", "We asked people.", "fMRI " * 20), ([], False))

    def test_inferred_fallback(self) -> None:
        body = "Intro.\n\n" + "We recorded EEG here. " * 9 + "Unlike fMRI work.\n\nReferences\n1. Smith, J. MEG and MEG (2020)."
        # Abstract, no Methods: only the dominant modality, named often enough.
        self.assertEqual(modalities.tag(self.vocab, "", "Brain responses.", "", body), (["EEG"], True))
        thin = "We recorded EEG here. " * 3 + "fMRI too."
        self.assertEqual(modalities.tag(self.vocab, "", "Brain responses.", "", thin), ([], False))
        # No abstract either: anything the body names, but not the references.
        self.assertEqual(modalities.tag(self.vocab, "", "", "", body), (["fMRI", "EEG"], True))


class SectionsTest(unittest.TestCase):
    def test_split(self) -> None:
        secs = sections.split(PAPER)
        keys = [s["key"] for s in secs]
        self.assertEqual(keys[0], "front")
        for key in ("abstract", "introduction", "methods", "figures", "results", "discussion", "references"):
            self.assertIn(key, keys)
        self.assertLess(keys.index("abstract"), keys.index("introduction"))
        self.assertLess(keys.index("methods"), keys.index("results"))
        headings = [s["heading"] for s in secs]
        self.assertIn("2. Materials and Methods", headings)
        self.assertIn("2.1 Participants", headings)
        # Running heads and page numbers are gone; the title lines are joined.
        front = secs[0]["text"]
        self.assertNotIn("Journal of Imaginary", "\n".join(s["text"] for s in secs))
        self.assertIn("Decoding inner speech from brain activity with transformers", front)
        # A word hyphenated at a line break is rejoined.
        discussion = next(s for s in secs if s["key"] == "discussion")
        self.assertIn("electroencephalography work.", discussion["text"])

    def test_methods_text(self) -> None:
        methods = sections.methods_text(sections.split(PAPER))
        self.assertIn("Twenty healthy adults", methods)
        self.assertIn("2.2 Stimuli\n\nStimuli were presented", methods)
        # The caption is routed aside and the section resumes after it.
        self.assertNotIn("Overview of the decoding pipeline", methods)
        self.assertIn("Scanning used a 3T scanner", methods)
        self.assertNotIn("Decoding accuracy", methods)

    def test_heading_prefixes(self) -> None:
        self.assertEqual(sections.classify_header("Discussion"), "discussion")
        self.assertEqual(sections.classify_header("I. INTRODUCTION"), "introduction")
        self.assertEqual(sections.classify_header("Conclusions"), "conclusion")
        self.assertEqual(sections.classify_header("Results and Discussion"), "results")
        self.assertEqual(sections.classify_header("Experimental procedures"), "methods")
        keys = [s["key"] for s in sections.split("Intro text here.\n\nParticipants were twenty adults\nfrom the area.\n")]
        self.assertEqual(keys, ["front"])

    def test_cut_bibliography(self) -> None:
        cut = sections.cut_bibliography(PAPER)
        self.assertIn("electroencephalography work.", cut)
        self.assertNotIn("Natural Scenes Dataset", cut)
        self.assertNotIn("References", cut)

    def test_references_without_heading(self) -> None:
        body = "\n".join(
            ["Some prose here.", "More prose follows.", "Even more prose."]
            + [
                "1. Colen, R. R. Multimodality intraoperative MRI. Neurotherapeutics 10, 1545-1558 (2010).",
                "2. Ogawa, S. et al. Brain magnetic resonance imaging with contrast. PNAS 87, 9868-9872 (1990).",
                "3. Ashtari, M. et al. Mapping the functional anatomy of sentence comprehension (2005).",
                "4. Zaca, D. Role of semantic paradigms. AJNR 34, doi:10.3174/ajnr.A3628 (2013).",
            ]
        )
        secs = sections.split(body)
        self.assertEqual([s["key"] for s in secs], ["front", "references"])
        self.assertEqual(sections.cut_bibliography(body), "Some prose here.\n\nMore prose follows.\n\nEven more prose.")


class LinksTest(unittest.TestCase):
    def test_split_url_is_stitched_and_deduplicated(self) -> None:
        found = links.code_links(("abstract", ""), ("body", PAPER))
        self.assertEqual(found, [{"url": "https://github.com/kelseyhan-lab/inner-speech", "host": "GitHub", "where": "body"}])

    def test_host_only_needs_a_newline(self) -> None:
        self.assertEqual([x["url"] for x in links.code_links(("body", "see https://github.com/\nowner/repo here"))], ["https://github.com/owner/repo"])
        self.assertEqual(links.code_links(("body", "see https://github.com/ owner said")), [])

    def test_trailing_punctuation_and_plausibility(self) -> None:
        text = "Code (https://github.com/a/b). Also https://github.com and www.zenodo.org/record/1/; cut https://gitlab.com/x/y-"
        self.assertEqual([x["url"] for x in links.code_links(("abstract", text))], ["https://github.com/a/b", "https://www.zenodo.org/record/1/"])

    def test_first_seen_where_wins(self) -> None:
        found = links.code_links(("abstract", "https://osf.io/abc12"), ("body", "osf.io/abc12/ and https://www.osf.io/abc12"))
        self.assertEqual(found, [{"url": "https://osf.io/abc12", "host": "OSF", "where": "abstract"}])

    def test_doi_hints(self) -> None:
        self.assertEqual(links.code_links(("body", "https://doi.org/10.5281/zenodo.123")), [{"url": "https://doi.org/10.5281/zenodo.123", "host": "Zenodo", "where": "body"}])
        self.assertEqual(links.data_links(("body", "https://doi.org/10.18112/openneuro.ds003020.v1.0.0 and ds003020"))[0]["host"], "OpenNeuro")
        self.assertEqual(len(links.data_links(("body", "https://doi.org/10.18112/openneuro.ds003020.v1.0.0 and ds003020"))), 1)

    def test_accession_minted(self) -> None:
        found = links.data_links(("abstract", ""), ("body", PAPER))
        self.assertEqual(found, [{"url": "https://openneuro.org/datasets/ds000123", "host": "OpenNeuro", "where": "body", "accession": "ds000123"}])
        # A GitHub repo is a code link, not a data one.
        self.assertFalse(any(x["host"] == "GitHub" for x in found))

    def test_dataset_names_ignore_references(self) -> None:
        names = links.dataset_names(PAPER)
        self.assertIn("HCP (Human Connectome Project)", [n["name"] for n in names])
        hcp = next(n for n in names if n["name"].startswith("HCP"))
        self.assertEqual(hcp["url"], "https://www.humanconnectome.org/")
        self.assertTrue(hcp["description"])
        # NSD is named three times, all in the reference list.
        self.assertNotIn("NSD (Natural Scenes Dataset)", [n["name"] for n in names])
        self.assertIn("NSD (Natural Scenes Dataset)", links.detect(PAPER))

    def test_scan_paper(self) -> None:
        result = links.scan_paper("Decoding inner speech", "We use HCP.", PAPER)
        self.assertEqual([x["host"] for x in result["code"]], ["GitHub"])
        self.assertEqual([x["url"] for x in result["data"]], ["https://openneuro.org/datasets/ds000123"])
        self.assertIn("HCP (Human Connectome Project)", [n["name"] for n in result["names"]])
        self.assertEqual(links.scan_paper("t", "We use HCP and HCP.", "")["names"], [])

    def test_abstract_from_inverted(self) -> None:
        self.assertEqual(links.abstract_from_inverted({"world": [1], "hello": [0], "again": [3], "hello,": [2]}), "hello world hello, again")
        self.assertEqual(links.abstract_from_inverted(None), "")


if __name__ == "__main__":
    unittest.main()
