"""
core/ai_engine.py
------------------
Thin wrapper around the local Ollama server (running Llama 3.x). Every
AI-powered feature in the app -- dataset understanding, issue explanations,
and the chatbot -- goes through this module, so there's exactly one place
that knows how to talk to Ollama, handle timeouts, and degrade gracefully
if the model / server isn't available.

No paid API is used anywhere in this file -- everything calls a local
Ollama daemon at AI_CONFIG.host.
"""

from __future__ import annotations
import json
from typing import Optional, Dict, Any, List

import pandas as pd

from config.settings import AI_CONFIG, MAX_ROWS_FOR_FULL_PROFILE
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import ollama
    _OLLAMA_IMPORT_OK = True
except ImportError:  # pragma: no cover
    _OLLAMA_IMPORT_OK = False


class AIUnavailableError(Exception):
    """Raised when Ollama isn't reachable or the requested model isn't pulled."""


def is_ollama_available(model: Optional[str] = None) -> bool:
    """
    Check whether the Ollama server is reachable and (optionally) whether
    a specific model has been pulled locally.

    Args:
        model: Model name to check for, e.g. "llama3.1". If None, only
               checks server reachability.

    Returns:
        True if usable, False otherwise (never raises).
    """
    if not _OLLAMA_IMPORT_OK:
        return False
    try:
        client = ollama.Client(host=AI_CONFIG.host)
        response = client.list()
        if model is None:
            return True
        available_names = [m.get("model", m.get("name", "")) for m in response.get("models", [])]
        return any(model in name for name in available_names)
    except Exception as exc:
        logger.warning(f"Ollama not available: {exc}")
        return False


def _chat(prompt: str, system: str = "", model: Optional[str] = None,
          temperature: Optional[float] = None) -> str:
    """
    Low-level call to Ollama's chat endpoint.

    Args:
        prompt: The user-turn content.
        system: Optional system prompt to steer behavior/tone.
        model: Override the default model.
        temperature: Override default sampling temperature.

    Returns:
        The model's text response.

    Raises:
        AIUnavailableError: if Ollama can't be reached or errors out.
    """
    if not _OLLAMA_IMPORT_OK:
        raise AIUnavailableError(
            "The 'ollama' Python package isn't installed. Run: pip install ollama"
        )
    model_name = model or AI_CONFIG.default_model
    try:
        client = ollama.Client(host=AI_CONFIG.host)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat(
            model=model_name,
            messages=messages,
            options={
                "temperature": temperature if temperature is not None else AI_CONFIG.temperature,
                "num_predict": AI_CONFIG.max_tokens,
            },
        )
        return response["message"]["content"].strip()
    except Exception as exc:
        logger.error(f"Ollama chat call failed (model={model_name}): {exc}")
        raise AIUnavailableError(
            f"Couldn't reach Ollama or model '{model_name}'. "
            f"Make sure Ollama is running (`ollama serve`) and the model is pulled "
            f"(`ollama pull {model_name}`)."
        ) from exc


# --------------------------------------------------------------------------
# DATASET METADATA SERIALIZATION (used to build AI prompts)
# --------------------------------------------------------------------------

