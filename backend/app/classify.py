LABELS = {
    "lock_in": "Lock-in period",
    "security_deposit": "Security deposit",
    "rent_escalation": "Rent increase",
    "landlord_entry": "Landlord entry",
    "termination": "Termination / eviction",
    "repairs": "Repairs & maintenance",
    "subletting": "Subletting",
    "notice_period": "Notice period",
    "rent": "Rent & payment",
    "utilities": "Utilities",
    "other": "Other",
}
# Order = priority. First type with a matching keyword wins.
RULES = [
    ("lock_in", ["lock-in", "lock in", "lockin"]),
    ("security_deposit", ["security deposit", "deposit"]),
    ("rent_escalation", ["escalat", "increase", "enhance", "hike"]),
    ("landlord_entry", ["inspect", "enter the premises", "right of entry", "access to the premises"]),
    ("termination", ["terminate", "termination", "evict", "vacate"]),
    ("repairs", ["repair", "maintenance"]),
    ("subletting", ["sublet", "sub-let", "assign"]),
    ("notice_period", ["notice"]),
    ("rent", ["monthly rent", "rent of", "rent shall", "payable"]),
    ("utilities", ["electricity", "water", "utility", "utilities"]),
]


def classify(text: str) -> str:
    t = text.lower()
    scores = {ctype: sum(k in t for k in kws) for ctype, kws in RULES}
    best = max(scores, key=scores.get)  # ties keep RULES order (max returns the first)
    return best if scores[best] else "other"
