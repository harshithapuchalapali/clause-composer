import re

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[ID_NUMBER]"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\d{10}(?!\d)"), "[PHONE]"),
]
PARTIES = re.compile(r"between\s+(.+?)\s*\(?(?:the\s+)?[\"“]?landlord[\"”]?\)?\s*,?\s*and\s+(.+?)\s*\(?(?:the\s+)?[\"“]?tenant", re.I | re.S)


def find_party_names(text: str):
    m = PARTIES.search(text[:1500])
    return [re.sub(r"\s+", " ", g).strip(" ,.") for g in m.groups()] if m else []


def redact(text: str, full_text: str | None = None) -> str:
    """Remove personal data before text is sent to any LLM."""
    names = find_party_names(full_text or text)
    if len(names) == 2:
        for name, tag in zip(names, ("LANDLORD", "TENANT")):
            if name:
                text = re.sub(re.escape(name), tag, text, flags=re.I)
    for pat, tag in PATTERNS:
        text = pat.sub(tag, text)
    return text
