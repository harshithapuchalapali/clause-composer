import re

HEAD = re.compile(r"^\s*(?:clause\s+)?(\d{1,2})[.)]\s+\S", re.I)


def segment(text: str) -> list[dict]:
    """Split an agreement into numbered clauses; fall back to paragraphs."""
    clauses: list[str] = []
    cur = None
    for ln in text.replace("\r", "").split("\n"):
        if HEAD.match(ln):
            if cur:
                clauses.append(cur)
            cur = ln.strip()
        elif cur is not None and ln.strip():
            cur += " " + ln.strip()  # sub-points (1.1, (a)) merge into parent
    if cur:
        clauses.append(cur)
    if len(clauses) < 3:
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        clauses = []
        for p in paras:
            if clauses and len(p) < 40:
                clauses[-1] += " " + p
            else:
                clauses.append(p)
    return [{"id": f"c{i + 1}", "text": t} for i, t in enumerate(clauses)]
