import re

RULES = []
SEV = {"high": 3, "medium": 2, "low": 1}


def rule(fn):
    RULES.append(fn)
    return fn


def _first(clauses, ctype):
    return next((c for c in clauses if c["type"] == ctype), None)


def _risk(rid, c, sev, title, reason, ask):
    return {"rule_id": rid, "clause_id": c["id"], "severity": sev, "title": title,
            "reason": reason, "ask": ask}


@rule
def long_lockin(clauses, terms):
    n, c = terms.get("lockin_months"), _first(clauses, "lock_in")
    if n and c and n > 11:
        return [_risk("long_lockin", c, "high" if n >= 24 else "medium", "Long lock-in period",
                      f"Lock-in is {n} months, above the 11-month level that is commonly seen.",
                      "Ask to reduce the lock-in to 6 months, or allow exit after 6 months with notice.")]
    return []


@rule
def exit_penalty(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] in ("lock_in", "termination") and re.search(
                r"remaining|penalty|forfeit|liquidated|compensation", low) and "rent" in low:
            if re.search(r"landlord[^.]{0,40}(shall|will|agrees)[^.]{0,60}(pay|compensat|refund)", low):
                continue
            sev = "high" if "remaining" in low else "medium"
            out.append(_risk("exit_penalty", c, sev, "One-sided exit penalty",
                             "The tenant must pay a penalty or remaining rent if leaving early, with no matching duty on the landlord.",
                             "Ask to cap the penalty at 1 month's rent, and add the same penalty if the landlord ends the tenancy early."))
    return out


@rule
def high_deposit(clauses, terms):
    m, c = terms.get("deposit_months"), _first(clauses, "security_deposit")
    if m and c and m > 3:
        return [_risk("high_deposit", c, "high" if m > 6 else "medium", "High security deposit",
                      f"Deposit is about {m:g} months of rent. 2 to 3 months is a common range.",
                      "Ask to reduce the deposit to 2 or 3 months of rent.")]
    return []


@rule
def vague_deductions(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] == "security_deposit" and re.search(
                r"deemed fit|sole discretion|at the discretion|as it may deem|any and all", low):
            out.append(_risk("vague_deductions", c, "medium", "Vague deposit deductions",
                             "Deductions depend on the landlord's judgement without a list or proof.",
                             "Ask that deductions be limited to documented damage beyond normal wear, with bills or photos shown."))
    return out


@rule
def no_refund_deadline(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] == "security_deposit" and not re.search(
                r"within\s+(?:\w+\s*)?\(?\d+|\d+\s*\)?\s*days", low):
            out.append(_risk("no_refund_deadline", c, "medium", "No deposit refund deadline",
                             "The clause gives no number of days in which the deposit must be returned.",
                             "Ask to add: deposit refunded within 30 days of handing over the keys."))
    return out


@rule
def unlimited_escalation(clauses, terms):
    out = []
    for c in clauses:
        if c["type"] == "rent_escalation" and "%" not in c["text"]:
            out.append(_risk("unlimited_escalation", c, "medium", "Rent increase has no cap",
                             "The rent can rise with no stated percentage or schedule.",
                             "Ask for a fixed increase (for example 5% once a year) written into the agreement."))
    return out


@rule
def entry_no_notice(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] == "landlord_entry" and ("any time" in low or "without notice" in low or "notice" not in low):
            out.append(_risk("entry_no_notice", c, "high" if "any time" in low else "medium",
                             "Landlord entry without notice",
                             "The landlord may enter without advance notice.",
                             "Ask for at least 24 hours' notice, except in emergencies, at reasonable hours."))
    return out


@rule
def immediate_eviction(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] == "termination" and "landlord" in low and re.search(
                r"immediate|forthwith|without (?:any )?notice", low):
            out.append(_risk("immediate_eviction", c, "high", "Termination without notice",
                             "The landlord can end the tenancy immediately, with no notice or time to fix a problem.",
                             "Ask for a written notice and a 15-day period to fix any breach before termination."))
    return out


@rule
def tenant_pays_all_repairs(clauses, terms):
    out = []
    for c in clauses:
        low = c["text"].lower()
        if c["type"] == "repairs" and "tenant" in low and re.search(
                r"all (?:repairs|maintenance)|any and all repair|entire cost", low) and not re.search(
                r"structural|major|landlord shall", low):
            out.append(_risk("tenant_pays_all_repairs", c, "medium", "Tenant pays for all repairs",
                             "There is no split between minor repairs and structural or major repairs.",
                             "Ask that the landlord bears structural and major repairs, and the tenant only minor ones."))
    return out


def run_rules(clauses, terms):
    risks = []
    for fn in RULES:
        risks.extend(fn(clauses, terms))
    risks.sort(key=lambda r: -SEV[r["severity"]])
    return risks


def summarize(risks):
    n = {s: sum(r["severity"] == s for r in risks) for s in SEV}
    return {**n, "text": f"{n['high']} high, {n['medium']} medium, {n['low']} low"}
