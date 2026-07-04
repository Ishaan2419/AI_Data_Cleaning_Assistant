"""
ui/components.py
------------------
Reusable, presentation-only rendering functions shared across pages:
KPI metric cards, feature cards (landing page), issue cards, and the
data quality gauge chart. Keeping these separate from page logic keeps
app.py readable and avoids repeating HTML/CSS snippets everywhere.
"""

from __future__ import annotations
from typing import Optional, List

import streamlit as st
import plotly.graph_objects as go

from core.issue_detector import Issue
from core.cleaning_engine import METHOD_LABELS


def render_kpi_card(label: str, value: str, delta: Optional[str] = None,
                     delta_good: bool = True, icon: str = "") -> None:
    """Render a single glassmorphism KPI metric card."""
    delta_html = ""
    if delta:
        cls = "kpi-delta-good" if delta_good else "kpi-delta-bad"
        delta_html = f'<div class="{cls}">{delta}</div>'
    st.markdown(
        f"""
        <div class="kpi-card fade-in">
            <div class="kpi-label">{icon} {label}</div>
            <div class="kpi-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_card(icon: str, title: str, description: str) -> None:
    """Render a landing-page feature card."""
    st.markdown(
        f"""
        <div class="glass-card feature-card fade-in">
            <span class="feature-icon">{icon}</span>
            <div class="feature-title">{title}</div>
            <div class="feature-desc">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_quality_gauge(score: float, label: str, color: str) -> go.Figure:
    """Build a Plotly gauge chart for the overall data quality score."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "%", "font": {"size": 42, "color": color}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "rgba(255,255,255,0.3)"},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 40], "color": "rgba(239,68,68,0.15)"},
                {"range": [40, 60], "color": "rgba(249,115,22,0.15)"},
                {"range": [60, 75], "color": "rgba(245,158,11,0.15)"},
                {"range": [75, 90], "color": "rgba(132,204,22,0.15)"},
                {"range": [90, 100], "color": "rgba(34,197,94,0.15)"},
            ],
        },
    ))
    fig.update_layout(
        height=260,
        margin=dict(t=10, b=10, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#C7C2DE", "family": "Inter"},
    )
    return fig


def render_issue_card(issue: Issue, key_prefix: str) -> str:
    """
    Render a single issue card with its explanation and details, then
    return the user's action for this issue via Streamlit buttons.

    Args:
        issue: The Issue to render.
        key_prefix: Unique key prefix (e.g. issue.issue_id) for widget keys.

    Returns:
        One of "accept", "skip", "learn_more", or "" (no action this run).
    """
    st.markdown(
        f"""
        <div class="issue-card fade-in" style="--sev-color: {issue.color};">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;">
                <div style="font-size:1.15rem; font-weight:700; color:var(--text-primary);">
                    {issue.icon} {issue.title}
                </div>
                <span class="severity-badge">{issue.severity}</span>
            </div>
            <div style="color:var(--text-secondary); font-size:0.92rem; line-height:1.55; margin-bottom:0.8rem;">
                {issue.description}
            </div>
            <div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.4rem;">
                <b>Affected columns:</b> {', '.join(issue.affected_columns) if issue.affected_columns else '—'}
            </div>
            <div style="background: rgba(124,92,252,0.10); border-radius:10px; padding:0.7rem 1rem; margin-top:0.6rem;">
                <b style="color:var(--primary-light);">💡 AI Recommendation:</b>
                <span style="color:var(--text-secondary);"> {issue.recommendation}</span>
                <div style="font-size:0.8rem; color:var(--text-muted); margin-top:0.25rem;">
                    Suggested method: <b>{METHOD_LABELS.get(issue.recommended_method, issue.recommended_method)}</b>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.3])
    action = ""
    with col1:
        if st.button("✅ Accept", key=f"{key_prefix}_accept", use_container_width=True, type="primary"):
            action = "accept"
    with col2:
        if st.button("⏭️ Skip", key=f"{key_prefix}_skip", use_container_width=True):
            action = "skip"
    with col3:
        if st.button("🔍 Review", key=f"{key_prefix}_review", use_container_width=True):
            action = "review"
    with col4:
        if issue.alternative_methods:
            chosen = st.selectbox(
                "Alternative method",
                options=[issue.recommended_method] + issue.alternative_methods,
                format_func=lambda m: METHOD_LABELS.get(m, m),
                key=f"{key_prefix}_method_select",
                label_visibility="collapsed",
            )
            st.session_state[f"{key_prefix}_chosen_method"] = chosen
    return action


def render_section_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Render a consistent section header used across dashboard tabs."""
    st.markdown(
        f"""
        <div style="margin: 1.2rem 0 0.6rem 0;">
            <div style="font-size:1.5rem; font-weight:800; color:var(--text-primary);
                        font-family:'Plus Jakarta Sans', sans-serif;">
                {icon} {title}
            </div>
            <div style="color:var(--text-muted); font-size:0.92rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_loading_animation(message: str = "Analyzing your dataset...") -> None:
    """Render a custom animated loading indicator (used during AI calls)."""
    st.markdown(
        f"""
        <div style="text-align:center; padding: 2rem;">
            <div style="
                width:52px; height:52px; margin: 0 auto 1rem auto;
                border: 4px solid rgba(124,92,252,0.15);
                border-top: 4px solid #7C5CFC;
                border-radius: 50%;
                animation: spin 0.9s linear infinite;
            "></div>
            <div style="color:var(--text-secondary); font-weight:600;">{message}</div>
        </div>
        <style>
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
