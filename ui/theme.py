"""
ui/theme.py
-----------
Injects custom CSS into the Streamlit app to override the default look
entirely: gradient backgrounds, glassmorphism cards, animated buttons,
custom sidebar, custom scrollbar, and full dark/light mode support.

Streamlit doesn't allow toggling a class on <body>, so dark/light mode is
implemented by generating two complete CSS variable sets and injecting
whichever one is active in `st.session_state.theme_mode`.
"""

from __future__ import annotations
import streamlit as st


def _palette(mode: str) -> dict:
    if mode == "light":
        return {
            "bg_main": "linear-gradient(135deg, #F0EEFF 0%, #E8F4FF 50%, #FFF0F7 100%)",
            "bg_card": "rgba(255, 255, 255, 0.65)",
            "bg_card_border": "rgba(124, 92, 252, 0.18)",
            "bg_sidebar": "rgba(255, 255, 255, 0.85)",
            "text_primary": "#1A1625",
            "text_secondary": "#5B5570",
            "text_muted": "#8B87A3",
            "shadow": "0 8px 32px rgba(124, 92, 252, 0.12)",
            "input_bg": "rgba(255, 255, 255, 0.9)",
        }
    return {
        "bg_main": "radial-gradient(circle at 15% 20%, #1E1640 0%, #0E0B1A 45%, #0A0814 100%)",
        "bg_card": "rgba(255, 255, 255, 0.05)",
        "bg_card_border": "rgba(255, 255, 255, 0.10)",
        "bg_sidebar": "rgba(18, 14, 34, 0.9)",
        "text_primary": "#F1EEFB",
        "text_secondary": "#C7C2DE",
        "text_muted": "#8B87A3",
        "shadow": "0 8px 32px rgba(0, 0, 0, 0.35)",
        "input_bg": "rgba(255, 255, 255, 0.06)",
    }


