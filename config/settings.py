"""
config/settings.py
-------------------
Single source of truth for every constant used across the application:
UI colors, thresholds for issue detection, AI model configuration, and
file-handling limits. Centralizing these values means the rest of the
codebase never hard-codes a "magic number" -- everything is tunable here.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


# --------------------------------------------------------------------------
# APPLICATION METADATA
# --------------------------------------------------------------------------
APP_NAME = "AI Data Cleaning Assistant"
APP_TAGLINE = "Clean your datasets intelligently using AI"
APP_VERSION = "1.0.0"
APP_ICON = "✨"

# --------------------------------------------------------------------------
# FILE HANDLING
# --------------------------------------------------------------------------
SUPPORTED_EXTENSIONS: List[str] = ["csv", "xlsx", "xls"]
MAX_FILE_SIZE_MB = 200
MAX_ROWS_FOR_FULL_PROFILE = 200_000  # beyond this, sample for heavy AI calls

# --------------------------------------------------------------------------
# OLLAMA / LLAMA CONFIGURATION
# --------------------------------------------------------------------------
@dataclass
class AIConfig:
    """Configuration for the local Ollama model used across the app."""
    host: str = "http://localhost:11434"
    default_model: str = "llama3.1"
    available_models: List[str] = field(
        default_factory=lambda: ["llama3.1", "llama3", "llama3.2"]
    )
    temperature: float = 0.3
    max_tokens: int = 1024
    request_timeout: int = 60


AI_CONFIG = AIConfig()

# --------------------------------------------------------------------------
# DATA QUALITY SCORING WEIGHTS
# --------------------------------------------------------------------------
# The quality score starts at 100 and loses points per detected problem.
# Weights are expressed as "points lost per 1% of affected rows/cols",
# capped per category so one issue can't tank the score unfairly.
QUALITY_WEIGHTS: Dict[str, float] = {
    "missing_values": 25.0,
    "duplicate_rows": 15.0,
    "duplicate_columns": 5.0,
    "outliers": 15.0,
    "wrong_dtypes": 10.0,
    "invalid_values": 15.0,
    "constant_columns": 5.0,
    "high_cardinality": 5.0,
    "encoding_issues": 5.0,
}

QUALITY_LABELS = [
    (90, "Excellent", "#22C55E"),
    (75, "Good", "#84CC16"),
    (60, "Fair", "#F59E0B"),
    (40, "Needs Cleaning", "#F97316"),
    (0, "Poor", "#EF4444"),
]

# --------------------------------------------------------------------------
# ISSUE DETECTION THRESHOLDS
# --------------------------------------------------------------------------
THRESHOLDS: Dict[str, float] = {
    "missing_high": 0.30,        # % missing considered HIGH severity
    "missing_medium": 0.05,      # % missing considered MEDIUM severity
    "high_cardinality_ratio": 0.90,  # unique/total ratio -> high cardinality
    "low_cardinality_max": 2,        # <= this many uniques -> near-constant
    "outlier_iqr_multiplier": 1.5,
    "outlier_zscore": 3.0,
    "rare_category_threshold": 0.01,  # categories under 1% of rows
    "high_correlation": 0.90,
    "skew_threshold": 1.0,
}

SEVERITY_COLORS = {
    "HIGH": "#EF4444",
    "MEDIUM": "#F59E0B",
    "LOW": "#3B82F6",
    "INFO": "#8B5CF6",
}

# --------------------------------------------------------------------------
# UI THEME TOKENS (used by ui/theme.py CSS injection)
# --------------------------------------------------------------------------
COLORS = {
    "bg_dark": "#0E0B1A",
    "bg_dark_secondary": "#161228",
    "bg_light": "#F7F7FC",
    "bg_light_secondary": "#FFFFFF",
    "primary": "#7C5CFC",
    "primary_light": "#9C87FF",
    "accent": "#22D3EE",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text_dark": "#F1EEFB",
    "text_light": "#1A1625",
    "muted": "#8B87A3",
}
