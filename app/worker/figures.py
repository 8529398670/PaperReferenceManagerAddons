"""Figure crops for one paper: detect the layout, crop each figure with its
caption, number the crops, and make a montage.

A port of the old app's `prma yolo` + `prma images` (src/pdf/yolo.py,
src/pdf/pdf.py, src/pdf/images.py, preprocess.duplicate_image_idxs and
method_images._page_figures_with_captions), with the same numbers:

  detect   doclayout-yolo on each page rendered at 200 DPI (the first 50
           pages), confidence 0.2, model image size 1024.
  crop     each `figure` box, padded and grown by the union of the caption,
           footnote and title boxes attached to it (x-overlap and a small
           vertical gap), cut from the page re-rendered at 400 DPI.
  number   figure-N counts EVERY figure box, page by page and in detection
           order within a page, duplicates included -- the picks are keyed on
           '<key>#figure-N', so this rule must never change.
  hide     a second box YOLO stacked on a graphic already cropped is still
           written (its number is taken) but flagged `dup` and left out of
           the montage.
  caption  the attached figure_caption boxes' text, from the PDF's own text
           layer, or OCR of that box when the text layer is empty or garbage.

Everything that is geometry is a pure function here and is tested without
torch. The heavy packages (torch, doclayout_yolo, pypdfium2, Pillow, numpy)
are imported inside the functions that use them, so the module imports in
the main app's venv.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from app.worker import ocr as ocr_mod

MODEL_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"

MANIFEST_VERSION = 1

# Detection: the page render YOLO sees, and its settings.
DETECT_DPI = 200
CONFIDENCE = 0.2
MODEL_IMG_SIZE = 1024
MAX_PAGES = 50

# Crops are cut from a sharper render; every detection box is scaled up by
# CROP_DPI / DETECT_DPI first.
CROP_DPI = 400

# Attachment rule, in pixels at CROP_DPI.
ATTACH_X_OVERLAP = 0.30  # least x-overlap, as a share of the narrower box
MAX_ATTACH_GAP = 150  # largest vertical gap between anchor and attachment

# Every box grows by this much before the union: YOLO boxes run a little tight.
PADDING = 10

# Montage: gap between cells, and how far the assembled grid is scaled down.
MONTAGE_PAD = 30
MONTAGE_SCALE = 0.5

FIGURE = "figure"
FIGURE_CAPTION = "figure_caption"
ATTACHMENTS = frozenset({"figure_caption", "table_caption", "table_footnote", "title"})

# Duplicate boxes on one graphic (preprocess.duplicate_image_idxs).
IMAGE_CLASSES = frozenset({"figure", "table"})
DUP_IMAGE_SAME_IOU = 0.80  # two boxes this alike are the same graphic twice
DUP_IMAGE_CONTAINED = 0.80  # share of a smaller box inside a larger: a sub-panel
# A larger box absorbs a smaller one only if it is at most this much LESS
# confident -- a 0.24 page-sized box must not swallow three 0.6 figures.
DUP_IMAGE_CONF_SLACK = 0.10

Box = Sequence[float]


# ---------------------------------------------------------------------------
# Geometry (pure)
# ---------------------------------------------------------------------------

def scale_bbox(bbox: Box, scale: float, padding: int, w: int, h: int) -> tuple[int, int, int, int]:
    """A detection box at DETECT_DPI scaled to CROP_DPI, padded, and clamped
    to a w x h page."""
    x1, y1, x2, y2 = bbox
    return (
        max(0, int(x1 * scale) - padding),
        max(0, int(y1 * scale) - padding),
        min(w, int(x2 * scale) + padding),
        min(h, int(y2 * scale) + padding),
    )


def x_overlap_frac(a: Box, b: Box) -> float:
    """How much two boxes overlap horizontally, as a share of the narrower."""
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    narrower = min(a[2] - a[0], b[2] - b[0])
    if narrower <= 0:
        return 0.0
    return overlap / narrower


def is_attached(anchor: Box, other: Box) -> bool:
    """Does `other` belong to `anchor`: enough x-overlap, and just below it
    (a caption, a footnote) or just above it (a title)?"""
    if x_overlap_frac(anchor, other) < ATTACH_X_OVERLAP:
        return False
    _, ay1, _, ay2 = anchor
    _, by1, _, by2 = other
    if 0 <= by1 - ay2 <= MAX_ATTACH_GAP:
        return True
    return 0 <= ay1 - by2 <= MAX_ATTACH_GAP


def union_box(anchor: Box, others: Iterable[Box]) -> tuple[int, int, int, int]:
    """The anchor grown to cover every box in `others` attached to it."""
    x1, y1, x2, y2 = anchor
    for o in others:
        if not is_attached(anchor, o):
            continue
        x1, y1 = min(x1, o[0]), min(y1, o[1])
        x2, y2 = max(x2, o[2]), max(y2, o[3])
    return (int(x1), int(y1), int(x2), int(y2))


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: Box, b: Box) -> float:
    return (max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
            * max(0.0, min(a[3], b[3]) - max(a[1], b[1])))


def duplicate_image_idxs(page_dets: Sequence[dict[str, Any]]) -> set[int]:
    """Indexes of figure / table boxes that repeat a graphic another box of
    the same type already shows:
      - two near-identical boxes (IoU >= DUP_IMAGE_SAME_IOU): the less
        confident one (the later one on a tie);
      - a box mostly inside a larger one (a sub-panel): the smaller, unless
        the larger is much less confident (DUP_IMAGE_CONF_SLACK).
    Every hidden box sits inside a kept one, so no pixels go missing. Hide,
    never drop: the numbering counts every box."""
    boxes = [
        (idx, d) for idx, d in enumerate(page_dets or [])
        if isinstance(d, dict) and d.get("type") in IMAGE_CLASSES
        and d.get("bbox") and len(d["bbox"]) == 4
    ]
    hidden: set[int] = set()
    for i, a in boxes:
        ab, ac = a["bbox"], float(a.get("confidence") or 0.0)
        aa = _area(ab)
        if aa <= 0:
            continue
        for j, b in boxes:
            if i == j or a["type"] != b["type"]:
                continue
            bb, bc = b["bbox"], float(b.get("confidence") or 0.0)
            inter = _intersection(ab, bb)
            if not inter:
                continue
            ba = _area(bb)
            if inter / (aa + ba - inter) >= DUP_IMAGE_SAME_IOU:
                if (ac, -i) < (bc, -j):
                    hidden.add(i)
                    break
            elif ba > aa and inter / aa >= DUP_IMAGE_CONTAINED and bc >= ac - DUP_IMAGE_CONF_SLACK:
                hidden.add(i)
                break
    return hidden


def number_figures(pages: Sequence[Sequence[dict[str, Any]]]) -> dict[tuple[int, int], int]:
    """(page index, detection index) -> N for every figure box, counting from
    1 page by page in detection order. Duplicates take a number too: the
    picks are keyed on '<key>#figure-N'."""
    out: dict[tuple[int, int], int] = {}
    n = 0
    for page_idx, page_dets in enumerate(pages or []):
        for det_idx, det in enumerate(page_dets or []):
            if isinstance(det, dict) and det.get("type") == FIGURE:
                n += 1
                out[(page_idx, det_idx)] = n
    return out


def page_crop_boxes(page_dets: Sequence[dict[str, Any]], scale: float, w: int, h: int) -> list[dict[str, Any]]:
    """For one page: each figure box's crop rectangle at CROP_DPI (the padded
    figure grown by its attachments) and whether it is a duplicate, as
    [{'det_idx', 'bbox', 'dup'}] in detection order."""
    hidden = duplicate_image_idxs(page_dets)
    scaled: list[tuple[int, str, tuple[int, int, int, int]]] = []
    for det_idx, d in enumerate(page_dets or []):
        if not isinstance(d, dict) or not d.get("bbox"):
            continue
        cls = d.get("type")
        if cls == FIGURE or cls in ATTACHMENTS:
            scaled.append((det_idx, cls, scale_bbox(d["bbox"], scale, PADDING, w, h)))
    attachments = [b for _, cls, b in scaled if cls in ATTACHMENTS]
    return [
        {"det_idx": det_idx, "bbox": union_box(b, attachments), "dup": det_idx in hidden}
        for det_idx, cls, b in scaled if cls == FIGURE
    ]


def pair_captions(page_dets: Sequence[dict[str, Any]], scale: float,
                  caption_texts: dict[int, str]) -> dict[int, str]:
    """figure det_idx -> caption text for one page. Captions attach by the
    same rule the crops use, so the text is the text inside the saved PNG.
    When nothing attaches and the page has exactly one figure, every caption
    on the page is its caption (a caption a little too far away is still
    unambiguous then). `caption_texts` maps a figure_caption det_idx to its
    text; captions are joined top to bottom, repeats dropped (merge_texts)."""
    figs: list[tuple[int, tuple[int, int, int, int]]] = []
    caps: list[tuple[tuple[int, int, int, int], str]] = []
    huge = 10 ** 9  # only the relative geometry matters, not page clamping
    for det_idx, det in enumerate(page_dets or []):
        if not isinstance(det, dict) or not det.get("bbox"):
            continue
        t = det.get("type")
        if t == FIGURE:
            figs.append((det_idx, scale_bbox(det["bbox"], scale, PADDING, huge, huge)))
        elif t == FIGURE_CAPTION:
            caps.append((scale_bbox(det["bbox"], scale, PADDING, huge, huge),
                         caption_texts.get(det_idx, "")))
    out: dict[int, str] = {}
    # Read the captions top to bottom: a caption YOLO split into boxes comes
    # back in detection order, which is not the order of its lines.
    caps.sort(key=lambda c: (c[0][1], c[0][0]))
    for det_idx, fb in figs:
        texts = [txt for cb, txt in caps if txt and is_attached(fb, cb)]
        if not texts and len(figs) == 1:
            texts = [txt for _, txt in caps if txt]
        out[det_idx] = " ".join(merge_texts(texts)).strip()
    return out


def merge_texts(texts: Iterable[str]) -> list[str]:
    """The texts with repeats dropped. YOLO often stacks two boxes on one
    caption, so a text already inside a kept one is a repeat, and a kept text
    inside a new, longer one gives way to it. Order is kept."""
    kept: list[str] = []
    for txt in texts:
        if not txt or any(txt in k for k in kept):
            continue
        kept = [k for k in kept if k not in txt]
        kept.append(txt)
    return kept


def montage_grid_size(sizes: Sequence[tuple[int, int]], pad: int = MONTAGE_PAD) -> Optional[tuple[int, int, int, int]]:
    """(canvas width, canvas height, cols, rows) of the montage for crops of
    these (w, h) sizes before scaling: a near-square grid (cols = ceil(sqrt
    N)) whose cells are the widest crop by the tallest. One crop is itself."""
    if not sizes:
        return None
    if len(sizes) == 1:
        return (sizes[0][0], sizes[0][1], 1, 1)
    n = len(sizes)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    rows = int(math.ceil(n / cols))
    cell_w = max(w for w, _ in sizes)
    cell_h = max(h for _, h in sizes)
    return (cols * cell_w + pad * (cols - 1), rows * cell_h + pad * (rows - 1), cols, rows)


def clean_caption(text: str) -> str:
    """One line of caption text: rejoin words hyphenated across a line break,
    then collapse all whitespace."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text or "")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Images (Pillow, imported lazily)
