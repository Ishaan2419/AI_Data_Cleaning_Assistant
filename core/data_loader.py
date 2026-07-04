"""
core/data_loader.py
--------------------
Handles reading uploaded CSV/Excel files into pandas DataFrames and
computing the "at a glance" metadata block shown immediately after upload
(rows, columns, memory usage, missing %, duplicate %, dtypes, preview).

Design notes:
- All functions are pure (no Streamlit calls) so they're independently
  testable and reusable outside the UI layer.
- `load_dataset` is defensive: it tries multiple encodings/separators
  for CSVs before giving up, since real-world files are messy.
"""

from __future__ import annotations
import io
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

CSV_ENCODINGS_TO_TRY = ["utf-8", "utf-8-sig", "latin1", "cp1252"]
CSV_SEPARATORS_TO_TRY = [",", ";", "\t", "|"]


class DataLoadError(Exception):
    """Raised when a file cannot be parsed into a DataFrame after all fallbacks."""


@dataclass
class DatasetMeta:
    """Snapshot of high-level dataset statistics, computed once per load."""
    n_rows: int
    n_cols: int
    memory_usage_mb: float
    file_size_mb: float
    missing_pct: float
    duplicate_pct: float
    dtypes_summary: Dict[str, int]
    column_names: List[str]


def load_dataset(uploaded_file) -> pd.DataFrame:
    """
    Parse an uploaded Streamlit `UploadedFile` (CSV or Excel) into a DataFrame.

    Tries multiple encodings and separators for CSV files since real-world
    exports frequently deviate from plain UTF-8 comma-separated format.

    Args:
        uploaded_file: A Streamlit `UploadedFile` object.

    Returns:
        A parsed pandas DataFrame.

    Raises:
        DataLoadError: if the file cannot be parsed by any strategy.
    """
    filename = uploaded_file.name.lower()
    raw_bytes = uploaded_file.getvalue()

    if filename.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(io.BytesIO(raw_bytes))
            logger.info(f"Loaded Excel file '{filename}' -> shape={df.shape}")
            return _post_process(df)
        except Exception as exc:
            logger.error(f"Failed to parse Excel file '{filename}': {exc}")
            raise DataLoadError(f"Could not read Excel file: {exc}") from exc

    if filename.endswith(".csv"):
        last_error: Optional[Exception] = None
        for encoding in CSV_ENCODINGS_TO_TRY:
            for sep in CSV_SEPARATORS_TO_TRY:
                try:
                    df = pd.read_csv(
                        io.BytesIO(raw_bytes), encoding=encoding, sep=sep,
                        engine="python", on_bad_lines="skip",
                    )
                    # Heuristic sanity check: a correct separator should
                    # produce more than one column (unless the file truly
                    # has one column).
                    if df.shape[1] >= 1:
                        logger.info(
                            f"Loaded CSV '{filename}' with encoding={encoding}, "
                            f"sep='{sep}' -> shape={df.shape}"
                        )
                        return _post_process(df)
                except Exception as exc:
                    last_error = exc
                    continue
        logger.error(f"Failed to parse CSV file '{filename}' after all fallbacks: {last_error}")
        raise DataLoadError(f"Could not read CSV file after multiple attempts: {last_error}")

    raise DataLoadError(f"Unsupported file type: {filename}")


def _post_process(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from column names and drop fully-empty unnamed columns."""
    df.columns = [str(c).strip() for c in df.columns]
    unnamed_empty = [
        c for c in df.columns
        if str(c).lower().startswith("unnamed") and df[c].isna().all()
    ]
    if unnamed_empty:
        df = df.drop(columns=unnamed_empty)
        logger.info(f"Dropped {len(unnamed_empty)} fully-empty unnamed column(s)")
    return df


def compute_metadata(df: pd.DataFrame, file_size_bytes: int) -> DatasetMeta:
    """
    Compute the summary statistics block shown right after upload.

    Args:
        df: The loaded DataFrame.
        file_size_bytes: Raw size of the uploaded file, in bytes.

    Returns:
        A DatasetMeta dataclass with rows, cols, memory, missing %, etc.
    """
    n_rows, n_cols = df.shape
    memory_mb = df.memory_usage(deep=True).sum() / (1024 ** 2)
    file_size_mb = file_size_bytes / (1024 ** 2)

    total_cells = max(n_rows * n_cols, 1)
    missing_pct = float(df.isna().sum().sum()) / total_cells * 100

    duplicate_pct = float(df.duplicated().sum()) / max(n_rows, 1) * 100

    dtypes_summary: Dict[str, int] = {}
    for dtype in df.dtypes:
        key = _friendly_dtype_name(dtype)
        dtypes_summary[key] = dtypes_summary.get(key, 0) + 1

    return DatasetMeta(
        n_rows=n_rows,
        n_cols=n_cols,
        memory_usage_mb=round(memory_mb, 3),
        file_size_mb=round(file_size_mb, 3),
        missing_pct=round(missing_pct, 2),
        duplicate_pct=round(duplicate_pct, 2),
        dtypes_summary=dtypes_summary,
        column_names=list(df.columns),
    )


def _friendly_dtype_name(dtype: np.dtype) -> str:
    """Map a numpy/pandas dtype to a human-friendly category label."""
    dtype_str = str(dtype)
    if "int" in dtype_str:
        return "Integer"
    if "float" in dtype_str:
        return "Float"
    if "bool" in dtype_str:
        return "Boolean"
    if "datetime" in dtype_str:
        return "Datetime"
    if "object" in dtype_str or "category" in dtype_str:
        return "Text / Categorical"
    return dtype_str.capitalize()


def classify_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Classify columns into semantic buckets used by the AI understanding
    module and the issue detector: numerical, categorical, datetime,
    and likely-ID columns.

    Returns:
        Dict with keys: 'numerical', 'categorical', 'datetime', 'id_like', 'boolean'.
    """
    n_rows = len(df)
    numerical, categorical, datetime_cols, id_like, boolean_cols = [], [], [], [], []

    for col in df.columns:
        series = df[col]
        dtype_str = str(series.dtype)

        if "datetime" in dtype_str:
            datetime_cols.append(col)
            continue
        if "bool" in dtype_str:
            boolean_cols.append(col)
            continue
        if pd.api.types.is_numeric_dtype(series):
            unique_ratio = series.nunique(dropna=True) / max(n_rows, 1)
            is_id_name = any(tok in col.lower() for tok in ["id", "code", "number", "no."])
            if is_id_name and unique_ratio > 0.9:
                id_like.append(col)
            else:
                numerical.append(col)
            continue

        # Object / string column: try to detect if it's secretly a date
        if _looks_like_date_column(series):
            datetime_cols.append(col)
            continue

        unique_ratio = series.nunique(dropna=True) / max(n_rows, 1)
        is_id_name = any(tok in col.lower() for tok in ["id", "uuid", "code"])
        if is_id_name and unique_ratio > 0.9:
            id_like.append(col)
        else:
            categorical.append(col)

    return {
        "numerical": numerical,
        "categorical": categorical,
        "datetime": datetime_cols,
        "id_like": id_like,
        "boolean": boolean_cols,
    }


def _looks_like_date_column(series: pd.Series, sample_size: int = 30) -> bool:
    """Heuristically check whether an object-dtype column contains dates."""
    sample = series.dropna().astype(str).head(sample_size)
    if sample.empty:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        success_ratio = parsed.notna().sum() / len(sample)
        return success_ratio > 0.8
    except Exception:
        return False
