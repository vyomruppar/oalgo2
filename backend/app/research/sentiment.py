"""Headline sentiment.

Two engines, both free and local:
  finbert  - ProsusAI/finbert, a BERT model fine-tuned on financial text (optional; `uv sync --group ai`).
             score = P(positive) - P(negative).
  lexicon  - a compact finance word list with simple negation handling. A statistical method, not AI;
             used when the model is not installed and always labelled as such.

A sentiment score describes the tone of a HEADLINE. It is not a forecast and has no backtest behind it,
which is why its weight in the research score is zero by default.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from ..config import get_settings

log = logging.getLogger(__name__)

POSITIVE = {
    "beat", "beats", "beating", "surge", "surges", "surged", "soar", "soars", "soared", "jump", "jumps", "jumped", "rally", "rallies",
    "rallied", "gain", "gains", "gained", "rise", "rises", "rose", "climb", "climbs", "climbed", "record", "upgrade", "upgrades",
    "upgraded", "outperform", "outperforms", "strong", "stronger", "strength", "growth", "grows", "profit", "profits", "profitable",
    "raises", "raised", "boost", "boosts", "boosted", "tops", "topped", "exceeds", "exceeded", "bullish", "buyback", "wins", "win",
    "approval", "approved", "breakthrough", "expands", "expansion", "rebound", "rebounds", "recovery", "recovers", "accelerates",
    "optimistic", "upside", "dividend", "hike", "hikes", "milestone", "robust", "momentum", "outpaces", "leads",
}
NEGATIVE = {
    "miss", "misses", "missed", "plunge", "plunges", "plunged", "slump", "slumps", "slumped", "drop", "drops", "dropped", "fall",
    "falls", "fell", "sink", "sinks", "sank", "tumble", "tumbles", "tumbled", "slide", "slides", "slid", "decline", "declines",
    "declined", "loss", "losses", "downgrade", "downgrades", "downgraded", "underperform", "weak", "weaker", "weakness", "cut",
    "cuts", "slashes", "slashed", "lawsuit", "sued", "sues", "probe", "investigation", "fraud", "recall", "recalls", "warning",
    "warns", "warned", "layoffs", "layoff", "bankruptcy", "default", "bearish", "selloff", "crash", "crashes", "crashed", "fine",
    "fined", "penalty", "delay", "delays", "delayed", "halts", "halted", "concern", "concerns", "fears", "risk", "risks", "slowdown",
    "shortfall", "disappoints", "disappointing", "struggles", "struggling", "downside", "resigns", "ousted", "breach", "tariffs",
}
NEGATORS = {"not", "no", "never", "without", "fails", "failed", "despite", "isn't", "won't", "can't", "doesn't", "didn't"}


class Engine(Protocol):
    name: str
    description: str

    def score(self, texts: list[str]) -> list[tuple[float, str]]: ...


def label_of(score: float, threshold: float = 0.2) -> str:
    return "positive" if score >= threshold else "negative" if score <= -threshold else "neutral"


class LexiconEngine:
    name = "lexicon"
    description = "Finance word list with negation handling (statistical, not AI)"

    def score(self, texts: list[str]) -> list[tuple[float, str]]:
        out = []
        for t in texts:
            words = re.findall(r"[a-z']+", t.lower())
            pos = neg = 0
            for i, w in enumerate(words):
                flip = any(x in NEGATORS for x in words[max(0, i - 2): i])
                if w in POSITIVE:
                    pos, neg = (pos, neg + 1) if flip else (pos + 1, neg)
                elif w in NEGATIVE:
                    pos, neg = (pos + 1, neg) if flip else (pos, neg + 1)
            s = (pos - neg) / (pos + neg) if pos + neg else 0.0
            # one matching word is weak evidence: shrink towards neutral
            s *= min(1.0, (pos + neg) / 2.0) if pos + neg else 0.0
            out.append((float(s), label_of(s)))
        return out


FINBERT_REPO = "https://huggingface.co/ProsusAI/finbert/resolve/main/"
FINBERT_FILES = ["config.json", "vocab.txt", "tokenizer_config.json", "special_tokens_map.json", "model.safetensors"]


class FinBertEngine:
    name = "finbert"
    description = "FinBERT (ProsusAI/finbert), a language model fine-tuned on financial text, running locally"

    def __init__(self) -> None:
        import torch  # noqa: F401  (ImportError here means the optional group is not installed)
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        path = self._ensure_files()
        self._torch = torch
        self.tok = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True)
        self.model.eval()
        labels = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        self.i_pos = next(i for i, v in labels.items() if v == "positive")
        self.i_neg = next(i for i, v in labels.items() if v == "negative")

    @staticmethod
    def _ensure_files():
        import httpx
        st = get_settings()
        d = st.models_dir / "finbert"
        d.mkdir(parents=True, exist_ok=True)
        for f in FINBERT_FILES:
            p = d / f
            if p.exists() and p.stat().st_size > 0:
                continue
            log.info("downloading FinBERT file %s", f)
            tmp = p.with_suffix(p.suffix + ".part")
            with httpx.stream("GET", FINBERT_REPO + f, follow_redirects=True, timeout=600.0,
                              headers={"User-Agent": st.http_user_agent}) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
            tmp.replace(p)
        return d

    def score(self, texts: list[str]) -> list[tuple[float, str]]:
        out: list[tuple[float, str]] = []
        torch = self._torch
        for i in range(0, len(texts), 16):
            batch = texts[i:i + 16]
            enc = self.tok(batch, padding=True, truncation=True, max_length=64, return_tensors="pt")
            with torch.no_grad():
                p = torch.softmax(self.model(**enc).logits, dim=-1)
            for row in p:
                s = float(row[self.i_pos] - row[self.i_neg])
                out.append((s, label_of(s)))
        return out


_engine: Engine | None = None
_engine_note: str | None = None
_lock = threading.Lock()


def get_engine() -> Engine:
    """FinBERT when available (and not disabled), otherwise the word list. Chosen once per process."""
    global _engine, _engine_note
    with _lock:
        if _engine is not None:
            return _engine
        want = get_settings().sentiment_engine
        if want in ("auto", "finbert"):
            try:
                _engine = FinBertEngine()
                _engine_note = None
                return _engine
            except ImportError:
                _engine_note = "FinBERT is not installed (run `uv sync --group ai` in backend/). Using the word list."
            except Exception as e:  # download or load failure must not break a scan
                _engine_note = f"FinBERT could not be loaded ({type(e).__name__}: {e}). Using the word list."
                log.warning(_engine_note)
        _engine = LexiconEngine()
        return _engine


def reset_engine() -> None:
    global _engine, _engine_note
    with _lock:
        _engine, _engine_note = None, None


def engine_status() -> dict[str, Any]:
    e = get_engine()
    return {"engine": e.name, "description": e.description, "note": _engine_note, "is_ai": e.name == "finbert",
            "caveat": "Scores describe the tone of headlines only. They are not forecasts and are not used in the research score unless you give sentiment a weight."}


def aggregate(items: list[dict[str, Any]], now: datetime | None = None, half_life_days: float = 3.0) -> dict[str, Any]:
    """Recency- and relevance-weighted mean sentiment. `items` need sentiment, relevance, published_at."""
    now = now or datetime.now(timezone.utc)
    num = den = 0.0
    n = 0
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for it in items:
        s = it.get("sentiment")
        if s is None:
            continue
        ts = it["published_at"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = max((now - ts).total_seconds() / 86400.0, 0.0)
        w = float(it.get("relevance") or 1.0) * math.pow(0.5, age / half_life_days)
        num += w * float(s)
        den += w
        n += 1
        counts[it.get("sentiment_label") or label_of(float(s))] += 1
    if n == 0 or den <= 0:
        return {"score": None, "label": None, "n": 0, "counts": counts}
    score = num / den
    return {"score": score, "label": label_of(score, 0.15), "n": n, "counts": counts}
