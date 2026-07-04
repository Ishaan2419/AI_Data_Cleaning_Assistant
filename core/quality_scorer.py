"""
core/quality_scorer.py
-----------------------
Computes a single 0-100 "Data Quality Score" from a list of detected
issues, using the weights defined in config.settings.QUALITY_WEIGHTS.

The score starts at 100 and loses points proportional to how much of the
dataset each issue category affects, capped so a single issue category
can never single-handedly zero out the score.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple

from config.settings import QUALITY_WEIGHTS, QUALITY_LABELS
from core.issue_detector import Issue


@dataclass
class QualityScore:
    score: float
    label: str
    color: str
    breakdown: List[Tuple[str, float]]  # (category, points_lost)


def compute_quality_score(issues: List[Issue], n_rows: int, n_cols: int) -> QualityScore:
    """
    Compute an overall data quality score from detected issues.

    Args:
        issues: List of Issue objects produced by the issue detector.
        n_rows: Total row count of the dataset (for normalizing severity).
        n_cols: Total column count of the dataset.

    Returns:
        A QualityScore with the final score, a human label, a color, and
        a breakdown of points lost per issue category.
    """
    score = 100.0
    breakdown: List[Tuple[str, float]] = []

    # Group issues by category and take the max "affected ratio" per category
    # so multiple overlapping issues in the same family don't double-penalize.
    category_max_ratio: dict[str, float] = {}
    for issue in issues:
        ratio = issue.affected_ratio
        category = issue.category
        category_max_ratio[category] = max(category_max_ratio.get(category, 0.0), ratio)

    for category, ratio in category_max_ratio.items():
        weight = QUALITY_WEIGHTS.get(category, 5.0)
        points_lost = min(weight, weight * ratio * 3)  # amplify small issues slightly, cap at weight
        points_lost = round(points_lost, 2)
        if points_lost > 0:
            score -= points_lost
            breakdown.append((category, points_lost))

    score = max(0.0, min(100.0, round(score, 1)))
    label, color = _label_for_score(score)

    breakdown.sort(key=lambda x: x[1], reverse=True)
    return QualityScore(score=score, label=label, color=color, breakdown=breakdown)


def _label_for_score(score: float) -> Tuple[str, str]:
    """Map a numeric score to its (label, color) using QUALITY_LABELS thresholds."""
    for threshold, label, color in QUALITY_LABELS:
        if score >= threshold:
            return label, color
    return "Poor", "#EF4444"