def inject_theme() -> None:
    """Inject the full custom CSS stylesheet based on the current theme mode."""
    mode = st.session_state.get("theme_mode", "dark")
    p = _palette(mode)

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

    :root {{
        --primary: #7C5CFC;
        --primary-light: #9C87FF;
        --accent: #22D3EE;
        --success: #22C55E;
        --warning: #F59E0B;
        --danger: #EF4444;
        --text-primary: {p['text_primary']};
        --text-secondary: {p['text_secondary']};
        --text-muted: {p['text_muted']};
        --card-bg: {p['bg_card']};
        --card-border: {p['bg_card_border']};
        --shadow: {p['shadow']};
    }}

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* ---------- App background ---------- */
    .stApp {{
        background: {p['bg_main']};
        background-attachment: fixed;
    }}

    /* Floating gradient orbs for ambience */
    .stApp::before {{
        content: "";
        position: fixed;
        top: -10%;
        right: -5%;
        width: 500px;
        height: 500px;
        background: radial-gradient(circle, rgba(124,92,252,0.25) 0%, transparent 70%);
        border-radius: 50%;
        filter: blur(60px);
        animation: float 12s ease-in-out infinite;
        pointer-events: none;
        z-index: 0;
    }}
    .stApp::after {{
        content: "";
        position: fixed;
        bottom: -10%;
        left: -5%;
        width: 450px;
        height: 450px;
        background: radial-gradient(circle, rgba(34,211,238,0.18) 0%, transparent 70%);
        border-radius: 50%;
        filter: blur(60px);
        animation: float 15s ease-in-out infinite reverse;
        pointer-events: none;
        z-index: 0;
    }}

    @keyframes float {{
        0%, 100% {{ transform: translate(0, 0) scale(1); }}
        50% {{ transform: translate(-30px, 40px) scale(1.08); }}
    }}

    /* ---------- Typography ---------- */
    h1, h2, h3, h4, h5, h6 {{
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        color: var(--text-primary) !important;
        font-weight: 700 !important;
    }}
    p, span, label, .stMarkdown {{
        color: var(--text-secondary);
    }}

    /* ---------- Hero title ---------- */
    .hero-title {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 4rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(135deg, #7C5CFC 0%, #9C87FF 40%, #22D3EE 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        background-size: 200% auto;
        animation: shine 4s linear infinite, fadeInUp 1s ease;
        margin-bottom: 0;
        line-height: 1.1;
    }}
    @keyframes shine {{
        to {{ background-position: 200% center; }}
    }}
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(24px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    .hero-subtitle {{
        text-align: center;
        font-size: 1.25rem;
        color: var(--text-secondary);
        font-weight: 500;
        margin-top: 0.5rem;
        animation: fadeInUp 1.2s ease;
    }}

    .hero-badge {{
        display: inline-block;
        padding: 6px 16px;
        border-radius: 999px;
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        color: var(--primary-light);
        font-size: 0.85rem;
        font-weight: 600;
        backdrop-filter: blur(10px);
        margin-bottom: 1rem;
    }}

    /* ---------- Glass cards ---------- */
    .glass-card {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 20px;
        padding: 1.6rem;
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        box-shadow: var(--shadow);
        transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
        position: relative;
        z-index: 1;
        margin-bottom: 1rem;
    }}
    .glass-card:hover {{
        transform: translateY(-4px);
        border-color: var(--primary);
        box-shadow: 0 12px 40px rgba(124, 92, 252, 0.25);
    }}

    .feature-card {{
        text-align: center;
        padding: 2rem 1.4rem;
    }}
    .feature-icon {{
        font-size: 2.4rem;
        margin-bottom: 0.8rem;
        display: block;
    }}
    .feature-title {{
        font-weight: 700;
        font-size: 1.05rem;
        color: var(--text-primary);
        margin-bottom: 0.4rem;
    }}
    .feature-desc {{
        font-size: 0.88rem;
        color: var(--text-muted);
        line-height: 1.5;
    }}

    /* ---------- KPI metric cards ---------- */
    .kpi-card {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        padding: 1.1rem 1.3rem;
        backdrop-filter: blur(16px);
        box-shadow: var(--shadow);
        transition: transform 0.2s ease;
    }}
    .kpi-card:hover {{ transform: translateY(-2px); }}
    .kpi-label {{
        font-size: 0.78rem;
        color: var(--text-muted);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .kpi-value {{
        font-size: 1.9rem;
        font-weight: 800;
        color: var(--text-primary);
        font-family: 'Plus Jakarta Sans', sans-serif;
        margin-top: 0.15rem;
    }}
    .kpi-delta-good {{ color: var(--success); font-size: 0.82rem; font-weight: 600; }}
    .kpi-delta-bad {{ color: var(--danger); font-size: 0.82rem; font-weight: 600; }}

    /* ---------- Issue cards ---------- */
    .issue-card {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-left: 4px solid var(--sev-color, var(--primary));
        border-radius: 16px;
        padding: 1.4rem 1.6rem;
        backdrop-filter: blur(16px);
        box-shadow: var(--shadow);
        margin-bottom: 1.2rem;
    }}
    .severity-badge {{
        display: inline-block;
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        background: color-mix(in srgb, var(--sev-color, var(--primary)) 18%, transparent);
        color: var(--sev-color, var(--primary));
    }}

    /* ---------- Buttons ---------- */
    .stButton > button {{
        border-radius: 12px !important;
        font-weight: 600 !important;
        border: 1px solid var(--card-border) !important;
        background: linear-gradient(135deg, rgba(124,92,252,0.15), rgba(34,211,238,0.10)) !important;
        color: var(--text-primary) !important;
        transition: all 0.2s ease !important;
        backdrop-filter: blur(10px);
    }}
    .stButton > button:hover {{
        transform: translateY(-2px);
        border-color: var(--primary) !important;
        box-shadow: 0 6px 20px rgba(124, 92, 252, 0.35) !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, #7C5CFC, #22D3EE) !important;
        border: none !important;
        color: white !important;
    }}

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {{
        background: {p['bg_sidebar']};
        backdrop-filter: blur(20px);
        border-right: 1px solid var(--card-border);
    }}

    /* ---------- Inputs ---------- */
    .stTextInput input, .stSelectbox > div > div, .stNumberInput input {{
        background: {p['input_bg']} !important;
        border-radius: 10px !important;
        border: 1px solid var(--card-border) !important;
        color: var(--text-primary) !important;
    }}

    /* ---------- Progress bar ---------- */
    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, #7C5CFC, #22D3EE) !important;
    }}

    /* ---------- File uploader ---------- */
    [data-testid="stFileUploader"] {{
        border-radius: 16px;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        background: var(--card-bg) !important;
        border: 2px dashed var(--card-border) !important;
        border-radius: 16px !important;
    }}

    /* ---------- Tabs ---------- */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background: transparent;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: var(--card-bg);
        border-radius: 10px;
        border: 1px solid var(--card-border);
        color: var(--text-secondary);
        padding: 8px 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, rgba(124,92,252,0.25), rgba(34,211,238,0.15)) !important;
        color: var(--text-primary) !important;
        border-color: var(--primary) !important;
    }}

    /* ---------- Scrollbar ---------- */
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{
        background: linear-gradient(180deg, #7C5CFC, #22D3EE);
        border-radius: 10px;
    }}

    /* ---------- Misc ---------- */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{background: transparent !important;}}

    .fade-in {{ animation: fadeInUp 0.6s ease; }}

    .quality-ring-label {{
        text-align: center;
        font-weight: 700;
        font-size: 0.95rem;
        margin-top: -8px;
        color: var(--text-secondary);
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def theme_toggle_widget() -> None:
    """Render a small dark/light mode toggle in the sidebar."""
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"

    labels = {"dark": "🌙 Dark Mode", "light": "☀️ Light Mode"}
    current = st.session_state.theme_mode
    if st.sidebar.button(labels[current], use_container_width=True, key="theme_toggle_btn"):
        st.session_state.theme_mode = "light" if current == "dark" else "dark"
        st.rerun()
