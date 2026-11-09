# Sample PDFs

Upload these on the app's upload box to exercise each path.

| File | PDF type | Expected result |
|---|---|---|
| `risky-agreement.pdf` | Digital (text layer) | 4 high + 5 medium risks, 6 highlighted boxes, terms prefilled (rent 20000, deposit 6 months, lock-in 24, notice 60 days) |
| `fair-agreement.pdf` | Digital (text layer) | No risks; deposit 2 months, lock-in 6 months |
| `risky-agreement-scanned.pdf` | Image only (no text layer) | Same 9 risks as the risky file, but goes through Tesseract OCR (`ocr: true`) and shows no highlights |

The scanned file needs Tesseract installed (see the root README). Both risky files are built from `backend/data/sample_agreement.txt`, so the flagged clauses match the test suite's expectations.
