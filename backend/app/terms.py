import re

MONEY = re.compile(r"(?:rs\.?|inr|₹|\$)\s*([\d,]+(?:\.\d+)?)", re.I)
DUR = re.compile(r"(\d+)\s*\)?\s*(months?|days?)", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_WORDS = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.I)


def _words(t):
    """Spell out as digits so the regexes below see "ten months" as "10 months"."""
    return _WORDS.sub(lambda m: WORDS[m.group(1).lower()], t)


def _money(t):
    m = MONEY.search(t)
    return float(m.group(1).replace(",", "")) if m else None


def _days(t):
    m = DUR.search(t)
    if not m:
        return None
    n = int(m.group(1))
    return n * 30 if m.group(2).lower().startswith("month") else n


def extract_terms(clauses: list[dict]) -> dict:
    """clauses need 'text' and 'type'. Returns terms + warnings (user can edit)."""
    t = dict(rent=None, deposit=None, deposit_months=None, lockin_months=None,
             notice_days=None, escalation_pct=None, penalty_months=0,
             penalty_remaining=False, fixed_deductions=0)
    for c in clauses:
        x, low = _words(c["text"]), _words(c["text"]).lower()
        if t["rent"] is None and any(k in low for k in ("monthly rent", "rent of", "rent shall be")):
            t["rent"] = _money(x)
        if c["type"] == "security_deposit":
            if t["deposit"] is None:
                t["deposit"] = _money(x)
            m = re.search(r"(\d+)\s*\)?\s*months?'?\s*(?:of\s+)?(?:the\s+)?(?:monthly\s+)?rent", low)
            if m and t["deposit_months"] is None:
                t["deposit_months"] = float(m.group(1))
        if t["lockin_months"] is None:
            # Not gated on type: "may not terminate before 11 months" is a lock-in too.
            m = re.search(r"(?:lock[-\s]?in|may not terminate|before)[^.]{0,40}?(\d+)\s*\)?\s*months?", low)
            if m:
                t["lockin_months"] = int(m.group(1))
        if "notice" in low and t["notice_days"] is None and c["type"] != "landlord_entry":
            t["notice_days"] = _days(x)
        if t["escalation_pct"] is None and any(k in low for k in ("increase", "escalat", "enhance")):
            m = PCT.search(x)
            if m:
                t["escalation_pct"] = float(m.group(1))
        if c["type"] in ("lock_in", "termination"):
            if "remaining" in low and "rent" in low:
                t["penalty_remaining"] = True
            m = re.search(r"(?:penalty|compensation|damages)[^.]{0,60}?(\d+)\s*\)?\s*months?'?\s*rent", low)
            if m:
                t["penalty_months"] = int(m.group(1))
    if t["deposit"] is None and t["deposit_months"] and t["rent"]:
        t["deposit"] = t["deposit_months"] * t["rent"]
    if t["deposit_months"] is None and t["deposit"] and t["rent"]:
        t["deposit_months"] = round(t["deposit"] / t["rent"], 1)
    warnings = []
    if t["deposit_months"] and t["deposit_months"] > 24:
        warnings.append("Deposit is over 24 months of rent: probably an extraction error. Please check.")
    for k in ("rent", "lockin_months", "notice_days"):
        if t[k] is None:
            warnings.append(f"Could not find '{k}'. Please fill it in.")
    return {"terms": t, "warnings": warnings}
