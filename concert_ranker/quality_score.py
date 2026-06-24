"""Absolute quality score — a standalone 0-100 score + A+..F letter grade.

Unlike the within-family ranking (which only says which transfer of one show is
best), this gives every recording an absolute grade by predicting the LB rating
rank from its metrics via the fitted :data:`config.QUALITY_MODEL` ridge model.
Held-out (5-fold CV) correlation to the real LB rating: Spearman 0.65, 93% within
one letter tier. Reads only stored metrics — no audio — so it reranks for free.
"""
from __future__ import annotations

from concert_ranker.calibrate import RATING_RANK
from concert_ranker.config import QUALITY_MODEL

_RANK_TO_LETTER = {v: k for k, v in RATING_RANK.items()}
_MIN_RANK, _MAX_RANK = min(RATING_RANK.values()), max(RATING_RANK.values())


def predict_rank(metrics: dict) -> float:
    """Predicted LB rating rank (1=F .. 13=A+) for one recording's raw metrics.

    Missing/NaN metrics fall back to the model's training median for that metric.
    """
    m = QUALITY_MODEL
    rank = m["intercept"]
    for i, name in enumerate(m["predictors"]):
        v = metrics.get(name)
        if v is None or (isinstance(v, float) and v != v):  # None or NaN
            v = m["median"][i]
        z = (v - m["mean"][i]) / m["std"][i]
        rank += m["weights"][i] * z
    return max(_MIN_RANK, min(_MAX_RANK, rank))


def grade(metrics: dict) -> tuple[float, str, float]:
    """Return ``(score_0_100, letter, predicted_rank)`` for a recording.

    ``score`` is the predicted rank mapped linearly to 0-100; ``letter`` is the
    nearest A+..F sub-grade.
    """
    rank = predict_rank(metrics)
    score = (rank - _MIN_RANK) / (_MAX_RANK - _MIN_RANK) * 100.0
    letter = _RANK_TO_LETTER[round(rank)]
    return score, letter, rank
