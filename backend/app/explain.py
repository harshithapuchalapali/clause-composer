import os
from pathlib import Path

import httpx
from fastapi import HTTPException

ENV = Path(__file__).resolve().parents[1] / ".env"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key and ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"\'')
    return key


def build_prompt(text: str, title: str = "", severity: str = "", law: dict | None = None) -> str:
    ctx = f"This clause was flagged as: {title} ({severity} risk).\n" if title else ""
    cite = ""
    if law:
        cite = (f"Relevant law summary ({law.get('act', '')}, {law.get('ref', '')}): {law.get('text', '')}\n"
                "Use it only if it genuinely applies to this clause. Cite only the Act name and the "
                "reference text above, verbatim. Never add a section number that is not in it.\n")
    return (
        "You explain rental agreement clauses to a renter in plain English. "
        "Be concrete and brief: at most 3 short paragraphs, no headings, no lists, "
        "no legal advice. Say what the clause lets each side do, why it matters, "
        "and finish with one practical question the renter can ask the landlord.\n\n"
        f"{ctx}{cite}Clause:\n\"\"\"{text}\"\"\""
    )


def explain_clause(text: str, title: str = "", severity: str = "", law: dict | None = None) -> str:
    key = api_key()
    if not key:
        raise HTTPException(503, "AI explanation is not configured (missing GEMINI_API_KEY).")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    try:
        r = httpx.post(
            url, params={"key": key}, timeout=60,
            json={"contents": [{"parts": [{"text": build_prompt(text, title, severity, law)}]}],
                  "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500,
                                       "thinkingConfig": {"thinkingBudget": 0}}},
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as e:
        raise HTTPException(502, f"AI explanation failed: {str(e)[:120]}")
