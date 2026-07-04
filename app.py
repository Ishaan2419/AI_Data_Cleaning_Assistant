"""
app.py
------
Main entry point for the AI Data Cleaning Assistant.

Flow:
    Landing Page (upload) -> Overview -> AI Insights -> Issues & Cleaning
    (approval workflow) -> Live Dashboard -> History -> Chatbot

Run with:
    streamlit run app.py

Requires a local Ollama server running for the AI features:
    ollama serve
    ollama pull llama3.1
"""

from __future__ import annotations
import time

import streamlit as st
import pandas as pd
import plotly.express as px

from config.settings import APP_NAME, APP_ICON, AI_CONFIG
from core.data_loader import load_dataset, compute_metadata, classify_columns, DataLoadError
from core.issue_detector import detect_all_issues
from core.quality_scorer import compute_quality_score
from core.cleaning_engine import CleaningHistory, apply_method, METHOD_LABELS
from core.ai_engine import (
    is_ollama_available, get_dataset_understanding, explain_issue_with_ai,
    chat_with_dataset, AIUnavailableError,
)
from ui.theme import inject_theme, theme_toggle_widget
from ui.landing_page import render_landing_page
from ui.components import (
    render_kpi_card, render_quality_gauge, render_issue_card,
    render_section_header, render_loading_animation,
)
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# --------------------------------------------------------------------------

