"""
core/issue_detector.py
-----------------------
Scans a DataFrame and produces a list of `Issue` objects, each describing
one detected data-quality problem: what it is, which columns/rows it
affects, how severe it is, and a recommended fix.

PHASE 1 coverage (this file will grow in later phases to the full catalog
requested: outliers, invalid emails/phones/URLs, encoding issues, skew,
correlation, feature leakage, etc.):
    - Missing values
    - Duplicate rows
    - Duplicate columns
    - Constant / near-constant columns
    - High cardinality columns
    - Whitespace issues
    - Inconsistent capitalization
    - Wrong / mixed data types

Each detector function is independent and pure (DataFrame in, list of
Issue out), so new detectors can be added without touching existing ones.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any

import pandas as pd
import numpy as np

from config.settings import THRESHOLDS, SEVERITY_COLORS
from utils.validators import has_inconsistent_case
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Issue:
    """A single detected data-quality issue, ready to be rendered as a card."""
    issue_id: str                    # stable unique key, e.g. "missing_values_Age"
    category: str                    # matches QUALITY_WEIGHTS key, e.g. "missing_values"
    title: str                       # e.g. "Missing Values"
    icon: str                        # emoji shown on the card
    severity: str                    # HIGH / MEDIUM / LOW / INFO
    affected_columns: List[str]
    affected_ratio: float            # 0.0-1.0, fraction of rows/cols affected
    description: str                 # plain-English explanation
    recommendation: str              # short recommended fix
    recommended_method: str          # method key used by cleaning_engine
    alternative_methods: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)  # extra data for UI (e.g. per-column %)

    @property
    def color(self) -> str:
        return SEVERITY_COLORS.get(self.severity, "#8B5CF6")


def detect_all_issues(df: pd.DataFrame) -> List[Issue]:
    """
    Run every registered detector against the DataFrame and return the
    combined, deduplicated list of issues.

    Args:
        df: The dataset to analyze.

    Returns:
        List of Issue objects, ordered roughly by severity (HIGH first).
    """
    detectors: List[Callable[[pd.DataFrame], List[Issue]]] = [
        detect_missing_values,
        detect_duplicate_rows,
        detect_duplicate_columns,
        detect_constant_columns,
        detect_high_cardinality,
        detect_whitespace_issues,
        detect_inconsistent_capitalization,
        detect_mixed_dtypes,
    ]

    issues: List[Issue] = []
    for detector in detectors:
        try:
            found = detector(df)
            issues.extend(found)
        except Exception as exc:
            logger.warning(f"Detector '{detector.__name__}' failed: {exc}")

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    issues.sort(key=lambda i: severity_order.get(i.severity, 4))
    return issues


# --------------------------------------------------------------------------
# INDIVIDUAL DETECTORS
# --------------------------------------------------------------------------

def detect_missing_values(df: pd.DataFrame) -> List[Issue]:
    """Flag columns with missing (NaN / None / empty-string) values."""
    issues: List[Issue] = []
    n_rows = len(df)
    if n_rows == 0:
        return issues

    missing_counts = df.isna().sum()
    affected = missing_counts[missing_counts > 0]
    if affected.empty:
        return issues

    overall_ratio = float(affected.sum()) / (n_rows * len(df.columns))
    max_col_ratio = float((affected / n_rows).max())

    if max_col_ratio >= THRESHOLDS["missing_high"]:
        severity = "HIGH"
    elif max_col_ratio >= THRESHOLDS["missing_medium"]:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    per_col_pct = {col: round(cnt / n_rows * 100, 2) for col, cnt in affected.items()}

    numeric_cols = [c for c in affected.index if pd.api.types.is_numeric_dtype(df[c])]
    recommended = "fill_median" if numeric_cols else "fill_mode"

    issues.append(Issue(
        issue_id="missing_values",
        category="missing_values",
        title="Missing Values",
        icon="🔴" if severity == "HIGH" else ("🟠" if severity == "MEDIUM" else "🟡"),
        severity=severity,
        affected_columns=list(affected.index),
        affected_ratio=overall_ratio,
        description=(
            f"{len(affected)} column(s) contain missing values, affecting up to "
            f"{max_col_ratio*100:.1f}% of rows in the worst column. Missing data can "
            f"bias statistics, break machine learning models, and cause errors in "
            f"downstream calculations."
        ),
        recommendation=(
            "Fill numeric columns with the median (robust to outliers) and categorical "
            "columns with the mode (most frequent value)."
        ),
        recommended_method=recommended,
        alternative_methods=[
            "fill_mean", "fill_mode", "forward_fill", "backward_fill",
            "interpolate", "drop_rows", "drop_columns",
        ],
        details={"per_column_pct": per_col_pct},
    ))
    return issues


def detect_duplicate_rows(df: pd.DataFrame) -> List[Issue]:
    """Flag fully duplicated rows."""
    n_rows = len(df)
    if n_rows == 0:
        return []
    dup_count = int(df.duplicated().sum())
    if dup_count == 0:
        return []

    ratio = dup_count / n_rows
    severity = "HIGH" if ratio > 0.10 else ("MEDIUM" if ratio > 0.02 else "LOW")

    return [Issue(
        issue_id="duplicate_rows",
        category="duplicate_rows",
        title="Duplicate Rows",
        icon="🔴" if severity == "HIGH" else "🟠",
        severity=severity,
        affected_columns=[],
        affected_ratio=ratio,
        description=(
            f"Found {dup_count} fully duplicated row(s), representing {ratio*100:.1f}% "
            f"of the dataset. Duplicate rows inflate counts, skew aggregations, and can "
            f"cause data leakage between training and test sets in ML pipelines."
        ),
        recommendation="Remove duplicate rows, keeping the first occurrence.",
        recommended_method="drop_duplicate_rows",
        alternative_methods=["drop_duplicate_rows_keep_last"],
        details={"duplicate_count": dup_count},
    )]


def detect_duplicate_columns(df: pd.DataFrame) -> List[Issue]:
    """Flag columns that are exact duplicates of another column (same values in same order)."""
    duplicate_groups: List[List[str]] = []
    seen: Dict[str, List[str]] = {}

    for col in df.columns:
        try:
            fingerprint = pd.util.hash_pandas_object(df[col], index=False).sum()
        except TypeError:
            continue
        seen.setdefault(fingerprint, []).append(col)

    for cols in seen.values():
        if len(cols) > 1:
            # Verify true equality (hash collisions are rare but possible)
            base = df[cols[0]]
            confirmed = [cols[0]] + [c for c in cols[1:] if df[c].equals(base)]
            if len(confirmed) > 1:
                duplicate_groups.append(confirmed)

    if not duplicate_groups:
        return []

    all_dupe_cols = [c for group in duplicate_groups for c in group[1:]]  # keep first of each group
    ratio = len(all_dupe_cols) / max(len(df.columns), 1)

    return [Issue(
        issue_id="duplicate_columns",
        category="duplicate_columns",
        title="Duplicate Columns",
        icon="🟠",
        severity="MEDIUM" if ratio > 0.05 else "LOW",
        affected_columns=all_dupe_cols,
        affected_ratio=ratio,
        description=(
            f"Found {len(duplicate_groups)} group(s) of columns with identical values: "
            f"{'; '.join([' = '.join(g) for g in duplicate_groups])}. Redundant columns "
            f"waste memory and can distort correlation-based analysis or ML feature importance."
        ),
        recommendation="Drop redundant duplicate columns, keeping one copy from each group.",
        recommended_method="drop_duplicate_columns",
        alternative_methods=["rename_and_keep"],
        details={"groups": duplicate_groups},
    )]


def detect_constant_columns(df: pd.DataFrame) -> List[Issue]:
    """Flag columns with only one unique value (or near-constant, e.g. 99%+ one value)."""
    n_rows = len(df)
    if n_rows == 0:
        return []

    constant_cols, near_constant_cols = [], []
    for col in df.columns:
        nunique = df[col].nunique(dropna=True)
        if nunique <= 1:
            constant_cols.append(col)
        else:
            top_freq_ratio = df[col].value_counts(normalize=True, dropna=True).iloc[0]
            if top_freq_ratio >= 0.99:
                near_constant_cols.append(col)

    issues: List[Issue] = []
    if constant_cols:
        issues.append(Issue(
            issue_id="constant_columns",
            category="constant_columns",
            title="Constant Columns",
            icon="🟡",
            severity="LOW",
            affected_columns=constant_cols,
            affected_ratio=len(constant_cols) / len(df.columns),
            description=(
                f"{len(constant_cols)} column(s) contain only a single unique value across "
                f"all rows: {', '.join(constant_cols)}. These columns carry zero information "
                f"and add no predictive value to any analysis or model."
            ),
            recommendation="Drop these columns since they carry no analytical value.",
            recommended_method="drop_columns",
            alternative_methods=["keep_as_metadata"],
            details={"columns": constant_cols},
        ))
    if near_constant_cols:
        issues.append(Issue(
            issue_id="near_constant_columns",
            category="constant_columns",
            title="Near-Constant Columns",
            icon="🟡",
            severity="LOW",
            affected_columns=near_constant_cols,
            affected_ratio=len(near_constant_cols) / len(df.columns),
            description=(
                f"{len(near_constant_cols)} column(s) have one value occupying 99%+ of rows: "
                f"{', '.join(near_constant_cols)}. These add minimal variance and rarely help "
                f"predictive models."
            ),
            recommendation="Consider dropping, or keep if the rare value is meaningful (e.g. fraud flag).",
            recommended_method="review_manually",
            alternative_methods=["drop_columns"],
            details={"columns": near_constant_cols},
        ))
    return issues


def detect_high_cardinality(df: pd.DataFrame) -> List[Issue]:
    """Flag categorical/text columns where almost every value is unique."""
    n_rows = len(df)
    if n_rows < 10:
        return []

    high_card_cols = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        ratio = df[col].nunique(dropna=True) / n_rows
        if ratio >= THRESHOLDS["high_cardinality_ratio"]:
            high_card_cols.append(col)

    if not high_card_cols:
        return []

    return [Issue(
        issue_id="high_cardinality",
        category="high_cardinality",
        title="High Cardinality Columns",
        icon="🟡",
        severity="LOW",
        affected_columns=high_card_cols,
        affected_ratio=len(high_card_cols) / len(df.columns),
        description=(
            f"{len(high_card_cols)} column(s) have nearly as many unique values as rows: "
            f"{', '.join(high_card_cols)}. These are likely identifiers (names, IDs, free text) "
            f"rather than useful categorical features, and one-hot encoding them would explode "
            f"dimensionality."
        ),
        recommendation="Exclude from categorical encoding, or use frequency/target encoding instead.",
        recommended_method="frequency_encoding",
        alternative_methods=["drop_columns", "target_encoding", "keep_as_identifier"],
        details={"columns": high_card_cols},
    )]


def detect_whitespace_issues(df: pd.DataFrame) -> List[Issue]:
    """Flag text columns with leading/trailing whitespace or double spaces."""
    affected_cols = []
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().astype(str)
        if sample.empty:
            continue
        has_issue = sample.str.contains(r"^\s+|\s+$|\s{2,}", regex=True).any()
        if has_issue:
            affected_cols.append(col)

    if not affected_cols:
        return []

    return [Issue(
        issue_id="whitespace_issues",
        category="invalid_values",
        title="Whitespace Issues",
        icon="🟡",
        severity="LOW",
        affected_columns=affected_cols,
        affected_ratio=len(affected_cols) / max(len(df.columns), 1),
        description=(
            f"{len(affected_cols)} text column(s) contain leading, trailing, or repeated "
            f"whitespace: {', '.join(affected_cols)}. This causes values like 'India' and "
            f"' India ' to be treated as different categories, breaking joins and groupings."
        ),
        recommendation="Trim leading/trailing spaces and collapse repeated internal spaces.",
        recommended_method="trim_spaces",
        alternative_methods=["remove_all_whitespace"],
        details={"columns": affected_cols},
    )]


def detect_inconsistent_capitalization(df: pd.DataFrame) -> List[Issue]:
    """Flag text columns where the same logical value appears in multiple cases."""
    affected_cols = []
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().head(500)
        if has_inconsistent_case(sample.tolist()):
            affected_cols.append(col)

    if not affected_cols:
        return []

    return [Issue(
        issue_id="inconsistent_capitalization",
        category="invalid_values",
        title="Inconsistent Capitalization",
        icon="🟡",
        severity="LOW",
        affected_columns=affected_cols,
        affected_ratio=len(affected_cols) / max(len(df.columns), 1),
        description=(
            f"{len(affected_cols)} column(s) mix different capitalization styles for what "
            f"looks like the same value, e.g. 'Mumbai' vs 'mumbai' vs 'MUMBAI': "
            f"{', '.join(affected_cols)}. This silently creates duplicate categories."
        ),
        recommendation="Standardize to Title Case (or lower/upper case, depending on the field).",
        recommended_method="title_case",
        alternative_methods=["lower_case", "upper_case"],
        details={"columns": affected_cols},
    )]


def detect_mixed_dtypes(df: pd.DataFrame) -> List[Issue]:
    """Flag object columns that contain a mix of numeric-looking and text values."""
    affected_cols = []
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().astype(str).head(500)
        if sample.empty:
            continue
        numeric_like = sample.str.match(r"^-?\d+(\.\d+)?$")
        ratio_numeric = numeric_like.mean()
        if 0.1 < ratio_numeric < 0.9:
            affected_cols.append(col)

    if not affected_cols:
        return []

    return [Issue(
        issue_id="mixed_dtypes",
        category="wrong_dtypes",
        title="Mixed Data Types",
        icon="🟠",
        severity="MEDIUM",
        affected_columns=affected_cols,
        affected_ratio=len(affected_cols) / max(len(df.columns), 1),
        description=(
            f"{len(affected_cols)} column(s) mix numeric-looking values with text in the same "
            f"column: {', '.join(affected_cols)}. This usually means the column was meant to be "
            f"numeric but has stray text (e.g. 'N/A', 'unknown') mixed in, forcing pandas to "
            f"store it as text."
        ),
        recommendation="Convert to numeric, turning non-numeric entries into missing values (NaN).",
        recommended_method="convert_to_numeric",
        alternative_methods=["convert_to_string", "review_manually"],
        details={"columns": affected_cols},
    )]
