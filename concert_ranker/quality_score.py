"""Absolute quality score — a standalone 0-100 score + A+..F letter grade.

Unlike the within-family ranking (which only says which transfer of one show is
best), this gives every recording an absolute grade by predicting the LB rating
rank from its metrics via a fitted ridge model: :data:`config.QUALITY_MODEL`
(AUD/default) or :data:`config.QUALITY_MODEL_SBD` (SBD/FM — the AUD curve sits
at the wrong absolute level for soundboards, see config.py). Held-out (5-fold
CV) correlation to the real LB rating: AUD Spearman 0.664 / 75.9% within one tier
(9 predictors including dff_vert_occ); SBD Spearman 0.53 / 69% within one tier. Reads only stored metrics — no audio —
so it reranks for free.
"""
from __future__ import annotations

from concert_ranker.calibrate import RATING_RANK
from concert_ranker.config import QUALITY_MODEL, QUALITY_MODEL_SBD

_RANK_TO_LETTER = {v: k for k, v in RATING_RANK.items()}
_MIN_RANK, _MAX_RANK = min(RATING_RANK.values()), max(RATING_RANK.values())


def _model_for(source_class: str | None) -> dict:
    return QUALITY_MODEL_SBD if source_class in ("SBD", "FM") else QUALITY_MODEL


def predict_rank(metrics: dict, source_class: str | None = None) -> float:
    """Predicted LB rating rank (1=F .. 13=A+) for one recording's raw metrics.

    Missing/NaN metrics fall back to the model's training median for that metric.
    ``source_class`` selects the AUD or SBD/FM model; unknown/None uses AUD.
    """
    m = _model_for(source_class)
    rank = m["intercept"]
    for i, name in enumerate(m["predictors"]):
        v = metrics.get(name)
        if v is None or (isinstance(v, float) and v != v):  # None or NaN
            v = m["median"][i]
        z = (v - m["mean"][i]) / m["std"][i]
        rank += m["weights"][i] * z
    return max(_MIN_RANK, min(_MAX_RANK, rank))


def grade(metrics: dict, source_class: str | None = None) -> tuple[float, str, float]:
    """Return ``(score_0_100, letter, predicted_rank)`` for a recording.

    ``score`` is the predicted rank mapped linearly to 0-100; ``letter`` is the
    nearest A+..F sub-grade. ``source_class`` selects the AUD or SBD/FM model.
    """
    rank = predict_rank(metrics, source_class)
    score = (rank - _MIN_RANK) / (_MAX_RANK - _MIN_RANK) * 100.0
    letter = _RANK_TO_LETTER[round(rank)]
    return score, letter, rank
