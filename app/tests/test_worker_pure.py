"""The heavy worker's pure parts (app/worker/figures.py, app/worker/ocr.py):
the crop geometry, duplicate hiding, figure numbering, caption pairing, the
montage grid, the text-quality gates and OCR line order. None of it needs
torch, pypdfium2 or Pillow; the one Pillow test is skipped without it."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from app.worker import figures as F
from app.worker import ocr as O

HAVE_PIL = importlib.util.find_spec("PIL") is not None


def det(kind: str, bbox: list[int], conf: float = 0.5) -> dict:
    return {"type": kind, "bbox": bbox, "confidence": conf}


class ImportTest(unittest.TestCase):
    def test_imports_without_heavy_packages(self) -> None:
        # The worker modules must import in the main venv: heavy packages are
        # imported inside the functions that use them.
        self.assertEqual(F.MODEL_FILENAME, "doclayout_yolo_docstructbench_imgsz1024.pt")
        self.assertTrue(callable(F.extract) and callable(O.ocr_pdf))


class GeometryTest(unittest.TestCase):
    def test_scale_bbox_pads_and_clamps(self) -> None:
        self.assertEqual(F.scale_bbox([10, 20, 30, 40], 2.0, 10, 1000, 1000), (10, 30, 70, 90))
        self.assertEqual(F.scale_bbox([0, 0, 600, 600], 2.0, 10, 1000, 1100), (0, 0, 1000, 1100))

    def test_x_overlap_is_share_of_narrower(self) -> None:
        self.assertAlmostEqual(F.x_overlap_frac((0, 0, 100, 10), (50, 0, 60, 10)), 1.0)
        self.assertAlmostEqual(F.x_overlap_frac((0, 0, 100, 10), (80, 0, 180, 10)), 0.2)
        self.assertEqual(F.x_overlap_frac((0, 0, 0, 10), (0, 0, 50, 10)), 0.0)

    def test_attached_below_within_gap(self) -> None:
        fig = (100, 100, 900, 800)
        self.assertTrue(F.is_attached(fig, (100, 800, 900, 850)))  # touching
        self.assertTrue(F.is_attached(fig, (100, 950, 900, 1000)))  # gap 150
        self.assertFalse(F.is_attached(fig, (100, 951, 900, 1000)))  # gap 151

    def test_attached_above_within_gap(self) -> None:
        fig = (100, 300, 900, 800)
        self.assertTrue(F.is_attached(fig, (100, 200, 900, 250)))
        self.assertFalse(F.is_attached(fig, (100, 50, 900, 140)))

    def test_padding_eats_small_gaps(self) -> None:
        # Both boxes are padded before the test, so at 200 -> 400 DPI a caption
        # closer than 10 px to its figure overlaps it and does not attach.
        page = [det("figure", [50, 50, 450, 400]), det("figure_caption", [50, 405, 450, 435])]
        self.assertEqual(F.page_crop_boxes(page, 2.0, 2000, 2000)[0]["bbox"], (90, 90, 910, 810))

    def test_not_attached_when_overlapping_or_side_by_side(self) -> None:
        fig = (100, 100, 900, 800)
        # Overlapping vertically is neither above nor below.
        self.assertFalse(F.is_attached(fig, (100, 700, 900, 850)))
        # Too little x-overlap: the other column's caption.
        self.assertFalse(F.is_attached(fig, (850, 820, 1700, 860)))

    def test_union_grows_by_attached_only(self) -> None:
        fig = (100, 100, 900, 800)
        cap = (80, 820, 950, 900)
        far = (100, 2000, 900, 2100)
        self.assertEqual(F.union_box(fig, [cap, far]), (80, 100, 950, 900))
        self.assertEqual(F.union_box(fig, []), fig)


class DuplicateTest(unittest.TestCase):
    def test_near_identical_hides_less_confident(self) -> None:
        dets = [det("figure", [0, 0, 100, 100], 0.4), det("figure", [1, 1, 100, 100], 0.9)]
        self.assertEqual(F.duplicate_image_idxs(dets), {0})

    def test_near_identical_tie_hides_later(self) -> None:
        dets = [det("figure", [0, 0, 100, 100], 0.5), det("figure", [0, 0, 100, 100], 0.5)]
        self.assertEqual(F.duplicate_image_idxs(dets), {1})

    def test_subpanel_hidden_inside_confident_parent(self) -> None:
        dets = [det("figure", [0, 0, 400, 400], 0.6), det("figure", [10, 10, 100, 100], 0.6)]
        self.assertEqual(F.duplicate_image_idxs(dets), {1})

    def test_weak_page_box_does_not_swallow_figures(self) -> None:
        dets = [det("figure", [0, 0, 1000, 1000], 0.24), det("figure", [10, 10, 300, 300], 0.6),
                det("figure", [400, 400, 700, 700], 0.6)]
        self.assertEqual(F.duplicate_image_idxs(dets), set())

    def test_types_and_text_are_separate(self) -> None:
        dets = [det("figure", [0, 0, 100, 100], 0.4), det("table", [0, 0, 100, 100], 0.9),
                det("plain text", [0, 0, 100, 100], 0.9)]
        self.assertEqual(F.duplicate_image_idxs(dets), set())


class NumberingTest(unittest.TestCase):
    def test_every_figure_numbered_page_then_detection_order(self) -> None:
        pages = [
            [det("plain text", [0, 0, 1, 1]), det("figure", [0, 0, 9, 9])],
            [],
            [det("figure", [0, 0, 9, 9]), det("table", [0, 0, 9, 9]), det("figure", [0, 0, 9, 9], 0.1)],
        ]
        self.assertEqual(F.number_figures(pages), {(0, 1): 1, (2, 0): 2, (2, 2): 3})

    def test_duplicates_still_take_a_number(self) -> None:
        page = [det("figure", [0, 0, 100, 100], 0.4), det("figure", [0, 0, 100, 100], 0.9)]
        boxes = F.page_crop_boxes(page, 2.0, 10_000, 10_000)
        self.assertEqual([b["dup"] for b in boxes], [True, False])
        self.assertEqual(len(F.number_figures([page])), 2)

    def test_crop_boxes_in_detection_order_with_attachments(self) -> None:
        page = [
            det("figure_caption", [50, 410, 450, 440]),
            det("figure", [50, 50, 450, 400]),
            det("table", [500, 50, 900, 400]),
            det("figure", [500, 500, 900, 900]),
        ]
        boxes = F.page_crop_boxes(page, 2.0, 2000, 2000)
        self.assertEqual([b["det_idx"] for b in boxes], [1, 3])
        # Figure 1 grew down over its caption (padded by 10 at crop scale).
        self.assertEqual(boxes[0]["bbox"], (90, 90, 910, 890))
        self.assertEqual(boxes[1]["bbox"], (990, 990, 1810, 1810))


class CaptionTest(unittest.TestCase):
    def test_attached_caption_text(self) -> None:
        page = [
            det("figure", [50, 50, 450, 400]),
            det("figure_caption", [50, 410, 450, 440]),
            det("figure", [50, 600, 450, 900]),
            det("figure_caption", [50, 910, 450, 940]),
        ]
        out = F.pair_captions(page, 2.0, {1: "Figure 1. A", 3: "Figure 2. B"})
        self.assertEqual(out, {0: "Figure 1. A", 2: "Figure 2. B"})

    def test_single_figure_falls_back_to_every_caption(self) -> None:
        page = [det("figure", [50, 50, 450, 400]), det("figure_caption", [50, 1500, 450, 1540])]
        self.assertEqual(F.pair_captions(page, 2.0, {1: "Far caption"}), {0: "Far caption"})

    def test_no_fallback_with_two_figures(self) -> None:
        page = [det("figure", [50, 50, 450, 400]), det("figure", [500, 50, 900, 400]),
                det("figure_caption", [50, 1500, 450, 1540])]
        self.assertEqual(F.pair_captions(page, 2.0, {2: "Far"}), {0: "", 1: ""})

    def test_split_caption_read_top_down_and_repeats_dropped(self) -> None:
        page = [
            det("figure", [50, 50, 450, 400]),
            det("figure_caption", [50, 450, 450, 480]),  # second line, detected first
            det("figure_caption", [50, 415, 450, 445]),
            det("figure_caption", [52, 416, 450, 444]),  # a stacked box on line one
        ]
        texts = {1: "and its legend.", 2: "Figure 1. The setup", 3: "The setup"}
        self.assertEqual(F.pair_captions(page, 2.0, texts), {0: "Figure 1. The setup and its legend."})

    def test_merge_texts(self) -> None:
        self.assertEqual(F.merge_texts(["abc", "", "abc", "b", "xabcx", "z"]), ["xabcx", "z"])

    def test_clean_caption(self) -> None:
        self.assertEqual(F.clean_caption("Fig. 1  An exam-\n ple\tof\n\ntext "), "Fig. 1 An example of text")


class MontageTest(unittest.TestCase):
    def test_grid_size(self) -> None:
        self.assertIsNone(F.montage_grid_size([]))
        self.assertEqual(F.montage_grid_size([(300, 200)]), (300, 200, 1, 1))
        # 3 crops -> 2 columns x 2 rows of the widest by the tallest, pad 30.
        self.assertEqual(F.montage_grid_size([(100, 50), (200, 80), (150, 60)]), (430, 190, 2, 2))
        # 5 crops -> 3 x 2.
        self.assertEqual(F.montage_grid_size([(10, 10)] * 5, pad=0), (30, 20, 3, 2))

    @unittest.skipUnless(HAVE_PIL, "needs Pillow")
    def test_montage_scaled(self) -> None:
        from PIL import Image

        crops = [Image.new("RGB", (100, 50)), Image.new("RGB", (200, 80)), Image.new("RGB", (150, 60))]
        self.assertEqual(F.montage(crops).size, (215, 95))
        self.assertIsNone(F.montage([]))


class SwapTest(unittest.TestCase):
    def test_swap_replaces_whole_set(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "figs"
            out.mkdir()
            (out / "figure-9.png").write_text("old")
            tmp = Path(d) / ".figs.new"
            tmp.mkdir()
            (tmp / "figure-1.png").write_text("new")
            F._swap_in(tmp, out)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["figure-1.png"])
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["figs"])


class TextQualityTest(unittest.TestCase):
    PROSE = ("The participants performed an inner speech task while we recorded "
             "functional images of the whole brain. ") * 40

    def test_needs_ocr_empty(self) -> None:
        self.assertTrue(O.needs_ocr(""))
        self.assertTrue(O.needs_ocr("  \n\t "))

    def test_needs_ocr_good_text(self) -> None:
        self.assertFalse(O.needs_ocr(self.PROSE))
        self.assertFalse(O.needs_ocr(self.PROSE, pages=5))

    def test_needs_ocr_too_thin_per_page(self) -> None:
        self.assertTrue(O.needs_ocr("Journal of Things, page 1", pages=10))
        self.assertFalse(O.needs_ocr("Journal of Things, page 1"))  # page count unknown

    def test_needs_ocr_garbage(self) -> None:
        self.assertTrue(O.needs_ocr(" abc " * 200, pages=1))
        self.assertTrue(O.needs_ocr("(cid:12)(cid:7) the (cid:44) " * 200, pages=1))
        self.assertTrue(O.needs_ocr("1234 5678 9012 ,,, ;;; " * 200, pages=1))
        self.assertTrue(O.needs_ocr("furthertechnicaladvantageofthemethodology " * 200, pages=1))

    def test_embedded_ok(self) -> None:
        self.assertTrue(O.embedded_ok("(1)"))
        self.assertTrue(O.embedded_ok("Figure 2. The task"))
        self.assertFalse(O.embedded_ok(""))
        self.assertFalse(O.embedded_ok(""))

    def test_normalize_text(self) -> None:
        self.assertEqual(O.normalize_text("ﬁne “quote”\n\n\n  a  b \x07"), 'fine "quote"\n\na b')


class OcrOrderTest(unittest.TestCase):
    def line(self, x1: float, y1: float, x2: float, y2: float, text: str) -> dict:
        return {"bbox": (x1, y1, x2, y2), "text": text}

    def test_two_columns_left_before_right(self) -> None:
        lines = [
            self.line(100, 10, 900, 30, "Title"),
            self.line(520, 100, 900, 120, "R1"),
            self.line(50, 100, 480, 120, "L1"),
            self.line(50, 130, 480, 150, "L2"),
            self.line(520, 130, 900, 150, "R2"),
            self.line(50, 500, 950, 520, "Full-width caption"),
            self.line(50, 600, 480, 620, "L3"),
            self.line(520, 600, 900, 620, "R3"),
        ]
        got = [l["text"] for l in O.order_lines(lines, 1000)]
        self.assertEqual(got, ["Title", "L1", "L2", "R1", "R2", "Full-width caption", "L3", "R3"])

    def test_one_column_is_top_down(self) -> None:
        lines = [self.line(50, 30, 950, 40, "b"), self.line(50, 10, 950, 20, "a")]
        self.assertEqual([l["text"] for l in O.order_lines(lines, 1000)], ["a", "b"])

    def test_polygon_to_bbox(self) -> None:
        self.assertEqual(O.polygon_to_bbox([[1, 2], [5, 2], [5, 9], [1, 9]]), (1.0, 2.0, 5.0, 9.0))
        self.assertIsNone(O.polygon_to_bbox(None))


class StuckWordsTest(unittest.TestCase):
    @staticmethod
    def fake_split(s: str) -> list[str]:
        vocab = ["international", "cooperation", "the", "foundation", "is", "a", "charity"]
        out, i = [], 0
        while i < len(s):
            for w in sorted(vocab, key=len, reverse=True):
                if s.startswith(w, i):
                    out.append(w)
                    i += len(w)
                    break
            else:
                out.append(s[i])
                i += 1
        return out

    def test_splits_and_keeps_case_and_punctuation(self) -> None:
        self.assertEqual(O.split_stuck_token("(TheFoundationisacharityinternational,", self.fake_split),
                         ["(The", "Foundation", "is", "a", "charity", "international,"])
        self.assertEqual(O.split_stuck_token("thefoundationisacharity.", self.fake_split),
                         ["the", "foundation", "is", "a", "charity."])

    def test_leaves_short_names_and_guesses(self) -> None:
        self.assertEqual(O.split_stuck_token("BrainVoyagerQX", self.fake_split), ["BrainVoyagerQX"])
        self.assertEqual(O.split_stuck_token("thexqzfoundation", self.fake_split), ["thexqzfoundation"])
        self.assertEqual(O.split_stuck_token("short", self.fake_split), ["short"])

    def test_only_stuck_lines_are_touched(self) -> None:
        text = "internationalcooperationthefoundation\ninternationalcooperation is fine here"
        self.assertEqual(O.split_stuck_words(text, self.fake_split),
                         "international cooperation the foundation\ninternationalcooperation is fine here")


if __name__ == "__main__":
    unittest.main()
