import json
import os
import re
from pathlib import Path

import httpx

from .explain import api_key

CORPUS = Path(__file__).resolve().parents[1] / "data" / "law" / "tenancy.json"
EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
MIN_SCORE = 0.62

STOP = set("""the a an of to and or in on for with by is are be as at from that this it its if any not no shall
may must can will which who whose other than also such into under over been has have had does do did but
""".lower().split())

_state: dict = {}


def docs() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))["docs"]


def _embed(texts: list[str]) -> list[list[float]] | None:
    """Gemini embeddings, or None when there is no key / no network."""
    key = api_key()
    if not key:
        return None
    out = []
    for i in range(0, len(texts), 100):  # batchEmbedContents caps requests at 100
        chunk = texts[i:i + 100]
        try:
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:batchEmbedContents",
                params={"key": key}, timeout=60,
                json={"requests": [{"model": f"models/{EMBED_MODEL}",
                                    "content": {"parts": [{"text": t}]}} for t in chunk]},
            )
            r.raise_for_status()
            out.extend(e["values"] for e in r.json()["embeddings"])
        except (httpx.HTTPError, KeyError, TypeError):
            return None
    return out


def _index():
    """Lazily embed the corpus into a FAISS index; None index means keyword fallback."""
    if "index" not in _state:
        d = docs()
        try:
            import faiss
            import numpy as np
            vecs = _embed([f"{x['title']}. {x['text']}" for x in d])
            if vecs:
                m = np.array(vecs, dtype="float32")
                faiss.normalize_L2(m)
                ix = faiss.IndexFlatIP(m.shape[1])
                ix.add(m)
                _state["index"], _state["docs"] = ix, d
            else:
                _state["index"], _state["docs"] = None, d
        except ImportError:
            _state["index"], _state["docs"] = None, d
    return _state["index"], _state["docs"]


def _tokens(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", t.lower()) if w not in STOP}


def _keyword(query: str, d: list[dict], k: int) -> list[dict]:
    q = _tokens(query)
    scored = []
    for x in d:
        overlap = len(q & _tokens(x["title"] + " " + x["text"]))
        if overlap:
            scored.append((overlap / max(len(q), 1) ** 0.5, x))
    scored.sort(key=lambda p: -p[0])
    return [{**x, "score": round(s, 2)} for s, x in scored[:k] if s >= 1.1]


def search(queries: list[str], k: int = 1) -> list[list[dict]]:
    """Top legal summaries for each query. Empty list when nothing matches."""
    if not queries:
        return []
    ix, d = _index()
    if ix is not None:
        try:
            import faiss
            import numpy as np
            vecs = _embed(queries)
            if vecs:
                q = np.array(vecs, dtype="float32")
                faiss.normalize_L2(q)
                scores, ids = ix.search(q, k)
                return [[{**d[j], "score": round(float(s), 2)}
                         for s, j in zip(row_s, row_j) if s >= MIN_SCORE and j >= 0]
                        for row_s, row_j in zip(scores, ids)]
        except Exception:
            pass  # fall through to keyword search
    return [_keyword(q, d, k) for q in queries]
