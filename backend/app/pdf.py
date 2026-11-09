"""PDF ingestion: text extraction, OCR fallback, and clause highlighting."""
import base64
import io
import os
import re
from pathlib import Path

from fastapi import HTTPException

MAX_PAGES = 30
MIN_CONF = 60.0  # below this OCR is guessing: no highlight beats a wrong one


def _ocr_page(img) -> tuple[str, list[dict]]:
    """Text plus word boxes (as fractions of the page) for one rendered page."""
    import pytesseract

    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    w, h = img.size
    lines, order, words = {}, [], []
    for i, raw in enumerate(d["text"]):
        word, conf = raw.strip(), float(d["conf"][i])
        if not word or conf < 0:
            continue
        key = (int(d["block_num"][i]), int(d["par_num"][i]), int(d["line_num"][i]))
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
        if conf >= MIN_CONF:
            words.append({"text": word,
                          "x": int(d["left"][i]) / w, "y": int(d["top"][i]) / h,
                          "w": int(d["width"][i]) / w, "h": int(d["height"][i]) / h})
    parts, prev = [], None
    for key in order:
        if prev is None or key[:2] != prev[:2]:
            parts.append(" ".join(lines[key]))
        else:
            parts[-1] += "\n" + " ".join(lines[key])
        prev = key
    return "\n\n".join(parts), words


def ocr_pdf(data: bytes) -> tuple[str, list[list[dict]]]:
    import pymupdf
    import pytesseract
    from PIL import Image

    cmd = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if Path(cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(400, "Could not read this PDF (corrupted or encrypted).")
    pages, words = [], []
    try:
        with doc:
            if len(doc) > MAX_PAGES:
                raise HTTPException(413, f"Too many pages (max {MAX_PAGES}).")
            for p in doc:
                text, boxes = _ocr_page(Image.open(io.BytesIO(p.get_pixmap(dpi=200).tobytes("png"))))
                pages.append(text)
                words.append(boxes)
    except HTTPException:
        raise
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(503, "OCR is not installed on the server. Install Tesseract, or paste the text instead.")
    except Exception:
        raise HTTPException(422, "OCR could not read this scan. Try a sharper scan, or paste the text instead.")
    return "\n".join(pages), words


def pdf_to_text(data: bytes) -> tuple[str, bool, list[list[dict]] | None]:
    """Returns (text, used_ocr, ocr word boxes per page)."""
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise HTTPException(413, f"Too many pages (max {MAX_PAGES}).")
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this PDF (corrupted or encrypted).")
    if len(text.strip()) >= 200:
        return text, False, None
    text, words = ocr_pdf(data)
    return text, True, words


def _snippets(text: str, n: int = 4) -> list[str]:
    parts = [s.strip() for s in re.split(r"(?<=[.;:])\s+", re.sub(r"\s+", " ", text).strip())]
    parts = [p for p in parts if len(p) >= 25] or [text.strip()]
    return [p[:90] for p in parts[:n]]


def _merge_rows(boxes: list[dict]) -> list[list[float]]:
    """One rect per text line: OCR gives a box per word, panels look better per row."""
    rows: list[list[dict]] = []
    for b in sorted(boxes, key=lambda b: (b["y"], b["x"])):
        if rows and abs(b["y"] - rows[-1][0]["y"]) < b["h"] * 0.6:
            rows[-1].append(b)
        else:
            rows.append([b])
    out = []
    for row in rows:
        x0 = min(b["x"] for b in row)
        x1 = max(b["x"] + b["w"] for b in row)
        y0 = min(b["y"] for b in row)
        y1 = max(b["y"] + b["h"] for b in row)
        out.append([round(x0 * 100, 2), round(y0 * 100, 2),
                    round((x1 - x0) * 100, 2), round((y1 - y0) * 100, 2)])
    return out[:40]


def _ocr_marks(pages: list[list[dict]], clauses: list[dict]) -> list[dict]:
    """Find each flagged clause in the OCR words and box the matched rows."""
    marks = []
    for c in clauses:
        for n, words in enumerate(pages, 1):
            if not words:
                continue
            starts, pos = [], 0
            for w in words:
                starts.append(pos)
                pos += len(w["text"]) + 1
            joined = " ".join(w["text"] for w in words)
            hit_ids: set[int] = set()
            for snip in _snippets(c["text"]):
                for size in (90, 60, 40):
                    hit = joined.find(snip[:size])
                    if hit < 0:
                        continue
                    end = hit + len(snip[:size])
                    hit_ids |= {i for i, s in enumerate(starts)
                                if s < end and s + len(words[i]["text"]) > hit}
                    break
            if hit_ids:
                marks.append({"page": n, "clause_id": c["id"], "severity": c["severity"],
                              "rects": _merge_rows([words[i] for i in sorted(hit_ids)])})
    return marks


def pdf_marks(data: bytes, clauses: list[dict], ocr: list[list[dict]] | None = None,
              max_pages: int = 8) -> dict:
    """Page thumbnails plus percent-positioned rects for flagged clauses.

    With ocr word boxes the boxes are matched against OCR text (scans); otherwise
    against the PDF's own text layer. Empty when nothing is flagged.
    """
    import pymupdf

    flagged = [c for c in clauses if c.get("severity") and c["text"].strip()]
    if not flagged:
        return {}
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return {}
    marks, shots = [], []
    with doc:
        if ocr is not None:
            marks = _ocr_marks(ocr, flagged)
        else:
            texts = [re.sub(r"\s+", " ", p.get_text()) for p in doc]
            for c in flagged:
                for n, page in enumerate(doc, 1):
                    rects = []
                    for snip in _snippets(c["text"]):
                        if snip[:40] not in texts[n - 1]:
                            continue
                        for size in (90, 60, 40):
                            found = page.search_for(snip[:size])
                            if found:
                                rects += found
                                break
                    if not rects:
                        continue
                    w, h = page.rect.width, page.rect.height
                    marks.append({"page": n, "clause_id": c["id"], "severity": c["severity"],
                                  "rects": [[round(r.x0 / w * 100, 2), round(r.y0 / h * 100, 2),
                                             round((r.x1 - r.x0) / w * 100, 2),
                                             round((r.y1 - r.y0) / h * 100, 2)] for r in rects[:40]]})
        for n in sorted({m["page"] for m in marks})[:max_pages]:
            pix = doc[n - 1].get_pixmap(dpi=90)
            shots.append({"page": n, "img": "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()})
    kept = {s["page"] for s in shots}
    return {"pages": shots, "marks": [m for m in marks if m["page"] in kept],
            "truncated": len({m["page"] for m in marks}) > max_pages}