# ---------------------------------------------------------------------------

def montage(crops: Sequence[Any], pad: int = MONTAGE_PAD, scale: float = MONTAGE_SCALE) -> Any:
    """The crops on a white near-square grid, each centred in its cell, the
    whole scaled down by `scale`. None for no crops."""
    from PIL import Image

    grid = montage_grid_size([(c.width, c.height) for c in crops], pad)
    if grid is None:
        return None
    canvas_w, canvas_h, cols, _rows = grid
    if len(crops) == 1:
        out = crops[0]
    else:
        cell_w = max(c.width for c in crops)
        cell_h = max(c.height for c in crops)
        out = Image.new("RGB", (canvas_w, canvas_h), "white")
        for i, c in enumerate(crops):
            r, col = divmod(i, cols)
            out.paste(c, (col * (cell_w + pad) + (cell_w - c.width) // 2,
                          r * (cell_h + pad) + (cell_h - c.height) // 2))
    if scale and scale < 1.0:
        out = out.resize((max(1, int(out.width * scale)), max(1, int(out.height * scale))),
                         Image.LANCZOS)
    return out


# ---------------------------------------------------------------------------
# The model (lazy, once per process)
# ---------------------------------------------------------------------------

_MODEL: Any = None
_MODEL_PATH: Optional[Path] = None


def _quiet() -> None:
    """Silence ultralytics' per-image banner and the transformers chatter.
    The env vars must be set before doclayout_yolo is first imported."""
    import logging

    os.environ.setdefault("YOLO_VERBOSE", "False")
    os.environ.setdefault("ULTRALYTICS_VERBOSE", "False")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "critical")
    for name in ("ultralytics", "doclayout_yolo", "transformers"):
        logging.getLogger(name).setLevel(logging.ERROR)


def load_model(model_path: Path) -> Any:
    """The process's doclayout-yolo model, loaded on first use (and again
    only if a different file is asked for)."""
    global _MODEL, _MODEL_PATH
    model_path = Path(model_path)
    if _MODEL is None or _MODEL_PATH != model_path:
        if not model_path.is_file():
            raise FileNotFoundError(f"layout model not found: {model_path}")
        _quiet()
        from doclayout_yolo import YOLOv10

        _MODEL = YOLOv10(str(model_path))
        _MODEL_PATH = model_path
    return _MODEL


def detect(image: Any, model: Any) -> list[dict[str, Any]]:
    """Layout boxes on one page image: [{'type', 'class_id', 'bbox' (pixels,
    clamped), 'confidence'}] in the model's order."""
    import numpy as np

    # The model takes numpy arrays as BGR (OpenCV order), as the old code fed it.
    arr = np.ascontiguousarray(np.array(image.convert("RGB"))[:, :, ::-1])
    results = model.predict(arr, imgsz=MODEL_IMG_SIZE, conf=CONFIDENCE, verbose=False)
    if not results or len(results[0].boxes) == 0:
        return []
    det = results[0]
    names, boxes = det.names, det.boxes
    h, w = arr.shape[:2]
    out: list[dict[str, Any]] = []
    for i in range(len(boxes)):
        class_id = int(boxes.cls[i])
        x1, y1, x2, y2 = boxes.xyxyn[i].tolist()
        out.append({
            "type": names[class_id],
            "class_id": class_id,
            "bbox": [max(0, int(x1 * w)), max(0, int(y1 * h)), min(w, int(x2 * w)), min(h, int(y2 * h))],
            "confidence": float(boxes.conf[i]),
        })
    return out


# ---------------------------------------------------------------------------
# PDF (pypdfium2, imported lazily)
# ---------------------------------------------------------------------------

def _render(page: Any, dpi: int) -> Any:
    bitmap = page.render(scale=dpi / 72.0)  # 72 points to the inch
    image = bitmap.to_pil().convert("RGB")  # convert copies off pdfium's buffer
    bitmap.close()
    return image


def _pixel_box_to_pdf(page: Any, bbox: Box, dpi: int) -> tuple[float, float, float, float]:
    """A box in pixels of a `dpi` render of `page` (top-left origin) as a PDF
    rectangle (left, bottom, right, top) for get_text_bounded. pdfium's own
    DeviceToPage is the exact inverse of render(), so the CropBox origin and
    /Rotate are honoured; a plain px * 72 / dpi is off on trimmed or rotated
    pages. Falls back to that, CropBox-aware, if the call fails."""
    import ctypes

    import pypdfium2.raw as pdfium_c

    x1, y1, x2, y2 = bbox
    w_pt, h_pt = page.get_size()
    w_px, h_px = int(round(w_pt * dpi / 72.0)), int(round(h_pt * dpi / 72.0))
    try:
        pts = []
        for x, y in ((x1, y1), (x2, y2)):
            px, py = ctypes.c_double(), ctypes.c_double()
            if not pdfium_c.FPDF_DeviceToPage(page.raw, 0, 0, w_px, h_px, 0, int(round(x)), int(round(y)),
                                              ctypes.byref(px), ctypes.byref(py)):
                raise RuntimeError("FPDF_DeviceToPage failed")
            pts.append((px.value, py.value))
        (ax, ay), (bx, by) = pts
        return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)
    except Exception:
        left, _bottom, _right, top = page.get_cropbox()
        k = 72.0 / dpi
        return left + x1 * k, top - y2 * k, left + x2 * k, top - y1 * k


