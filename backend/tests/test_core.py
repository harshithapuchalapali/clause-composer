import io

import pytest
from fastapi.testclient import TestClient

from app import law
from app.analyze import analyze_text
from app.main import app, SAMPLE
from app.redact import redact
from app.segment import segment
from app.simulator import simulate


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch):
    """Keep tests offline: law search uses its keyword fallback."""
    monkeypatch.setattr(law, "_embed", lambda texts: None)
    law._state.clear()
    yield
    law._state.clear()

FAIR = """1. Rent. The monthly rent shall be Rs. 20,000 payable monthly.
2. Security Deposit. Deposit of Rs. 40,000 (2 months of rent), refunded within 30 days of handover. Deductions only for documented damage.
3. Lock-in Period. There is a lock-in period of 6 months.
4. Notice. Either party gives 1 month notice.
5. Inspection. Landlord may inspect with 24 hours notice."""


def test_segment_numbered_and_subpoints():
    cl = segment("1. Rent is due.\n1.1 On the 5th.\n2. Deposit.\n3. Lock-in.")
    assert len(cl) == 3 and "On the 5th" in cl[0]["text"]


def test_segment_fallback_paragraphs():
    cl = segment("First paragraph about rent and payment terms here.\n\nSecond paragraph about the security deposit refund.")
    assert len(cl) == 2


def test_sample_flags_expected_rules():
    r = analyze_text(SAMPLE.read_text(encoding="utf-8"))
    ids = {x["rule_id"] for x in r["risks"]}
    assert {"long_lockin", "exit_penalty", "high_deposit", "vague_deductions", "no_refund_deadline",
            "unlimited_escalation", "tenant_pays_all_repairs", "entry_no_notice",
            "immediate_eviction"} <= ids
    t = r["terms"]
    assert (t["rent"], t["lockin_months"], t["notice_days"], t["deposit_months"]) == (20000, 24, 60, 6)


def test_fair_agreement_has_no_risks():
    assert analyze_text(FAIR)["risks"] == []


def test_redaction():
    txt = "between Ramesh Kumar (the Landlord) and Anita Rao (the Tenant). Mail ramesh@example.com call 9876543210, PAN ABCDE1234F"
    out = redact(txt)
    for bad in ("Ramesh", "Anita", "ramesh@", "9876543210", "ABCDE1234F"):
        assert bad not in out
    assert "LANDLORD" in out and "TENANT" in out


def test_simulator_hand_calculated():
    r = simulate(20000, 60000, 11, 60, 5, penalty_remaining=True, fixed_deductions=3000)
    assert r["rent_owed"] == 120000 and r["total_cost"] == 123000
    assert r["net_deposit_refund"] == 0 and r["out_of_pocket"] == 63000
    r = simulate(20000, 60000, 11, 60, 12, penalty_remaining=True)
    assert r["total_cost"] == 40000 and r["net_deposit_refund"] == 20000


def test_api():
    c = TestClient(app)
    assert c.get("/api/health").json() == {"ok": True}
    text = c.get("/api/sample").json()["text"]
    res = c.post("/api/analyze", data={"text": text}).json()
    assert res["summary"]["high"] >= 1
    sim = c.post("/api/simulate", json={"rent": 20000, "deposit": 120000, "lockin_months": 24,
                                        "notice_days": 60, "months_stayed": 3,
                                        "penalty_remaining": True}).json()
    assert sim["result"]["total_cost"] == 20000 * 21
    msg = c.post("/api/negotiate", json={"risks": res["risks"]}).json()["message"]
    assert "lock-in" in msg.lower()
    assert any(r["law"] for r in res["risks"])
    assert c.post("/api/analyze", data={"text": "x"}).status_code == 400


def test_law_retrieval_prefers_deposit_rules():
    hits = law.search(["High security deposit of six months of rent"], 1)[0]
    assert hits and hits[0]["id"] in ("deposit-cap", "deposit-refund")


