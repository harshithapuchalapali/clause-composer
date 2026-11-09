from .classify import classify, LABELS
from .risk_rules import run_rules, summarize, SEV
from .segment import segment
from .terms import extract_terms


def analyze_text(text: str) -> dict:
    clauses = segment(text)
    for c in clauses:
        c["type"] = classify(c["text"])
        c["label"] = LABELS[c["type"]]
    ext = extract_terms(clauses)
    risks = run_rules(clauses, ext["terms"])
    for c in clauses:
        c["risks"] = [r["rule_id"] for r in risks if r["clause_id"] == c["id"]]
        c["severity"] = max((r["severity"] for r in risks if r["clause_id"] == c["id"]),
                            key=lambda s: SEV[s], default=None)
    return {"clauses": clauses, "terms": ext["terms"], "warnings": ext["warnings"],
            "risks": risks, "summary": summarize(risks)}


def negotiation_message(risks: list[dict], max_items: int = 3) -> str:
    top = sorted(risks, key=lambda r: -SEV[r["severity"]])[:max_items]
    if not top:
        return "Hi, thank you for the agreement. I have reviewed it and have no changes to request."
    lines = ["Hi,", "", "Thank you for sharing the draft agreement. Before signing, I would like to discuss a few points:", ""]
    for i, r in enumerate(top, 1):
        lines.append(f"{i}. {r['title']} ({r['clause_id'].replace('c', 'clause ')}): {r['ask']}")
    lines += ["", "I am happy to find a middle ground on any of these. Thank you for your time.", "", "Regards"]
    return "\n".join(lines)