def _caption_text(page: Any, textpage: Any, crop_image: Any, bbox: Box, use_ocr: bool) -> str:
    """One caption box's text: the text layer when it reads as text, else
    OCR of the box cut from the CROP_DPI render, else ''. The box is read
    as detected, unpadded, like the old OCR stage: widening it to rescue a
    clipped last letter also catches half-words from a box's neighbours."""
    try:
        left, bottom, right, top = _pixel_box_to_pdf(page, bbox, DETECT_DPI)
        text = textpage.get_text_bounded(left=left, bottom=bottom, right=right, top=top) or ""
    except Exception:
        text = ""
    text = text.strip()
    if text and ocr_mod.embedded_ok(text):
        return clean_caption(ocr_mod.normalize_text(text))
    if not use_ocr:
        return ""
    k = CROP_DPI / DETECT_DPI
    x1, y1, x2, y2 = bbox
    box = (max(0, int(x1 * k)), max(0, int(y1 * k)),
           min(crop_image.width, int(x2 * k)), min(crop_image.height, int(y2 * k)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return ""
    try:
        return clean_caption(ocr_mod.ocr_text(crop_image.crop(box)))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# One paper
# ---------------------------------------------------------------------------

def extract(pdf_path: Path, out_dir: Path, model_path: Path) -> dict:
    """Detect (doclayout-yolo, 200 DPI render, up to 50 pages, conf 0.2,
    imgsz 1024), crop figures (anchors 'figure' only; attachments
    figure_caption/table_caption/table_footnote/title per the old
    _is_attached rule) re-rendered at 400 DPI, write out_dir/figure-N.png
    for every figure box (N from 1, page then detection order, duplicates
    included), out_dir/montage.png (the non-duplicate crops, scale 0.5) and
    out_dir/manifest.json. Returns the manifest:

    {"version": 1, "source": "worker", "dpi": 400, "pages": <pages scanned>,
     "figures": [{"n", "page" (1-based), "bbox" [x1,y1,x2,y2] at 400 DPI,
                  "w", "h", "caption", "dup", "file"}...],
     "montage": "montage.png" or None}

    The set is written to a temporary directory beside out_dir and swapped
    in at the end, so a crash leaves the previous set (or none), never half
    of one. A paper with no figures still replaces out_dir, with an empty
    set, so stale crops do not outlive a new PDF."""
    import pypdfium2 as pdfium

    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    model = load_model(model_path)
    use_ocr = ocr_mod.rapid_available()
    scale = CROP_DPI / DETECT_DPI

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", suffix=".tmp", dir=out_dir.parent))
    try:
        figures: list[dict[str, Any]] = []
        montage_crops: list[Any] = []
        n = 0
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            pdf.init_forms()  # draw form fields, as the old renders did
            n_pages = min(len(pdf), MAX_PAGES)
            for page_idx in range(n_pages):
                page = pdf[page_idx]
                try:
                    dets = detect(_render(page, DETECT_DPI), model)
                    if not any(d["type"] == FIGURE for d in dets):
                        continue
                    big = _render(page, CROP_DPI)
                    textpage = page.get_textpage()
                    try:
                        texts = {
                            i: _caption_text(page, textpage, big, d["bbox"], use_ocr)
                            for i, d in enumerate(dets) if d["type"] == FIGURE_CAPTION
                        }
                    finally:
                        textpage.close()
                    captions = pair_captions(dets, scale, texts)
                    for box in page_crop_boxes(dets, scale, big.width, big.height):
                        n += 1
                        x1, y1, x2, y2 = box["bbox"]
                        # A box squeezed to nothing (only possible off the page
                        # edge) still keeps its number: one pixel, not a gap.
                        x2, y2 = max(x2, min(x1 + 1, big.width)), max(y2, min(y1 + 1, big.height))
                        x1, y1 = min(x1, x2 - 1), min(y1, y2 - 1)
                        crop = big.crop((x1, y1, x2, y2))
                        name = f"figure-{n}.png"
                        crop.save(tmp / name)
                        if not box["dup"]:
                            montage_crops.append(crop)
                        figures.append({
                            "n": n,
                            "page": page_idx + 1,
                            "bbox": [x1, y1, x2, y2],
                            "w": crop.width,
                            "h": crop.height,
                            "caption": captions.get(box["det_idx"], ""),
                            "dup": box["dup"],
                            "file": name,
                        })
                finally:
                    page.close()
        finally:
            pdf.close()

        grid = montage(montage_crops)
        if grid is not None:
            grid.save(tmp / "montage.png")
        manifest = {
            "version": MANIFEST_VERSION,
            "source": "worker",
            "dpi": CROP_DPI,
            "pages": n_pages,
            "figures": figures,
            "montage": "montage.png" if grid is not None else None,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        _swap_in(tmp, out_dir)
        return manifest
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _swap_in(tmp: Path, out_dir: Path) -> None:
    """Replace out_dir with the finished tmp directory: two renames, so at
    every instant out_dir is either the whole old set or the whole new one
    (or briefly absent)."""
    old: Optional[Path] = None
    if out_dir.exists():
        old = out_dir.with_name(f".{out_dir.name}.old-{os.getpid()}")
        shutil.rmtree(old, ignore_errors=True)
        os.replace(out_dir, old)
    os.replace(tmp, out_dir)
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)