def init_session_state() -> None:
    """Set up all session_state keys used across the app, once per session."""
    defaults = {
        "theme_mode": "dark",
        "raw_df": None,               # original, never modified after load
        "history": None,              # CleaningHistory instance
        "file_size_bytes": 0,
        "file_name": "",
        "ai_understanding": None,
        "chat_messages": [],          # [{"role": ..., "content": ...}]
        "reviewed_issue_ids": set(),  # issue_ids the user accepted or skipped
        "skipped_issue_ids": set(),
        "all_issue_ids_seen": set(),  # cumulative issue_ids ever detected this session
        "ai_model": AI_CONFIG.default_model,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()
inject_theme()


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"""
            <div style="text-align:center; padding: 0.5rem 0 1rem 0;">
                <div style="font-size:2rem;">{APP_ICON}</div>
                <div style="font-weight:800; font-size:1.1rem; color:var(--text-primary);
                            font-family:'Plus Jakarta Sans', sans-serif;">{APP_NAME}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        theme_toggle_widget()
        st.divider()

        if st.session_state.raw_df is not None:
            st.caption(f"📄 **File:** {st.session_state.file_name}")
            df = st.session_state.history.current_df()
            st.caption(f"📐 **Shape:** {df.shape[0]:,} rows × {df.shape[1]} cols")

            ollama_ok = is_ollama_available(st.session_state.ai_model)
            status_color = "#22C55E" if ollama_ok else "#EF4444"
            status_text = "Connected" if ollama_ok else "Not reachable"
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px; margin: 0.5rem 0;">
                    <div style="width:9px; height:9px; border-radius:50%; background:{status_color};"></div>
                    <span style="font-size:0.85rem; color:var(--text-secondary);">
                        Ollama ({st.session_state.ai_model}): {status_text}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.session_state.ai_model = st.selectbox(
                "AI Model", options=AI_CONFIG.available_models,
                index=AI_CONFIG.available_models.index(st.session_state.ai_model)
                if st.session_state.ai_model in AI_CONFIG.available_models else 0,
            )

            st.divider()
            if st.button("🔄 Start Over (new file)", use_container_width=True):
                for key in ["raw_df", "history", "ai_understanding", "chat_messages",
                            "reviewed_issue_ids", "skipped_issue_ids", "all_issue_ids_seen"]:
                    st.session_state[key] = None if key in ("raw_df", "history", "ai_understanding") else \
                        ([] if key == "chat_messages" else set())
                st.rerun()
        else:
            st.caption("Upload a dataset to begin.")

        st.divider()
        st.caption("Built with Streamlit + Ollama · 100% local, no paid APIs")


# --------------------------------------------------------------------------
# OVERVIEW TAB
# --------------------------------------------------------------------------

def render_overview_tab() -> None:
    df = st.session_state.history.current_df()
    meta = compute_metadata(df, st.session_state.file_size_bytes)
    quality = compute_quality_score(detect_all_issues(df), meta.n_rows, meta.n_cols)

    render_section_header("Dataset Overview", "Key statistics at a glance", "📊")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Rows", f"{meta.n_rows:,}", icon="📏")
    with c2:
        render_kpi_card("Columns", f"{meta.n_cols}", icon="📐")
    with c3:
        render_kpi_card("Memory Usage", f"{meta.memory_usage_mb} MB", icon="💾")
    with c4:
        render_kpi_card("File Size", f"{meta.file_size_mb} MB", icon="📦")

    st.write("")
    c5, c6, c7 = st.columns(3)
    with c5:
        render_kpi_card("Missing Data", f"{meta.missing_pct}%", icon="🕳️",
                         delta_good=meta.missing_pct < 5,
                         delta="Low" if meta.missing_pct < 5 else "High")
    with c6:
        render_kpi_card("Duplicate Rows", f"{meta.duplicate_pct}%", icon="🔁",
                         delta_good=meta.duplicate_pct < 2,
                         delta="Low" if meta.duplicate_pct < 2 else "High")
    with c7:
        dtype_str = ", ".join(f"{v} {k}" for k, v in meta.dtypes_summary.items())
        render_kpi_card("Column Types", dtype_str, icon="🏷️")

    st.write("")
    col_gauge, col_breakdown = st.columns([1, 1.3])
    with col_gauge:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown(f"**Data Quality Score — {quality.label}**")
        st.plotly_chart(render_quality_gauge(quality.score, quality.label, quality.color),
                         use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with col_breakdown:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("**Points Lost by Category**")
        if quality.breakdown:
            bd_df = pd.DataFrame(quality.breakdown, columns=["Category", "Points Lost"])
            bd_df["Category"] = bd_df["Category"].str.replace("_", " ").str.title()
            fig = px.bar(bd_df, x="Points Lost", y="Category", orientation="h",
                         color="Points Lost", color_continuous_scale=["#7C5CFC", "#EF4444"])
            fig.update_layout(
                height=220, margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font={"color": "#C7C2DE"}, showlegend=False, coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.success("No quality issues detected! Your dataset looks clean. ✨")
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("")
    render_section_header("Dataset Preview", "First 50 rows", "👁️")
    st.dataframe(df.head(50), use_container_width=True, height=320)

    render_section_header("Column Details", "Types and non-null counts", "🏷️")
    col_info = pd.DataFrame({
        "Column": df.columns,
        "Data Type": [str(dt) for dt in df.dtypes],
        "Non-Null Count": [df[c].notna().sum() for c in df.columns],
        "Missing": [df[c].isna().sum() for c in df.columns],
        "Unique Values": [df[c].nunique(dropna=True) for c in df.columns],
    })
    st.dataframe(col_info, use_container_width=True, height=300)


# --------------------------------------------------------------------------
# AI INSIGHTS TAB
# --------------------------------------------------------------------------

def render_ai_insights_tab() -> None:
    render_section_header("AI Dataset Understanding", "Powered by your local Llama model", "🤖")

    if not is_ollama_available(st.session_state.ai_model):
        st.warning(
            f"⚠️ Ollama isn't reachable, or the model **{st.session_state.ai_model}** isn't pulled yet.\n\n"
            f"Run these in your terminal:\n```bash\nollama serve\nollama pull {st.session_state.ai_model}\n```"
        )
        return

    df = st.session_state.history.current_df()
    col_classes = classify_columns(df)

    if st.session_state.ai_understanding is None:
        if st.button("✨ Analyze Dataset with AI", type="primary"):
            placeholder = st.empty()
            with placeholder.container():
                render_loading_animation("Llama is reading your dataset...")
            try:
                result = get_dataset_understanding(df, col_classes, model=st.session_state.ai_model)
                st.session_state.ai_understanding = result
            except (AIUnavailableError, ValueError) as exc:
                st.error(f"AI analysis failed: {exc}")
            placeholder.empty()
            st.rerun()
        else:
            st.info("Click the button above to have AI explain your dataset's domain, columns, and use cases.")
            return

    result = st.session_state.ai_understanding
    if not result:
        return

    st.markdown(
        f"""<div class="glass-card fade-in">
            <b style="color:var(--primary-light);">📝 Summary</b><br>
            <span style="color:var(--text-secondary);">{result.get('overall_summary', result.get('dataset_summary', ''))}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"""<div class="glass-card fade-in">
                <b style="color:var(--primary-light);">🏢 Business Domain</b><br>
                <span style="color:var(--text-secondary);">{result.get('business_domain', 'N/A')}</span><br><br>
                <b style="color:var(--primary-light);">🎯 Possible Target Column</b><br>
                <span style="color:var(--text-secondary);">{result.get('possible_target_column') or 'None identified'}</span><br><br>
                <b style="color:var(--primary-light);">🔑 Possible Primary Key</b><br>
                <span style="color:var(--text-secondary);">{result.get('possible_primary_key') or 'None identified'}</span>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        issues_list = "".join(f"<li>{i}</li>" for i in result.get("potential_cleaning_issues", []))
        st.markdown(
            f"""<div class="glass-card fade-in">
                <b style="color:var(--primary-light);">⚠️ Potential Cleaning Issues (AI-flagged)</b>
                <ul style="color:var(--text-secondary);">{issues_list}</ul>
            </div>""",
            unsafe_allow_html=True,
        )

    c3, c4, c5 = st.columns(3)
    for col, key, title, icon in [
        (c3, "ml_use_cases", "ML Use Cases", "🧠"),
        (c4, "dashboard_use_cases", "Dashboard Ideas", "📊"),
        (c5, "bi_use_cases", "BI Use Cases", "📈"),
    ]:
        with col:
            items = "".join(f"<li>{i}</li>" for i in result.get(key, []))
            st.markdown(
                f"""<div class="glass-card fade-in">
                    <b style="color:var(--primary-light);">{icon} {title}</b>
                    <ul style="color:var(--text-secondary); font-size:0.88rem;">{items or '<li>N/A</li>'}</ul>
                </div>""",
                unsafe_allow_html=True,
            )

    render_section_header("Column Meanings", "", "📖")
    meanings = result.get("column_meanings", {})
    if meanings:
        meanings_df = pd.DataFrame(list(meanings.items()), columns=["Column", "AI-Inferred Meaning"])
        st.dataframe(meanings_df, use_container_width=True, height=min(400, 40 + 35 * len(meanings_df)))

    if st.button("🔁 Re-analyze"):
        st.session_state.ai_understanding = None
        st.rerun()


# --------------------------------------------------------------------------
# ISSUES & CLEANING TAB (the core approval workflow)
# --------------------------------------------------------------------------

def render_issues_tab() -> None:
    render_section_header(
        "Issues & Cleaning", "Review every issue and approve fixes — nothing changes automatically.", "🧹"
    )

    df = st.session_state.history.current_df()
    issues = detect_all_issues(df)
    pending_issues = [i for i in issues if i.issue_id not in st.session_state.reviewed_issue_ids]

    # Track every issue_id ever detected this session (cumulative), since a
    # resolved issue disappears from `issues` on the next scan -- using only
    # the *current* scan as the denominator would shrink `total` below
    # `reviewed`, pushing progress above 1.0 (and crashing st.progress).
    current_ids = {i.issue_id for i in issues}
    st.session_state.all_issue_ids_seen = st.session_state.all_issue_ids_seen | current_ids

    total = len(st.session_state.all_issue_ids_seen)
    reviewed = len(st.session_state.reviewed_issue_ids & st.session_state.all_issue_ids_seen)
    progress = max(0.0, min(reviewed / total, 1.0)) if total else 1.0

    st.markdown(f"**Cleaning Progress:** {reviewed} / {total} issues reviewed")
    st.progress(progress)
    st.write("")

    if not issues:
        st.success("🎉 No issues detected! Your dataset is already clean.")
        return

    if not pending_issues:
        st.success("✅ All detected issues have been reviewed. Check the Dashboard or History tab for results.")
        return

    for issue in pending_issues:
        action = render_issue_card(issue, key_prefix=issue.issue_id)

        # AI "Learn More" deep-dive, expandable
        with st.expander("🤖 Ask AI to explain this issue in more detail"):
            if is_ollama_available(st.session_state.ai_model):
                if st.button("Explain with AI", key=f"{issue.issue_id}_explain_btn"):
                    with st.spinner("Llama is thinking..."):
                        try:
                            explanation = explain_issue_with_ai(
                                issue.title, issue.description, issue.affected_columns,
                                model=st.session_state.ai_model,
                            )
                            for k, v in explanation.items():
                                st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                        except (AIUnavailableError, ValueError) as exc:
                            st.error(f"Couldn't get AI explanation: {exc}")
            else:
                st.caption("Ollama isn't reachable — start it to enable AI explanations.")

        if action == "accept":
            method = st.session_state.get(f"{issue.issue_id}_chosen_method", issue.recommended_method)
            df_before = df.copy()
            try:
                columns = issue.affected_columns if issue.affected_columns else \
                    issue.details.get("groups", [[]])[0] if issue.details.get("groups") else []
                df_after = apply_method(df, method, columns)
                st.session_state.history.push(
                    df_after=df_after,
                    action=f"{METHOD_LABELS.get(method, method)} on {issue.title}",
                    method=method,
                    columns=columns,
                    df_before=df_before,
                )
                st.session_state.reviewed_issue_ids.add(issue.issue_id)
                st.toast(f"✅ Applied: {METHOD_LABELS.get(method, method)}", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to apply cleaning method: {exc}")

        elif action == "skip":
            st.session_state.reviewed_issue_ids.add(issue.issue_id)
            st.session_state.skipped_issue_ids.add(issue.issue_id)
            st.toast(f"⏭️ Skipped: {issue.title}", icon="⏭️")
            st.rerun()

        elif action == "review":
            with st.expander("📋 Full details", expanded=True):
                st.json(issue.details)


# --------------------------------------------------------------------------
# LIVE DASHBOARD TAB
# --------------------------------------------------------------------------

def render_dashboard_tab() -> None:
    render_section_header("Live Dashboard", "Charts update automatically as you clean your data", "📈")
    df = st.session_state.history.current_df()
    col_classes = classify_columns(df)

    numeric_cols = col_classes["numerical"]
    categorical_cols = col_classes["categorical"]

    if numeric_cols:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            selected_num = st.selectbox("Distribution of:", numeric_cols, key="dash_hist_col")
            fig = px.histogram(df, x=selected_num, nbins=30, color_discrete_sequence=["#7C5CFC"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font={"color": "#C7C2DE"}, height=320, margin=dict(t=20, b=10))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            selected_box = st.selectbox("Outlier Check (Box Plot):", numeric_cols, key="dash_box_col")
            fig2 = px.box(df, y=selected_box, color_discrete_sequence=["#22D3EE"])
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                font={"color": "#C7C2DE"}, height=320, margin=dict(t=20, b=10))
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

    if len(numeric_cols) >= 2:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("**Correlation Heatmap**")
        corr = df[numeric_cols].corr(numeric_only=True)
        fig3 = px.imshow(corr, color_continuous_scale="Purples", zmin=-1, zmax=1, text_auto=".2f")
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font={"color": "#C7C2DE"}, height=420, margin=dict(t=20, b=10))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    if categorical_cols:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        selected_cat = st.selectbox("Category Breakdown:", categorical_cols, key="dash_pie_col")
        top_vals = df[selected_cat].value_counts().head(10).reset_index()
        top_vals.columns = [selected_cat, "count"]
        fig4 = px.pie(top_vals, names=selected_cat, values="count", hole=0.5,
                      color_discrete_sequence=px.colors.sequential.Purp)
        fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", font={"color": "#C7C2DE"},
                            height=380, margin=dict(t=20, b=10))
        st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("**Missing Value Map**")
    missing_matrix = df.isna().astype(int)
    if missing_matrix.values.sum() > 0:
        fig5 = px.imshow(missing_matrix.T, color_continuous_scale=["#161228", "#EF4444"],
                          aspect="auto")
        fig5.update_layout(paper_bgcolor="rgba(0,0,0,0)", font={"color": "#C7C2DE"},
                            height=280, margin=dict(t=20, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})
    else:
        st.success("No missing values remaining in the dataset. ✨")
    st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# HISTORY TAB
# --------------------------------------------------------------------------

def render_history_tab() -> None:
    render_section_header("Cleaning History", "Full timeline of every applied change, with undo/redo", "🕒")
    history: CleaningHistory = st.session_state.history

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("↩️ Undo", disabled=not history.can_undo(), use_container_width=True):
            history.undo()
            st.rerun()
    with c2:
        if st.button("↪️ Redo", disabled=not history.can_redo(), use_container_width=True):
            history.redo()
            st.rerun()

    st.write("")
    if not history.entries:
        st.info("No cleaning actions applied yet. Approve an issue in the **Issues & Cleaning** tab to begin.")
        return

    for idx, entry in enumerate(reversed(history.entries), 1):
        st.markdown(
            f"""
            <div class="glass-card fade-in" style="padding:1rem 1.4rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="color:var(--success); font-weight:700;">✔</span>
                        <b style="color:var(--text-primary);"> {entry.action}</b>
                    </div>
                    <span style="color:var(--text-muted); font-size:0.82rem;">{entry.timestamp}</span>
                </div>
                <div style="color:var(--text-muted); font-size:0.82rem; margin-top:0.3rem;">
                    Rows: {entry.rows_before:,} → {entry.rows_after:,} &nbsp;|&nbsp;
                    Columns: {entry.cols_before} → {entry.cols_after}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# CHATBOT TAB
# --------------------------------------------------------------------------

def render_chatbot_tab() -> None:
    render_section_header("Chat With Your Data", "Ask anything about your dataset", "💬")

    if not is_ollama_available(st.session_state.ai_model):
        st.warning("⚠️ Ollama isn't reachable. Start it with `ollama serve` to enable the chatbot.")
        return

    df = st.session_state.history.current_df()
    col_classes = classify_columns(df)

    suggestions = [
        "Explain this dataset", "Which columns are problematic?",
        "Suggest an ML algorithm", "Suggest dashboard KPIs", "Suggest SQL queries",
    ]
    st.markdown("**Quick questions:**")
    cols = st.columns(len(suggestions))
    quick_prompt = None
    for col, suggestion in zip(cols, suggestions):
        with col:
            if st.button(suggestion, use_container_width=True, key=f"quick_{suggestion}"):
                quick_prompt = suggestion

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask about your dataset...")
    prompt = quick_prompt or user_input

    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply = chat_with_dataset(
                        prompt, df, col_classes,
                        chat_history=st.session_state.chat_messages[:-1],
                        model=st.session_state.ai_model,
                    )
                except AIUnavailableError as exc:
                    reply = f"⚠️ {exc}"
                st.markdown(reply)
        st.session_state.chat_messages.append({"role": "assistant", "content": reply})


# --------------------------------------------------------------------------
# MAIN APP FLOW
# --------------------------------------------------------------------------

def main() -> None:
    render_sidebar()

    if st.session_state.raw_df is None:
        uploaded_file = render_landing_page()
        if uploaded_file is not None:
            try:
                with st.spinner("Loading and analyzing your dataset..."):
                    df = load_dataset(uploaded_file)
                st.session_state.raw_df = df
                st.session_state.history = CleaningHistory(df)
                st.session_state.file_size_bytes = len(uploaded_file.getvalue())
                st.session_state.file_name = uploaded_file.name
                st.toast("✅ Dataset loaded successfully!", icon="✅")
                st.rerun()
            except DataLoadError as exc:
                st.error(f"❌ Couldn't load this file: {exc}")
        return

    tabs = st.tabs([
        "📊 Overview", "🤖 AI Insights", "🧹 Issues & Cleaning",
        "📈 Dashboard", "🕒 History", "💬 Chatbot",
    ])
    with tabs[0]:
        render_overview_tab()
    with tabs[1]:
        render_ai_insights_tab()
    with tabs[2]:
        render_issues_tab()
    with tabs[3]:
        render_dashboard_tab()
    with tabs[4]:
        render_history_tab()
    with tabs[5]:
        render_chatbot_tab()


if __name__ == "__main__":
    main()
