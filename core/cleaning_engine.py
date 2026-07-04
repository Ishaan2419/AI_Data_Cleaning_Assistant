"""
core/cleaning_engine.py
-------------------------
Implements every cleaning operation the UI can trigger, plus an undo/redo
history stack. Every function takes a DataFrame + parameters and returns
a NEW DataFrame (never mutates in place), so the history stack can hold
full snapshots safely.

The `apply_method` dispatcher maps the string method keys used by
issue_detector.Issue.recommended_method / alternative_methods to the
actual implementation, so the UI never needs to know implementation
details -- it just calls `apply_method(df, method_key, columns, **kwargs)`.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional

import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class HistoryEntry:
    """One entry in the cleaning timeline, used for the history UI and undo/redo."""
    timestamp: str
    action: str                 # human-readable description, e.g. "Filled missing values in Age"
    method: str                 # method key applied
    columns: List[str]
    df_snapshot: pd.DataFrame   # full DataFrame state AFTER this action
    rows_before: int
    rows_after: int
    cols_before: int
    cols_after: int


class CleaningHistory:
    """
    Manages the undo/redo stack of DataFrame snapshots. Kept intentionally
    simple (snapshot-based rather than diff-based) since typical uploaded
    datasets are small/medium enough that this trades a little memory for
    a lot of reliability and simplicity.
    """

    def __init__(self, original_df: pd.DataFrame):
        self._entries: List[HistoryEntry] = []
        self._redo_stack: List[HistoryEntry] = []
        self.original_df = original_df.copy()

    def push(self, df_after: pd.DataFrame, action: str, method: str,
              columns: List[str], df_before: pd.DataFrame) -> None:
        entry = HistoryEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            action=action,
            method=method,
            columns=columns,
            df_snapshot=df_after.copy(),
            rows_before=len(df_before),
            rows_after=len(df_after),
            cols_before=df_before.shape[1],
            cols_after=df_after.shape[1],
        )
        self._entries.append(entry)
        self._redo_stack.clear()
        logger.info(f"History: applied '{method}' on {columns} -> {action}")

    def current_df(self) -> pd.DataFrame:
        if not self._entries:
            return self.original_df.copy()
        return self._entries[-1].df_snapshot.copy()

    def undo(self) -> Optional[pd.DataFrame]:
        if not self._entries:
            return None
        entry = self._entries.pop()
        self._redo_stack.append(entry)
        return self.current_df()

    def redo(self) -> Optional[pd.DataFrame]:
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        self._entries.append(entry)
        return self.current_df()

    @property
    def entries(self) -> List[HistoryEntry]:
        return list(self._entries)

    def can_undo(self) -> bool:
        return len(self._entries) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0


# --------------------------------------------------------------------------
# INDIVIDUAL CLEANING OPERATIONS
# (Each takes a DataFrame + column list and returns a NEW DataFrame)
# --------------------------------------------------------------------------

def fill_median(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].fillna(out[col].median())
    return out


def fill_mean(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].fillna(out[col].mean())
    return out


def fill_mode(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        mode_vals = out[col].mode(dropna=True)
        if not mode_vals.empty:
            out[col] = out[col].fillna(mode_vals.iloc[0])
    return out


def forward_fill(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    out[columns] = out[columns].ffill()
    return out


def backward_fill(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    out[columns] = out[columns].bfill()
    return out


def interpolate(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].interpolate(method="linear", limit_direction="both")
    return out


def drop_rows(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Drop rows that have any missing value in the given columns."""
    return df.dropna(subset=columns).reset_index(drop=True)


def drop_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    return df.drop(columns=[c for c in columns if c in df.columns])


