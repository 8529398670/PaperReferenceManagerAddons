"""The method-figure caption matcher: the keyword file, the two tiers, the
rules that keep one concept from voting twice, the overview (lead) flag, and
spans that point into the caption as written."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.content import method_figures as mf

ROOT = Path(__file__).resolve().parents[2]


def kws(strong: tuple[str, ...] = (), weak: tuple[str, ...] = ()) -> mf.Keywords:
    return mf.Keywords(strong, weak, "test")


class LoadKeywords(unittest.TestCase):
    def write(self, text: str) -> Path:
        d = tempfile.mkdtemp()
        p = Path(d) / "method-images.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_sections_comments_and_dedupe(self) -> None:
        p = self.write("# comment\nflat term\n\n[weak]\nLSTM\n  # indented comment\n[strong]\nArchitecture\n[ WEAK ]\narchitecture\nlstm\nlayer\n")
        kw = mf.load_keywords(p)
        # Before any header is strong; a repeat (any case, either tier) is dropped
        # and the first spelling and tier win.
        self.assertEqual(kw.strong, ("flat term", "Architecture"))
        self.assertEqual(kw.weak, ("LSTM", "layer"))
        self.assertEqual(len(kw.signature), 12)

    def test_signature_follows_content(self) -> None:
        a = mf.load_keywords(self.write("[strong]\narchitecture\n"))
        b = mf.load_keywords(self.write("[strong]\narchitecture\n"))
        c = mf.load_keywords(self.write("[strong]\npipeline\n"))
        self.assertEqual(a.signature, b.signature)
        self.assertNotEqual(a.signature, c.signature)

    def test_missing_file_is_empty(self) -> None:
        kw = mf.load_keywords(Path(tempfile.mkdtemp()) / "nope.txt")
        self.assertEqual((kw.strong, kw.weak, kw.signature), ((), (), ""))
        self.assertIsNone(mf.match("Overall architecture of the model", kw))

    def test_shipped_file(self) -> None:
        kw = mf.load_keywords(ROOT / "config" / "method-images.txt")
        self.assertEqual((len(kw.strong), len(kw.weak)), (27, 57))
        self.assertIn("architecture", kw.strong)
        self.assertIn("transformer", kw.weak)


class Match(unittest.TestCase):
    def test_strong_alone_qualifies(self) -> None:
        m = mf.match("Figure 1. Overall architecture of the network.", kws(("architecture",)))
        assert m is not None
        self.assertEqual(m["terms"], ["architecture"])
        self.assertTrue(m["strong"])
        self.assertEqual(m["score"], 100.0)

    def test_fuzzy_inflection(self) -> None:
        self.assertIsNotNone(mf.match("Two CNNs side by side", kws(("CNN",))))

    def test_weak_needs_min_weak_distinct(self) -> None:
        kw = kws(weak=("encoder", "block", "LSTM", "transformer"))
        self.assertIsNone(mf.match("Accuracy of our transformer", kw))
        self.assertIsNone(mf.match("The encoder block", kw))  # 2 < 3
        m = mf.match("The encoder block feeds an LSTM", kw)
        assert m is not None
        self.assertFalse(m["strong"])
        self.assertFalse(m["lead"])
        self.assertIsNotNone(mf.match("The encoder block", kw, min_weak=2))

    def test_same_word_votes_once(self) -> None:
        # 'block' and 'blocks' in different sentences are one piece of evidence.
        kw = kws(weak=("block", "task", "vowel"))
        self.assertIsNone(mf.match("Results per block. Blocks repeat.", kws(weak=("block", "blocks", "results"))))
        self.assertIsNotNone(mf.match("vowel task block", kw))

    def test_overlapping_hits_vote_once(self) -> None:
        kw = kws(weak=("attention", "self-attention", "attention mechanism"))
        self.assertIsNone(mf.match("A self attention mechanism", kw, min_weak=2))

    def test_prefix_keeps_decoder_off_encoder(self) -> None:
        # rapidfuzz scores decoder/encoder at 85.7; the prefix rule stops it.
        self.assertIsNone(mf.match("the encoder", kws(("decoder",))))
        # Single words match whole tokens, never the inside of a longer word.
        self.assertIsNone(mf.match("a variational autoencoder", kws(("decoder",))))

    def test_multiword_alignment_on_word_boundary(self) -> None:
        kw = kws(("self-attention", "block diagram"))
        m = mf.match("Multi-head self attention and its block-diagram.", kw)
        assert m is not None
        self.assertEqual(m["terms"], ["self-attention", "block diagram"])
        # Starting mid-word is not a match.
        self.assertIsNone(mf.match("unblock diagrams", kws(("block diagram",))))

    def test_strong_terms_listed_first(self) -> None:
        kw = kws(("pipeline",), ("encoder",))
        m = mf.match("An encoder inside the pipeline", kw)
        assert m is not None
        self.assertEqual(m["terms"], ["pipeline", "encoder"])

    def test_lead_ignores_the_figure_label(self) -> None:
        kw = kws(("architecture",))
        early = mf.match("Supplementary Figure 12: " + "x" * 80 + " architecture", kw)
        late = mf.match("Fig. 3. Accuracy " + "y" * 100 + " with the same architecture", kw)
        assert early is not None and late is not None
        self.assertTrue(early["lead"])
        self.assertFalse(late["lead"])

    def test_spans_point_into_the_original(self) -> None:
        cap = "  Fig 1.\n The   Overall\tARCHITECTURE  and a Pipeline."
        m = mf.match(cap, kws(("overall architecture", "pipeline")))
        assert m is not None
        self.assertEqual([cap[a:b] for a, b in m["spans"]], ["Overall\tARCHITECTURE", "Pipeline"])

    def test_spans_merge_overlaps(self) -> None:
        cap = "Model architecture overview"
        m = mf.match(cap, kws(("architecture", "model architecture")))
        assert m is not None
        self.assertEqual(m["spans"], [[0, 18]])

    def test_spans_survive_chars_that_grow_when_lowered(self) -> None:
        cap = "İİ  the Encoder–Decoder backbone"
        m = mf.match(cap, kws(("backbone",)))
        assert m is not None
        self.assertEqual([cap[a:b] for a, b in m["spans"]], ["backbone"])

    def test_empty(self) -> None:
        self.assertIsNone(mf.match("", kws(("architecture",))))
        self.assertIsNone(mf.match("   \n", kws(("architecture",))))


class MatchPaper(unittest.TestCase):
    def test_keys_by_figure_number(self) -> None:
        figs = [
            {"n": 1, "caption": "Overall architecture"},
            {"n": 2, "caption": "ROC curves"},
            {"n": 3, "caption": None},
            {"n": 4, "page": 2, "caption": "Processing pipeline"},
        ]
        out = mf.match_paper(figs, kws(("architecture", "pipeline")))
        self.assertEqual(sorted(out), [1, 4])
        self.assertEqual(out[4]["terms"], ["pipeline"])


if __name__ == "__main__":
    unittest.main()