def build_dataset_profile_text(df: pd.DataFrame, column_classes: Dict[str, List[str]]) -> str:
    """
    Serialize a compact, token-efficient description of the dataset for
    inclusion in AI prompts: shape, column names/types, sample values,
    and basic stats -- NOT the raw data itself (keeps prompts small and
    avoids sending full datasets to the model).

    Args:
        df: The dataset.
        column_classes: Output of data_loader.classify_columns().

    Returns:
        A formatted text block ready to interpolate into a prompt.
    """
    lines = [f"Dataset shape: {df.shape[0]} rows x {df.shape[1]} columns.", "", "Columns:"]
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_missing = int(df[col].isna().sum())
        n_unique = int(df[col].nunique(dropna=True))
        sample_vals = df[col].dropna().unique()[:3].tolist()
        lines.append(
            f"- {col} (dtype={dtype}, missing={n_missing}, unique={n_unique}, "
            f"sample={sample_vals})"
        )

    lines.append("")
    lines.append(f"Likely numerical columns: {column_classes.get('numerical', [])}")
    lines.append(f"Likely categorical columns: {column_classes.get('categorical', [])}")
    lines.append(f"Likely datetime columns: {column_classes.get('datetime', [])}")
    lines.append(f"Likely ID columns: {column_classes.get('id_like', [])}")
    lines.append(f"Likely boolean columns: {column_classes.get('boolean', [])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# HIGH-LEVEL AI FEATURES
# --------------------------------------------------------------------------

DATASET_UNDERSTANDING_SYSTEM_PROMPT = """You are a senior data analyst helping a user
understand a dataset they just uploaded. Be concise, concrete, and beginner-friendly.
Always respond with valid JSON only -- no markdown fences, no preamble, no commentary
outside the JSON object."""

DATASET_UNDERSTANDING_SCHEMA_HINT = """
Respond with a JSON object with EXACTLY these keys:
{
  "dataset_summary": "1-2 sentence plain-English summary of what this dataset is about",
  "business_domain": "e.g. Retail, Healthcare, Finance, HR, E-commerce",
  "column_meanings": {"column_name": "short meaning of this column", ...},
  "possible_target_column": "column name most likely to be an ML prediction target, or null",
  "possible_primary_key": "column name most likely to be a unique identifier, or null",
  "potential_relationships": ["short description of relationships between columns"],
  "ml_use_cases": ["short use case 1", "short use case 2"],
  "dashboard_use_cases": ["short KPI/dashboard idea 1", "short idea 2"],
  "bi_use_cases": ["short BI use case 1"],
  "potential_cleaning_issues": ["short issue description 1", "short issue description 2"],
  "overall_summary": "2-3 sentence overall narrative summary"
}
"""


def get_dataset_understanding(df: pd.DataFrame, column_classes: Dict[str, List[str]],
                                model: Optional[str] = None) -> Dict[str, Any]:
    """
    Ask Llama to explain the dataset: domain, column meanings, target column,
    relationships, and potential use cases. Returns parsed JSON.

    Args:
        df: The dataset to describe.
        column_classes: Output of data_loader.classify_columns().
        model: Optional model override.

    Returns:
        Parsed dict matching DATASET_UNDERSTANDING_SCHEMA_HINT.

    Raises:
        AIUnavailableError: if the model can't be reached.
        ValueError: if the model's response isn't valid JSON.
    """
    profile_text = build_dataset_profile_text(df, column_classes)
    prompt = f"{profile_text}\n\n{DATASET_UNDERSTANDING_SCHEMA_HINT}"
    raw = _chat(prompt, system=DATASET_UNDERSTANDING_SYSTEM_PROMPT, model=model)
    return _safe_parse_json(raw)


ISSUE_EXPLANATION_SYSTEM_PROMPT = """You are a friendly senior data scientist explaining
a data quality issue to a beginner. Be clear, practical, and encouraging. Respond with
valid JSON only, no markdown fences."""


def explain_issue_with_ai(issue_title: str, issue_description: str, affected_columns: List[str],
                            model: Optional[str] = None) -> Dict[str, str]:
    """
    Ask Llama for a beginner-friendly deep-dive explanation of a specific
    detected issue: why it happened, how serious it is, business impact,
    risk, recommended fix, alternatives, and best practice.

    Returns:
        Dict with keys: why_it_happened, severity_explanation, business_impact,
        risk, recommended_solution, alternative_solutions, best_practice.
    """
    prompt = f"""
Issue: {issue_title}
Description: {issue_description}
Affected columns: {affected_columns}

Respond with a JSON object with EXACTLY these keys (each value is 1-2 short sentences):
{{
  "why_it_happened": "...",
  "severity_explanation": "...",
  "business_impact": "...",
  "risk": "...",
  "recommended_solution": "...",
  "alternative_solutions": "...",
  "best_practice": "..."
}}
"""
    raw = _chat(prompt, system=ISSUE_EXPLANATION_SYSTEM_PROMPT, model=model)
    return _safe_parse_json(raw)


CHATBOT_SYSTEM_PROMPT = """You are an embedded data analyst assistant inside a data
cleaning app. You have access to a summary of the user's uploaded dataset (provided
below). Answer questions about the dataset, suggest ML algorithms, dashboards, KPIs,
SQL queries, visualizations, and feature engineering ideas. Be concise, concrete, and
reference actual column names from the dataset. Do not invent columns that don't exist."""


def chat_with_dataset(user_question: str, df: pd.DataFrame, column_classes: Dict[str, List[str]],
                        chat_history: Optional[List[Dict[str, str]]] = None,
                        model: Optional[str] = None) -> str:
    """
    Answer a free-form user question about the uploaded dataset, using the
    dataset profile as context. Powers the AI Chatbot feature.

    Args:
        user_question: The user's question.
        df: The current (possibly partially cleaned) dataset.
        column_classes: Output of data_loader.classify_columns().
        chat_history: Optional prior turns as [{"role": "user"/"assistant", "content": ...}].
        model: Optional model override.

    Returns:
        The assistant's text reply.
    """
    profile_text = build_dataset_profile_text(df, column_classes)
    context_prompt = f"Dataset context:\n{profile_text}\n\nUser question: {user_question}"

    if not _OLLAMA_IMPORT_OK:
        raise AIUnavailableError("The 'ollama' Python package isn't installed.")

    model_name = model or AI_CONFIG.default_model
    try:
        client = ollama.Client(host=AI_CONFIG.host)
        messages = [{"role": "system", "content": CHATBOT_SYSTEM_PROMPT}]
        if chat_history:
            messages.extend(chat_history[-10:])  # keep prompt bounded
        messages.append({"role": "user", "content": context_prompt})

        response = client.chat(
            model=model_name,
            messages=messages,
            options={"temperature": 0.4, "num_predict": AI_CONFIG.max_tokens},
        )
        return response["message"]["content"].strip()
    except Exception as exc:
        logger.error(f"Chatbot call failed: {exc}")
        raise AIUnavailableError(
            f"Couldn't reach Ollama or model '{model_name}'. Make sure Ollama is running."
        ) from exc


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    """Parse a model response as JSON, stripping accidental markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse AI JSON response: {exc}\nRaw: {raw[:500]}")
        raise ValueError(f"AI response wasn't valid JSON: {exc}") from exc
