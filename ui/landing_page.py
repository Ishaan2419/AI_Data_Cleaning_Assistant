"""
ui/landing_page.py
--------------------
Renders the first-screen experience: an animated hero title, tagline,
feature cards, and the file upload zone. Designed to look like a premium
SaaS product landing page rather than a default Streamlit app.
"""

from __future__ import annotations
from typing import Optional

import streamlit as st

from config.settings import APP_NAME, APP_TAGLINE, SUPPORTED_EXTENSIONS
from ui.components import render_feature_card

FEATURES = [
    ("🤖", "AI-Powered Insights", "Llama 3 explains your dataset, its business domain, and every column in plain English."),
    ("🔍", "Deep Issue Detection", "Scans for 30+ data quality problems, from missing values to feature leakage."),
    ("✅", "You're Always in Control", "Nothing is cleaned automatically. Review and approve every single change."),
    ("📊", "Live Dashboards", "Interactive charts and KPIs update in real time as you clean your data."),
    ("💬", "Chat With Your Data", "Ask questions, get ML suggestions, KPIs, SQL queries, and more."),
    ("📤", "Export Anything", "Download cleaned data as CSV, Excel, or JSON, plus a full PDF/HTML report."),
]


def render_hero() -> None:
    """Render the animated hero title, badge, and tagline."""
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1rem 0;">
            <div class="hero-badge">✨ 100% Local &nbsp;•&nbsp; Powered by Llama 3 &nbsp;•&nbsp; No Paid APIs</div>
            <div class="hero-title">AI Data Cleaning Assistant</div>
            <div class="hero-subtitle">Clean your datasets intelligently using AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_grid() -> None:
    """Render the 2-row feature card grid."""
    cols = st.columns(3)
    for idx, (icon, title, desc) in enumerate(FEATURES):
        with cols[idx % 3]:
            render_feature_card(icon, title, desc)


def render_upload_zone() -> Optional[object]:
    """
    Render the glassmorphism upload card and file uploader widget.

    Returns:
        The Streamlit UploadedFile object, or None if nothing uploaded yet.
    """
    st.markdown(
        """
        <div class="glass-card fade-in" style="text-align:center; padding: 2.4rem 2rem; margin-top: 1rem;">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">📁✨</div>
            <div style="font-size:1.3rem; font-weight:700; color:var(--text-primary); margin-bottom:0.3rem;">
                Upload Your Dataset to Get Started
            </div>
            <div style="color:var(--text-muted); font-size:0.9rem;">
                Supports CSV and Excel files &nbsp;•&nbsp; Processed 100% locally &nbsp;•&nbsp; Nothing leaves your machine
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "Upload dataset",
        type=SUPPORTED_EXTENSIONS,
        label_visibility="collapsed",
    )
    return uploaded_file


def render_landing_page() -> Optional[object]:
    """
    Compose the full landing page: hero, feature grid, upload zone.

    Returns:
        The uploaded file object (or None).
    """
    render_hero()
    st.write("")
    render_feature_grid()
    st.write("")
    uploaded = render_upload_zone()
    return uploaded