def _scan_pdf(lines):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("arial.ttf", 44)
    img = Image.new("RGB", (1500, 120 + 80 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((50, 50 + i * 75), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=200)
    return buf.getvalue()


def test_scanned_pdf_falls_back_to_ocr():
    import os
    from pathlib import Path

    import pytesseract
    cmd = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if Path(cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract is not installed")
    pdf = _scan_pdf([
        "1. Rent. The monthly rent shall be Rs. 20000 payable monthly.",
        "2. Security Deposit. Deposit of Rs. 120000 is 6 months of rent.",
        "3. Lock-in Period. There is a lock-in period of 24 months.",
        "4. Notice. Either party gives 2 months notice after the lock-in period.",
        "5. Inspection. The Landlord may enter the premises at any time.",
    ])
    res = TestClient(app).post("/api/analyze", files={"file": ("scan.pdf", pdf, "application/pdf")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ocr"] is True and body["text"].strip() and body["risks"]
    marks = body["pdf"].get("marks") or []
    assert marks, "scanned PDF should get OCR-positioned highlights"
    for m in marks:
        for x, y, w, h in m["rects"]:
            assert 0 <= x <= 100 and 0 <= y <= 100 and 0 < w <= 100 and 0 < h <= 100


def test_explain_prompt_and_route(monkeypatch):
    from app import main
    from app.explain import build_prompt
    assert "24 months" in build_prompt("Lock-in of 24 months.", "Long lock-in", "high")
    monkeypatch.setattr(main, "explain_clause", lambda *a: "Plain English answer.")
    c = TestClient(main.app)
    r = c.post("/api/explain", json={"text": "Lock-in period of 24 months applies.", "title": "Long lock-in", "severity": "high"})
    assert r.status_code == 200 and r.json()["explanation"] == "Plain English answer."
    assert c.post("/api/explain", json={"text": "hi"}).status_code == 400


def test_pdf_marks_map_flagged_clause_to_page():
    import pymupdf
    from app.pdf import pdf_marks
    doc = pymupdf.open()
    page = doc.new_page()
    text = "There is a lock-in period of 24 months."
    page.insert_text((60, 80), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    out = pdf_marks(data, [{"id": "c3", "text": text, "severity": "high"}])
    assert out["pages"][0]["page"] == 1
    assert out["pages"][0]["img"].startswith("data:image/png;base64,")
    m = out["marks"][0]
    assert m["clause_id"] == "c3" and m["severity"] == "high" and m["rects"]
    x, y, w, h = m["rects"][0]
    assert 0 <= x < 100 and 0 <= y < 100 and 0 < w <= 100 and 0 < h <= 100


def test_pdf_marks_empty_without_flags():
    from app.pdf import pdf_marks
    assert pdf_marks(b"", [{"id": "c1", "text": "Rent is due.", "severity": None}]) == {}


def test_terms_read_number_words_and_ungated_lockin():
    from app.terms import extract_terms
    t = extract_terms([
        {"text": "The Tenant shall pay a security deposit equal to ten months rent.", "type": "security_deposit"},
        {"text": "The Tenant may not terminate this agreement before 11 months.", "type": "security_deposit"},
        {"text": "A penalty of two months rent is payable.", "type": "termination"},
    ])["terms"]
    assert (t["deposit_months"], t["lockin_months"], t["penalty_months"]) == (10.0, 11, 2)


def test_classify_prefers_the_clause_matching_more_keywords():
    from app.classify import classify
    assert classify("Security deposit of 2 months.") == "security_deposit"
    assert classify("The Tenant may not terminate; if the Tenant vacates early the deposit is forfeited.") == "termination"


def test_explain_prompt_does_not_ask_for_a_section():
    from app.explain import build_prompt
    p = build_prompt("Landlord may enter at any time.", "Entry", "high",
                     {"act": "Model Tenancy Act, 2021", "ref": "landlord's right to enter", "text": "Prior notice."})
    assert "landlord's right to enter" in p and "Never add a section number" in p
