"""HTTP layer: app setup and routes. Business logic lives in the sibling modules."""
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import law
from .analyze import analyze_text, negotiation_message
from .explain import explain_clause
from .pdf import pdf_marks, pdf_to_text
from .simulator import cost_series, simulate

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "backend" / "data" / "sample_agreement.txt"
MAX_BYTES = 8 * 1024 * 1024
DISCLAIMER = "Informational only, not legal advice."

app = FastAPI(title="Clause Compass")


@app.on_event("startup")
def warm_law_index():
    threading.Thread(target=law._index, daemon=True).start()


def attach_law(risks: list[dict]) -> None:
    try:
        for r, hits in zip(risks, law.search([f"{r['title']}. {r['reason']}" for r in risks], 1)):
            r["law"] = hits
    except Exception:
        pass  # law retrieval is an add-on; never fail the analysis


@app.get("/")
def home():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/sample")
def sample():
    return {"text": SAMPLE.read_text(encoding="utf-8")}


@app.post("/api/analyze")
async def analyze(file: UploadFile | None = File(None), text: str | None = Form(None)):
    used_ocr, data, ocr_words = False, b"", None
    if file is not None:
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "File too large (max 8 MB).")
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(415, "Only PDF files or pasted text are supported.")
        text, used_ocr, ocr_words = pdf_to_text(data)
    if not text or len(text.strip()) < 50:
        raise HTTPException(400, "OCR could not read this scan. Try a sharper image, or paste the text."
                            if used_ocr else "Provide a PDF or paste the agreement text.")
    result = analyze_text(text)
    attach_law(result["risks"])
    return {**result, "disclaimer": DISCLAIMER, "ocr": used_ocr, "text": text if used_ocr else "",
            "pdf": {} if not data else pdf_marks(data, result["clauses"], ocr_words)}


class SimIn(BaseModel):
    rent: float
    deposit: float = 0
    lockin_months: float = 0
    notice_days: float = 30
    months_stayed: float = 0
    penalty_months: float = 0
    penalty_remaining: bool = False
    fixed_deductions: float = 0


@app.post("/api/simulate")
def simulate_route(b: SimIn):
    kw = dict(penalty_months=b.penalty_months, penalty_remaining=b.penalty_remaining,
              fixed_deductions=b.fixed_deductions)
    return {"result": simulate(b.rent, b.deposit, b.lockin_months, b.notice_days, b.months_stayed, **kw),
            "series": cost_series(b.rent, b.deposit, b.lockin_months, b.notice_days, **kw),
            "assumptions": "Cost includes rent for the notice period. Based on the terms you confirmed.",
            "disclaimer": DISCLAIMER}


class NegIn(BaseModel):
    risks: list[dict]


@app.post("/api/negotiate")
def negotiate(b: NegIn):
    return {"message": negotiation_message(b.risks)}


class ExplainIn(BaseModel):
    text: str
    title: str = ""
    severity: str = ""
    law: dict | None = None


@app.post("/api/explain")
def explain_route(b: ExplainIn):
    if len(b.text.strip()) < 15:
        raise HTTPException(400, "Clause is too short to explain.")
    return {"explanation": explain_clause(b.text[:6000], b.title, b.severity, b.law)}