def drop_duplicate_rows(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    return df.drop_duplicates(keep="first").reset_index(drop=True)


def drop_duplicate_rows_keep_last(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    return df.drop_duplicates(keep="last").reset_index(drop=True)


def drop_duplicate_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """`columns` here is the pre-computed list of redundant columns to drop."""
    return df.drop(columns=[c for c in columns if c in df.columns])


def trim_spaces(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].astype(str).str.strip().str.replace(r"\s{2,}", " ", regex=True)
        out.loc[df[col].isna(), col] = np.nan  # preserve original NaNs
    return out


def lower_case(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].astype(str).str.lower()
        out.loc[df[col].isna(), col] = np.nan
    return out


def upper_case(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].astype(str).str.upper()
        out.loc[df[col].isna(), col] = np.nan
    return out


def title_case(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].astype(str).str.strip().str.title()
        out.loc[df[col].isna(), col] = np.nan
    return out


def convert_to_numeric(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def convert_to_string(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].astype(str)
    return out


def frequency_encoding(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        freq_map = out[col].value_counts(normalize=True)
        out[f"{col}_freq_enc"] = out[col].map(freq_map)
    return out


def review_manually(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """No-op: marks the issue as reviewed without changing data."""
    return df.copy()


def keep_as_metadata(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    return df.copy()


# --------------------------------------------------------------------------
# METHOD REGISTRY + DISPATCHER
# --------------------------------------------------------------------------

METHOD_REGISTRY: Dict[str, Callable[..., pd.DataFrame]] = {
    "fill_median": fill_median,
    "fill_mean": fill_mean,
    "fill_mode": fill_mode,
    "forward_fill": forward_fill,
    "backward_fill": backward_fill,
    "interpolate": interpolate,
    "drop_rows": drop_rows,
    "drop_columns": drop_columns,
    "drop_duplicate_rows": drop_duplicate_rows,
    "drop_duplicate_rows_keep_last": drop_duplicate_rows_keep_last,
    "drop_duplicate_columns": drop_duplicate_columns,
    "trim_spaces": trim_spaces,
    "lower_case": lower_case,
    "upper_case": upper_case,
    "title_case": title_case,
    "convert_to_numeric": convert_to_numeric,
    "convert_to_string": convert_to_string,
    "frequency_encoding": frequency_encoding,
    "review_manually": review_manually,
    "keep_as_metadata": keep_as_metadata,
}

METHOD_LABELS: Dict[str, str] = {
    "fill_median": "Fill with Median",
    "fill_mean": "Fill with Mean",
    "fill_mode": "Fill with Mode",
    "forward_fill": "Forward Fill",
    "backward_fill": "Backward Fill",
    "interpolate": "Interpolate",
    "drop_rows": "Drop Affected Rows",
    "drop_columns": "Drop Column(s)",
    "drop_duplicate_rows": "Remove Duplicates (keep first)",
    "drop_duplicate_rows_keep_last": "Remove Duplicates (keep last)",
    "drop_duplicate_columns": "Drop Redundant Column(s)",
    "trim_spaces": "Trim Whitespace",
    "lower_case": "Convert to lower case",
    "upper_case": "CONVERT TO UPPER CASE",
    "title_case": "Convert To Title Case",
    "convert_to_numeric": "Convert to Numeric",
    "convert_to_string": "Convert to Text",
    "frequency_encoding": "Frequency Encoding",
    "review_manually": "Mark as Reviewed (no change)",
    "keep_as_metadata": "Keep As-Is",
}


def apply_method(df: pd.DataFrame, method: str, columns: List[str]) -> pd.DataFrame:
    """
    Dispatch a cleaning method by its string key.

    Args:
        df: Current DataFrame.
        method: One of the keys in METHOD_REGISTRY.
        columns: Columns the operation should act on.

    Returns:
        A new, cleaned DataFrame.

    Raises:
        KeyError: if `method` isn't a registered cleaning operation.
    """
    if method not in METHOD_REGISTRY:
        raise KeyError(f"Unknown cleaning method: '{method}'")
    func = METHOD_REGISTRY[method]
    try:
        return func(df, columns)
    except Exception as exc:
        logger.error(f"Cleaning method '{method}' failed on columns {columns}: {exc}")
        raise
