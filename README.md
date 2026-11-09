---
title: Clause Compass
emoji: 🧭
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Clause Compass (MVP)

Rental agreement risk analyzer: clause highlighting, rule-based risk flags, key terms, leave-early cost simulator, negotiation message. Informational only, not legal advice.

## Run (Windows 10)
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 and click "Try a sample agreement".

To test the PDF upload path, use the PDFs in `samples/` (see `samples/README.md`).

## Built
Digital PDF + pasted text, OCR for scanned PDFs (Tesseract), segmentation, classification, term extraction, 9 risk rules, law-text retrieval (FAISS over `data/law/tenancy.json`, Gemini embeddings, keyword fallback offline), Gemini clause explanations grounded in the retrieved law, redaction module, simulator (tested by hand-calculated cases), negotiation draft, responsive UI.

## Highlights and report export
For PDFs with a text layer, `/api/analyze` also returns the flagged clauses' positions: the pages that carry a flag are rendered at 90 dpi (first 8 such pages) and each match is drawn as a coloured box over the page, severity-tinted, clickable to jump to the risk card. Scanned (OCR) PDFs have no text layer, so the clauses are matched against the OCR word boxes instead (words below confidence 60 are dropped, matches on one line are merged into a strip). "Download report (PDF)" opens the browser print dialog with a print stylesheet that flattens the result into a clean document.

## OCR
Install Tesseract once, then restart the server:
```
winget install UB-Mannheim.TesseractOCR
```
The app looks for `C:\Program Files\Tesseract-OCR\tesseract.exe`; set `TESSERACT_CMD` for another path. PDFs with no text layer go through OCR automatically and the extracted text is shown back in the paste box for correction.

## Law retrieval
`data/law/tenancy.json` holds short, curated summaries (not verbatim statute). Replace or extend it with your state's Act text. Each risk card shows its best-matching passage, and the AI explanation is given that passage to cite.

## AI explanations
Set `GEMINI_API_KEY` in `backend/.env` (gitignored) or the environment. Optional `GEMINI_MODEL` overrides the default `gemini-3.1-flash-lite`; `GEMINI_EMBED_MODEL` overrides the embedding model.

## Not built yet (from the doc)
CI.
