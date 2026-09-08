"""
audit_intel_app.py
------------------
Audit Intelligence — global banking risk & controls briefing.

Run with:      streamlit run audit_intel_app.py

Requires `news_providers.py` in the same folder.
API keys go in config.py (rename config_template.py), environment
variables, Streamlit secrets, or the in-page fields.
"""

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import streamlit as st

import news_providers as npv

# Optional config.py — any subset of the three keys may be defined there.
CONFIG_KEYS = {}
try:
    import config as _cfg
    for _name in ("API_KEY", "NEWSAPI_KEY", "APITUBE_KEY", "APITUBE_API_KEY",
                  "NEWSDATA_KEY", "NEWSDATA_API_KEY"):
        if hasattr(_cfg, _name):
            CONFIG_KEYS[_name] = getattr(_cfg, _name)
except ImportError:
    pass


# ---------------------------------------------------------
# 1. APP CONFIGURATION & LIGHT EDITORIAL PALETTE
# ---------------------------------------------------------

st.set_page_config(
    page_title="Audit Intelligence | Global Banking Briefing",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --bg: #F7F8FA;
        --card: #FFFFFF;
        --border: #E5E7EB;
        --text-primary: #111827;
        --text-secondary: #4B5563;
        --text-muted: #6B7280;
        --accent-blue: #2563EB;
        --accent-blue-dark: #1D4ED8;
        --up: #16A34A;
        --down: #DC2626;
        --amber: #B45309;
    }

    .stApp {
        background: var(--bg);
        color: var(--text-primary);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    #MainMenu, header[data-testid="stHeader"] { background: transparent; }

    /* ---------------- Top navigation ---------------- */
    .topnav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 6px 2px 18px 2px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 8px;
    }
    .topnav-left { display: flex; align-items: center; gap: 18px; }

    /* ---- Emblem: deep navy tile, inner bevel, blue rim glow ---- */
    .logo-icon {
        position: relative;
        width: 62px; height: 62px;
        border-radius: 18px;
        background:
            radial-gradient(120% 120% at 28% 18%, #3B82F6 0%, #1D4ED8 42%, #14264F 100%);
        display: flex; align-items: center; justify-content: center;
        box-shadow:
            0 10px 26px rgba(29, 78, 216, 0.38),
            0 2px 5px rgba(11, 18, 32, 0.22),
            inset 0 1px 0 rgba(255, 255, 255, 0.42),
            inset 0 -2px 6px rgba(3, 10, 26, 0.45);
        flex-shrink: 0;
    }
    .logo-icon::after {
        content: "";
        position: absolute; inset: 0;
        border-radius: 18px;
        border: 1px solid rgba(255, 255, 255, 0.20);
        pointer-events: none;
    }
    .logo-icon svg { width: 34px; height: 34px; display: block; }

    /* ---- Wordmark ---- */
    .logo-lockup { display: flex; flex-direction: column; }
    .logo-textrow { display: flex; align-items: center; gap: 12px; }
    .logo-text {
        font-weight: 900;
        font-size: 38px;
        letter-spacing: -1.5px;
        line-height: 1.02;
        color: #0B1220;
        white-space: nowrap;
    }
    /* Two-tone: "Audit" in ink, "Intelligence" in a blue gradient */
    .logo-text .lt-accent {
        background: linear-gradient(92deg, #2563EB 0%, #4F46E5 55%, #7C3AED 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        color: #2563EB;
    }

    /* Live status pill */
    .live-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(22, 163, 74, 0.10);
        border: 1px solid rgba(22, 163, 74, 0.35);
        color: #15803D;
        font-size: 10px; font-weight: 800;
        letter-spacing: 1.2px; text-transform: uppercase;
        padding: 4px 10px; border-radius: 999px;
        white-space: nowrap;
    }
    .live-dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: #16A34A;
        box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.65);
        animation: livepulse 2s infinite;
    }
    @keyframes livepulse {
        0%   { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.60); }
        70%  { box-shadow: 0 0 0 7px rgba(22, 163, 74, 0); }
        100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
    }

    .logo-sub {
        display: flex; align-items: center; gap: 9px;
        font-size: 11px; font-weight: 700; color: var(--text-muted);
        letter-spacing: 2.1px; text-transform: uppercase; margin-top: 7px;
    }
    .logo-rule {
        width: 30px; height: 3px; border-radius: 2px;
        background: linear-gradient(90deg, #2563EB, #7C3AED);
        flex-shrink: 0;
    }

    /* ---- Top-right principal block ---- */
    .topnav-user {
        display: flex; align-items: center; gap: 16px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 12px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .topnav-user-meta { text-align: right; line-height: 1.3; }
    .topnav-user-label {
        font-size: 10px; font-weight: 700; color: var(--accent-blue);
        letter-spacing: 1px; text-transform: uppercase; margin-bottom: 3px;
    }
    .topnav-user-name { font-weight: 800; font-size: 20px; color: #0B1220; letter-spacing: -0.3px; }
    .topnav-user-title { font-size: 13.5px; color: var(--text-secondary); font-weight: 500; }
    .topnav-user-stamp { font-size: 11px; color: var(--text-muted); margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
    .avatar-photo {
        width: 68px; height: 68px; border-radius: 50%;
        object-fit: cover; flex-shrink: 0;
        border: 3px solid #fff;
        box-shadow: 0 0 0 2px var(--accent-blue);
    }
    .avatar-circle-lg {
        width: 68px; height: 68px; border-radius: 50%;
        background: linear-gradient(135deg, #2563EB, #7C3AED);
        display: flex; align-items: center; justify-content: center;
        font-weight: 800; font-size: 26px; color: #fff; flex-shrink: 0;
        box-shadow: 0 0 0 2px var(--accent-blue);
    }

    .action-caption {
        font-size: 11.5px; color: var(--text-muted);
        font-family: 'JetBrains Mono', monospace; padding-top: 10px;
    }

    /* ---------------- Section headings ---------------- */
    .section-heading {
        font-size: 15px;
        font-weight: 700;
        color: #0B1220;
        margin: 4px 0 14px 0;
    }
    .page-title {
        font-size: 26px;
        font-weight: 800;
        color: #0B1220;
        letter-spacing: -0.5px;
        margin-bottom: 2px;
    }
    .page-subtitle {
        font-size: 13px;
        color: var(--text-secondary);
        margin-bottom: 20px;
    }

    /* ================= TAB VISIBILITY FIX =================
       Streamlit nests each tab label inside <p>/<div> nodes and applies its
       own theme colour + a red/pink highlight bar. Colour therefore has to be
       forced on the INNER nodes (and via -webkit-text-fill-color) or the
       inactive tabs render almost invisible against the light background. */
    div[data-testid="stTabs"] { margin-top: 4px; margin-bottom: 20px; }
    div[data-testid="stTabs"] [role="tablist"] {
        gap: 4px;
        border-bottom: 1px solid var(--border);
        background: transparent !important;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        border-radius: 0 !important;
        padding: 9px 18px !important;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        background: transparent !important;
        border: none !important;
        border-bottom: 3px solid transparent !important;
        opacity: 1 !important;
    }
    div[data-testid="stTabs"] button[role="tab"],
    div[data-testid="stTabs"] button[role="tab"] *,
    div[data-testid="stTabs"] button[role="tab"] p {
        color: #0B1220 !important;
        -webkit-text-fill-color: #0B1220 !important;
        font-size: 13px !important;
        font-weight: 700 !important;
        opacity: 1 !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:hover,
    div[data-testid="stTabs"] button[role="tab"]:hover *,
    div[data-testid="stTabs"] button[role="tab"]:hover p {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] *,
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
        color: var(--accent-blue) !important;
        -webkit-text-fill-color: var(--accent-blue) !important;
        font-weight: 800 !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        border-bottom: 3px solid var(--accent-blue) !important;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] [data-baseweb="tab-border"] {
        background-color: transparent !important;
        display: none !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:focus,
    div[data-testid="stTabs"] button[role="tab"]:focus-visible {
        outline: none !important;
        box-shadow: none !important;
    }
    /* ======================================================= */

    /* ---------------- Inputs ---------------- */
    .stTextInput>div>div>input {
        background-color: #fff !important;
        border: 1px solid var(--border) !important;
        color: var(--text-primary) !important;
        border-radius: 10px !important;
        padding: 11px 16px !important;
        font-size: 14px !important;
    }
    .stTextInput>div>div>input:focus {
        border-color: var(--accent-blue) !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
    }

    /* ---------------- Buttons ---------------- */
    .stButton>button {
        background: var(--accent-blue);
        color: #fff !important;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 13.5px;
        padding: 9px 18px;
    }
    .stButton>button * { color: #fff !important; -webkit-text-fill-color: #fff !important; }
    .stButton>button:hover { background: var(--accent-blue-dark); }
    [data-testid="stDownloadButton"]>button {
        background: #fff;
        color: var(--accent-blue) !important;
        border: 1px solid var(--accent-blue);
        border-radius: 8px;
        font-weight: 600;
    }
    [data-testid="stDownloadButton"]>button:hover { background: #EFF6FF; }

    /* ---------------- Legible light theme inside controls ---------------- */
    [data-testid="stExpander"] {
        background: #fff !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
    }
    [data-testid="stExpander"] summary {
        background: #fff !important;
        color: var(--text-primary) !important;
    }
    [data-testid="stExpander"] summary:hover { color: var(--accent-blue) !important; }
    [data-testid="stExpanderDetails"] { background: #fff !important; }
    [data-testid="stExpander"] label,
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] span,
    [data-testid="stExpander"] div { color: var(--text-primary) !important; }
    [data-testid="stSlider"] [data-testid="stTickBarMin"],
    [data-testid="stSlider"] [data-testid="stTickBarMax"] { color: var(--text-secondary) !important; }
    [data-testid="stSlider"] div[data-baseweb="slider"] > div { background: #E5E7EB !important; }
    [data-testid="stSlider"] div[role="slider"] {
        background-color: var(--accent-blue) !important;
        border-color: var(--accent-blue) !important;
    }
    div[data-baseweb="tag"] {
        background-color: rgba(37, 99, 235, 0.10) !important;
        border: 1px solid rgba(37, 99, 235, 0.35) !important;
        color: var(--accent-blue) !important;
    }
    div[data-baseweb="tag"] span { color: var(--accent-blue) !important; }
    div[data-baseweb="tag"] svg { fill: var(--accent-blue) !important; }

    /* ---------------- Featured Analysis hero ---------------- */
    .featured-hero {
        position: relative;
        height: 360px;
        border-radius: 16px;
        background-size: cover;
        background-position: center;
        /* Fallback tint if the hero image fails to load */
        background-color: #1E3A8A;
        overflow: hidden;
        margin-bottom: 30px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .featured-badge {
        position: absolute; top: 20px; left: 20px;
        color: #fff; font-size: 11px; font-weight: 700;
        padding: 5px 12px; border-radius: 6px;
        text-transform: uppercase; letter-spacing: 0.5px;
        z-index: 2;
    }
    .featured-text { position: absolute; bottom: 24px; left: 28px; right: 28px; z-index: 2; }
    .featured-title {
        font-size: 27px; font-weight: 800; color: #fff; line-height: 1.28;
        margin-bottom: 8px; text-shadow: 0 2px 10px rgba(0,0,0,0.35);
    }
    .featured-meta { font-size: 13px; color: rgba(255,255,255,0.85); font-weight: 500; }
    .featured-link-overlay { position: absolute; inset: 0; z-index: 3; }

    /* ---------------- Insight cards ---------------- */
    .insight-card {
        display: flex;
        gap: 20px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px;
        margin-bottom: 16px;
        transition: box-shadow 0.15s ease, border-color 0.15s ease;
    }
    .insight-card:hover { border-color: #D1D5DB; box-shadow: 0 4px 14px rgba(0,0,0,0.05); }

    /* Thumbnails are real <img> elements (not CSS backgrounds) so that a
       broken/hotlink-blocked remote image still paints the element's OWN
       background — i.e. the newspaper placeholder shows through automatically. */
    .insight-thumb {
        width: 180px; min-width: 180px; height: 128px;
        border-radius: 10px;
        object-fit: cover;
        background-color: #EEF2F7;
        background-repeat: no-repeat;
        background-position: center;
        background-size: 52px 52px;
        border: 1px solid var(--border);
        display: block;
    }
    .insight-content { display: flex; flex-direction: column; min-width: 0; }
    .insight-meta-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
    .badge {
        display: inline-block; color: #fff; font-size: 10.5px; font-weight: 700;
        padding: 3px 10px; border-radius: 5px; text-transform: uppercase; letter-spacing: 0.4px;
    }
    .insight-date { font-size: 12px; color: var(--text-muted); font-weight: 500; }
    .insight-title-link { text-decoration: none; }
    .insight-title {
        font-size: 17px; font-weight: 700; color: #0B1220;
        line-height: 1.35; margin-bottom: 6px;
    }
    .insight-title-link:hover .insight-title { color: var(--accent-blue); }
    .insight-desc {
        font-size: 13.5px; color: var(--text-secondary); line-height: 1.55;
        margin-bottom: 12px;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }
    .insight-footer { display: flex; justify-content: flex-end; align-items: center; margin-top: auto; }
    .read-link {
        font-size: 12.5px; font-weight: 700; color: var(--accent-blue); text-decoration: none;
    }
    .read-link:hover { text-decoration: underline; }

    /* ---------------- Right sidebar panels ---------------- */
    .side-panel {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }
    .side-panel-title {
        font-size: 11px; font-weight: 700; color: var(--text-secondary);
        text-transform: uppercase; letter-spacing: 0.8px;
        margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
    }
    .filter-row, .pulse-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 8px 0; border-bottom: 1px solid #F3F4F6; font-size: 13px; color: #374151;
    }
    .filter-row:last-child, .pulse-row:last-child { border-bottom: none; }
    .filter-value { font-weight: 600; color: var(--text-primary); }
    .pulse-value { font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; }

    /* ---------------- Market panel ---------------- */
    .mkt-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 9px 0; border-bottom: 1px solid #F3F4F6;
    }
    .mkt-row:last-child { border-bottom: none; }
    .mkt-name { font-size: 13px; font-weight: 600; color: #374151; }
    .mkt-sub { font-size: 10.5px; color: var(--text-muted); font-weight: 500; }
    .mkt-right { text-align: right; }
    .mkt-price { font-size: 13.5px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; }
    .mkt-chg { font-size: 11.5px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .mkt-up { color: var(--up); }
    .mkt-down { color: var(--down); }
    .mkt-stamp { font-size: 10.5px; color: var(--text-muted); margin-top: 12px; }

    /* ---------------- Risk radar ---------------- */
    .risk-row { padding: 8px 0; border-bottom: 1px solid #F3F4F6; }
    .risk-row:last-child { border-bottom: none; }
    .risk-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .risk-name { font-size: 12.5px; font-weight: 600; color: #374151; }
    .risk-count { font-size: 11px; font-weight: 700; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; }
    .risk-track { height: 6px; background: #F3F4F6; border-radius: 3px; overflow: hidden; }
    .risk-fill { height: 100%; border-radius: 3px; }

    .alert-item {
        display: block; text-decoration: none;
        padding: 9px 0; border-bottom: 1px solid #F3F4F6;
    }
    .alert-item:last-child { border-bottom: none; }
    .alert-tag {
        font-size: 9.5px; font-weight: 800; color: var(--amber);
        letter-spacing: 0.6px; text-transform: uppercase;
    }
    .alert-text {
        font-size: 12.5px; color: #0B1220; font-weight: 600; line-height: 1.4; margin-top: 3px;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }
    .alert-item:hover .alert-text { color: var(--accent-blue); }

    .cta-panel {
        background: linear-gradient(135deg, #2563EB, #1D4ED8);
        border-radius: 14px;
        padding: 20px 22px 6px 22px;
        color: #fff;
        margin-bottom: -4px;
    }
    .cta-title { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
    .cta-desc { font-size: 12.5px; color: rgba(255,255,255,0.85); line-height: 1.5; margin-bottom: 14px; }

    .empty-state-panel {
        text-align: center; padding: 48px;
        background: var(--card); border-radius: 16px; border: 1px dashed var(--border);
        margin-top: 14px;
    }

    /* ---------------- Footer ---------------- */
    .app-footer {
        display: flex; justify-content: space-between; align-items: flex-start;
        padding-top: 22px; margin-top: 8px;
    }
    .footer-brand { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 800; font-size: 14.5px; color: #0B1220; }
    .footer-tagline { font-size: 12px; color: var(--text-muted); max-width: 320px; line-height: 1.5; }
    .footer-links { display: flex; gap: 22px; font-size: 12.5px; color: var(--text-secondary); font-weight: 600; }
    .footer-copyright { font-size: 11.5px; color: var(--text-muted); margin-top: 18px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 2. CATEGORIES, SCORING VOCABULARY & BRANDING
# ---------------------------------------------------------

CATEGORIES = {k: {} for k in npv.CATEGORY_NAMES}

CATEGORY_DISPLAY = {
    "Transformation": "Transformation",
    "Regulation": "Regulation",
    "People": "People",
    "Global Banks": "Global Banking",
}
CATEGORY_COLORS = {
    "Transformation": "#2563EB",
    "Regulation": "#16A34A",
    "People": "#6B7280",
    "Global Banks": "#7C3AED",
}

# Head of Internal Audit Department — shown top-right
PRAGATI_NAME = "Pragati"
PRAGATI_TITLE = "Head of Internal Audit"
# NOTE: paste your base64 JPEG string here to show the photo.
PRAGATI_PHOTO_B64 = "PASTE_YOUR_EXISTING_BASE64_STRING_HERE"

AUDIT_TERMS = [
    "internal audit", "external audit", "audit committee", "auditor",
    "audit finding", "audit findings", "internal control", "internal controls",
    "control weakness", "control weaknesses", "control deficiency",
    "control deficiencies", "governance", "risk management", "operational risk",
    "model risk", "compliance", "regulatory", "regulation", "supervision",
    "supervisory", "enforcement", "aml", "anti-money laundering", "kyc",
    "sanctions", "fraud", "misconduct", "financial crime",
    "bank", "banking", "lender", "rbi", "central bank", "basel", "npa",
    "asset quality", "provisioning", "capital adequacy", "credit risk",
    "liquidity", "penalty", "fined", "probe", "investigation", "whistleblower",
    "disclosure", "restatement", "irregularities", "lapses",
]

ALERT_TERMS = [
    "enforcement", "penalty", "fined", "fine", "fraud", "misconduct",
    "investigation", "probe", "money laundering", "aml", "sanctions",
    "irregularities", "lapses", "control deficiency", "restatement",
    "whistleblower", "settlement",
]

CATEGORY_TERMS = {
    "Transformation": [
        "digital transformation", "modernization", "modernisation", "core banking",
        "automation", "artificial intelligence", "generative ai", "genai",
        "machine learning", "cloud", "digital banking", "technology transformation",
        "operating model",
    ],
    "Regulation": [
        "regulation", "regulatory", "rbi", "basel", "prudential", "supervision",
        "supervisory", "enforcement", "aml", "anti-money laundering", "kyc",
        "sanctions", "capital requirements", "regulatory capital", "compliance",
    ],
    "People": [
        "appointed", "appointment", "ceo", "cfo", "cro", "ciso", "chief audit",
        "internal audit", "audit committee", "board", "director", "chairman",
        "chairwoman", "leadership", "executive",
    ],
    "Global Banks": [
        "hsbc", "jpmorgan", "jpmorgan chase", "citi", "citigroup", "barclays",
        "deutsche bank", "ubs", "bnpparibas", "bnp paribas", "santander",
        "standard chartered", "bank of america", "goldman sachs", "morgan stanley",
        "wells fargo", "ing", "icbc", "mufg", "mizuho",
    ],
}


def placeholder_data_uri(hex_color="#94A3B8"):
    """
    Inline, URL-encoded newspaper SVG used as the thumbnail fallback.
    Returned as a data: URI so it needs no network call and cannot itself fail.
    """
    c = hex_color.replace("#", "%23")
    return (
        "data:image/svg+xml;charset=utf-8,"
        "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
        f"stroke='{c}' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E"
        "%3Cpath d='M4 5h13a1 1 0 0 1 1 1v12a2 2 0 0 0 2 2H5a1 1 0 0 1-1-1V5z'/%3E"
        "%3Cpath d='M18 8h2a1 1 0 0 1 1 1v9a2 2 0 0 1-2 2'/%3E"
        "%3Cpath d='M7 8h7'/%3E%3Cpath d='M7 11.5h7'/%3E"
        "%3Cpath d='M7 15h4'/%3E%3Cpath d='M13.5 15h.5'/%3E"
        "%3C/svg%3E"
    )


RISK_THEMES = {
    "Financial crime / AML": (["aml", "anti-money laundering", "money laundering", "kyc", "financial crime", "sanctions"], "#DC2626"),
    "Enforcement / penalties": (["enforcement", "penalty", "fined", "fine", "settlement", "supervisory action"], "#EA580C"),
    "Fraud & misconduct": (["fraud", "misconduct", "irregularities", "lapses", "whistleblower"], "#B45309"),
    "Credit & asset quality": (["npa", "asset quality", "provisioning", "credit risk", "bad loan", "slippage"], "#7C3AED"),
    "Technology & AI risk": (["artificial intelligence", "generative ai", "cloud", "automation", "core banking", "outage"], "#2563EB"),
}


# ---------------------------------------------------------
# 3. KEY RESOLUTION & SCORING
# ---------------------------------------------------------

def _lookup_secret(*names):
    """Check config.py, then env vars, then Streamlit secrets — first hit wins."""
    for name in names:
        val = CONFIG_KEYS.get(name)
        if val and str(val).strip():
            return str(val).strip()

    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            return val

    try:
        for name in names:
            val = st.secrets.get(name, "")
            if val:
                return str(val).strip()
    except Exception:
        pass

    return ""


def get_api_keys():
    """Resolve a key for each of the three providers. Any may be blank."""
    return {
        "newsapi": _lookup_secret("NEWSAPI_KEY", "API_KEY"),
        "apitube": _lookup_secret("APITUBE_KEY", "APITUBE_API_KEY"),
        "newsdata": _lookup_secret("NEWSDATA_KEY", "NEWSDATA_API_KEY"),
    }


def audit_relevance(text):
    """Simple, transparent audit relevance score."""
    score = 0
    for term in AUDIT_TERMS:
        if term in text:
            score += 5

    for term in [
        "internal audit", "audit committee", "internal controls",
        "control deficiency", "regulatory enforcement",
        "model risk", "financial crime",
    ]:
        if term in text:
            score += 10

    return min(score, 100)


def classify_article(article):
    """Classify using transparent keyword scoring."""
    text = " ".join([
        article.get("title") or "",
        article.get("description") or "",
        article.get("content") or "",
    ]).lower()

    scores = {}
    for category, terms in CATEGORY_TERMS.items():
        score = 0
        for term in terms:
            if term in text:
                score += 1
        scores[category] = score

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        best_category = "Regulation"

    return best_category, scores[best_category]


@st.cache_data(ttl=300, show_spinner=False)
def load_news(api_keys, lookback_days, min_relevance, fuzzy_threshold, categories):
    """
    Pull from every configured provider, dedupe across them, then score.
    Fetching/normalizing/deduping lives in news_providers.py; this function
    only applies the audit-specific relevance and category logic.
    """
    records, errors, fetch_stats = npv.fetch_all(
        api_keys=dict(api_keys),
        lookback_days=lookback_days,
        categories=list(categories) if categories else None,
        fuzzy_threshold=fuzzy_threshold,
    )

    cleaned = []
    dropped_low_relevance = 0

    for rec in records:
        text = " ".join([
            rec.get("title") or "",
            rec.get("description") or "",
            rec.get("content") or "",
        ]).lower()

        relevance = audit_relevance(text)
        if relevance < min_relevance:
            dropped_low_relevance += 1
            continue

        category, category_score = classify_article(rec)

        cleaned.append({
            "category": category,
            "audit_relevance": relevance,
            "category_score": category_score,
            "title": rec.get("title") or "Untitled",
            "description": rec.get("description") or "",
            "source": rec.get("source") or "Institutional Source",
            "publishedAt": rec.get("published_at") or "",
            "url": rec.get("url") or "",
            "author": rec.get("author") or "",
            "image_url": rec.get("image_url") or "",
        })

    cleaned.sort(key=lambda x: (x["audit_relevance"], x["publishedAt"]), reverse=True)

    stats = dict(fetch_stats)
    stats["dropped_low_relevance"] = dropped_low_relevance
    stats["kept"] = len(cleaned)
    return cleaned, errors, stats


def format_relative_time(pub_date_str):
    if not pub_date_str:
        return "Recent"
    try:
        clean_str = pub_date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        now = datetime.now(timezone.utc)
        diff = now - dt
        days = diff.days
        if days == 0:
            return "Today"
        elif days == 1:
            return "1 day ago"
        elif days < 7:
            return f"{days} days ago"
        elif days < 14:
            return "1 week ago"
        else:
            return f"{days // 7} weeks ago"
    except Exception:
        return pub_date_str[:10] if len(pub_date_str) >= 10 else "Recent"


def ist_now_str():
    stamp = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return stamp.strftime("%d %b %Y, %H:%M IST")


# ---------------------------------------------------------
# 4. LIVE MARKET SNAPSHOT
# ---------------------------------------------------------

MARKET_TICKERS = [
    ("^BSESN",   "SENSEX",      "BSE 30"),
    ("^NSEI",    "NIFTY 50",    "NSE"),
    ("^NSEBANK", "BANK NIFTY",  "NSE Banks"),
    ("USDINR=X", "USD / INR",   "Spot FX"),
    ("BZ=F",     "Brent Crude", "USD/bbl"),
    ("GC=F",     "Gold",        "USD/oz"),
]

YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuditIntel/1.0)"}


def fetch_quote(symbol):
    resp = requests.get(
        YF_CHART_URL.format(symbol=symbol),
        params={"range": "1d", "interval": "5m"},
        headers=YF_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")

    if price is None or not prev:
        raise ValueError("No price data returned")

    change = price - prev
    pct = (change / prev) * 100
    return {"price": float(price), "change": float(change), "pct": float(pct)}


@st.cache_data(ttl=180, show_spinner=False)
def load_market_snapshot():
    results = {}

    with ThreadPoolExecutor(max_workers=len(MARKET_TICKERS)) as executor:
        futures = {
            executor.submit(fetch_quote, symbol): symbol
            for symbol, _, _ in MARKET_TICKERS
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception:
                results[symbol] = None

    return results, ist_now_str()


def render_market_panel():
    quotes, stamp = load_market_snapshot()

    rows_html = ""
    for symbol, name, sub in MARKET_TICKERS:
        q = quotes.get(symbol)

        if not q:
            rows_html += (
                f'<div class="mkt-row">'
                f'<div><div class="mkt-name">{name}</div><div class="mkt-sub">{sub}</div></div>'
                f'<div class="mkt-right"><div class="mkt-price" style="color:#9CA3AF;">—</div>'
                f'<div class="mkt-chg" style="color:#9CA3AF;">unavailable</div></div>'
                f'</div>'
            )
            continue

        cls = "mkt-up" if q["pct"] >= 0 else "mkt-down"
        arrow = "▲" if q["pct"] >= 0 else "▼"
        rows_html += (
            f'<div class="mkt-row">'
            f'<div><div class="mkt-name">{name}</div><div class="mkt-sub">{sub}</div></div>'
            f'<div class="mkt-right"><div class="mkt-price">{q["price"]:,.2f}</div>'
            f'<div class="mkt-chg {cls}">{arrow} {abs(q["change"]):,.2f} ({abs(q["pct"]):.2f}%)</div></div>'
            f'</div>'
        )

    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">📈 Live Market Snapshot</div>
        {rows_html}
        <div class="mkt-stamp">Last refreshed {stamp} · delayed data, indicative only</div>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# 5. RISK RADAR + PRIORITY ALERTS
# ---------------------------------------------------------

def render_risk_radar(rows):
    if not rows:
        return

    counts = {}
    for theme, (terms, color) in RISK_THEMES.items():
        n = 0
        for row in rows:
            text = f'{row["title"]} {row["description"]}'.lower()
            if any(t in text for t in terms):
                n += 1
        counts[theme] = (n, color)

    peak = max((n for n, _ in counts.values()), default=0)
    if peak == 0:
        return

    rows_html = ""
    for theme, (n, color) in sorted(counts.items(), key=lambda x: x[1][0], reverse=True):
        width = int((n / peak) * 100) if peak else 0
        rows_html += (
            f'<div class="risk-row">'
            f'<div class="risk-head"><span class="risk-name">{theme}</span>'
            f'<span class="risk-count">{n}</span></div>'
            f'<div class="risk-track"><div class="risk-fill" style="width:{width}%; background:{color};"></div></div>'
            f'</div>'
        )

    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">🎯 Risk Radar · Theme Exposure</div>
        {rows_html}
    </div>
    """, unsafe_allow_html=True)


def render_priority_alerts(rows, limit=5):
    flagged = []
    for row in rows:
        text = f'{row["title"]} {row["description"]}'.lower()
        hits = [t for t in ALERT_TERMS if t in text]
        if hits:
            flagged.append((len(hits), row, hits[0]))

    if not flagged:
        return

    flagged.sort(key=lambda x: (x[0], x[1]["audit_relevance"]), reverse=True)

    items_html = ""
    for _, row, tag in flagged[:limit]:
        items_html += (
            f'<a class="alert-item" href="{row["url"]}" target="_blank">'
            f'<div class="alert-tag">⚠ {tag.upper()} · {row["source"]}</div>'
            f'<div class="alert-text">{row["title"]}</div>'
            f'</a>'
        )

    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">🚨 Priority Alerts ({len(flagged)})</div>
        {items_html}
    </div>
    """, unsafe_allow_html=True)


def render_source_panel(rows, limit=5):
    if not rows:
        return

    counter = Counter(r["source"] for r in rows)
    rows_html = "".join(
        f'<div class="pulse-row"><span>{name}</span><span class="pulse-value">{n}</span></div>'
        for name, n in counter.most_common(limit)
    )

    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">📰 Top Sources</div>
        {rows_html}
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# 6. TOP NAVIGATION
# ---------------------------------------------------------

if PRAGATI_PHOTO_B64 and not PRAGATI_PHOTO_B64.startswith("PASTE_"):
    avatar_html = (
        f'<img src="data:image/jpeg;base64,{PRAGATI_PHOTO_B64}" '
        f'class="avatar-photo" alt="{PRAGATI_NAME}" />'
    )
else:
    avatar_html = f'<div class="avatar-circle-lg">{PRAGATI_NAME[:1].upper()}</div>'

# Emblem: an audit lens (magnifier) whose glass contains a rising analytics
# bar chart, framed by a scanning arc — "examine + measure + monitor".
LOGO_SVG = """
<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M26.6 8.4a13 13 0 0 1 .9 13.4" stroke="#FFFFFF" stroke-opacity="0.42"
        stroke-width="2" stroke-linecap="round"/>
  <path d="M5.2 22.6a13 13 0 0 1 .5-13.9" stroke="#FFFFFF" stroke-opacity="0.42"
        stroke-width="2" stroke-linecap="round"/>
  <circle cx="14.6" cy="14.6" r="8.2" stroke="#FFFFFF" stroke-width="2.4"/>
  <circle cx="14.6" cy="14.6" r="8.2" fill="#FFFFFF" fill-opacity="0.14"/>
  <rect x="10.7" y="15.1" width="2.25" height="4.5" rx="1.12" fill="#FFFFFF"/>
  <rect x="13.9" y="12.2" width="2.25" height="7.4" rx="1.12" fill="#FFFFFF"/>
  <rect x="17.1" y="9.6"  width="2.25" height="10"  rx="1.12" fill="#FFFFFF"/>
  <path d="M20.9 20.9 L26.4 26.4" stroke="#FFFFFF" stroke-width="3.1"
        stroke-linecap="round"/>
</svg>
"""

st.markdown(f"""
<div class="topnav">
    <div class="topnav-left">
        <div class="logo-icon">{LOGO_SVG}</div>
        <div class="logo-lockup">
            <div class="logo-textrow">
                <div class="logo-text">Audit<span class="lt-accent">&nbsp;Intelligence</span></div>
                <span class="live-pill"><span class="live-dot"></span>Live</span>
            </div>
            <div class="logo-sub"><span class="logo-rule"></span>Global Banking Risk &amp; Controls Briefing</div>
        </div>
    </div>
    <div class="topnav-user">
        <div class="topnav-user-meta">
            <div class="topnav-user-label">Prepared for</div>
            <div class="topnav-user-name">{PRAGATI_NAME}</div>
            <div class="topnav-user-title">{PRAGATI_TITLE}</div>
            <div class="topnav-user-stamp">{ist_now_str()}</div>
        </div>
        {avatar_html}
    </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 7. ACTION BAR — one button refreshes BOTH news and markets
# ---------------------------------------------------------

api_keys = get_api_keys()

act_l, act_r = st.columns([1, 4])

with act_l:
    hard_refresh = st.button("⟲  Refresh All Data", use_container_width=True, key="refresh_all")

with act_r:
    last_run = st.session_state.get("last_refresh", "not yet loaded this session")
    active_now = [npv.PROVIDERS[p]["label"] for p, k in api_keys.items() if k]
    src_txt = ", ".join(active_now) if active_now else "no provider keys yet"
    st.markdown(
        f'<div class="action-caption">{src_txt} · last pulled: {last_run}</div>',
        unsafe_allow_html=True,
    )

if hard_refresh:
    load_news.clear()
    load_market_snapshot.clear()
    st.session_state.pop("news_loaded", None)


# ---------------------------------------------------------
# 8. DATA CONTROLS
# ---------------------------------------------------------

with st.expander("⚙️  Data Sources, Filters & Controls", expanded=(not any(api_keys.values()))):

    st.markdown(
        '<div style="font-size:12.5px;font-weight:700;color:#0B1220;margin-bottom:2px;">'
        'News provider keys'
        '</div>'
        '<div style="font-size:11.5px;color:#6B7280;margin-bottom:8px;">'
        'The two primary services run together on every refresh. '
        'The reserve service stays idle and only engages if both primaries hit their limits.'
        '</div>',
        unsafe_allow_html=True,
    )

    for pid in list(npv.PRIMARY_PROVIDERS) + list(npv.RESERVE_PROVIDERS):
        meta = npv.PROVIDERS[pid]
        role = "Primary" if meta["tier"] == 1 else "Reserve (standby)"
        label = f'{meta["label"]} · {role}'

        if api_keys[pid]:
            st.text_input(
                label, value="•" * 16, disabled=True,
                key=f"key_display_{pid}",
                help="Loaded from config.py / environment / secrets.",
            )
        else:
            api_keys[pid] = st.text_input(
                label,
                type="password",
                placeholder="Paste key (optional)...",
                key=f"key_input_{pid}",
                help=f"Free key: {meta['signup']}",
            )

    st.divider()

    ctrl_a, ctrl_b, ctrl_c = st.columns(3)

    with ctrl_a:
        lookback_days = st.slider("Lookback Window (Days)", min_value=1, max_value=30, value=7)

    with ctrl_b:
        min_relevance = st.slider(
            "Minimum Audit Relevance",
            min_value=0, max_value=40, value=5, step=5,
            help="Lower this to widen the feed; raise it to keep only high-signal stories.",
        )

    with ctrl_c:
        dedup_mode = st.select_slider(
            "Duplicate Removal",
            options=["Loose", "Balanced", "Aggressive"],
            value="Balanced",
            help=(
                "Loose keeps near-identical rewrites as separate stories. "
                "Aggressive merges reworded headlines about the same event."
            ),
        )
    fuzzy_threshold = {"Loose": 0.85, "Balanced": 0.72, "Aggressive": 0.58}[dedup_mode]

    selected_categories = st.multiselect(
        "Active Categories",
        options=list(CATEGORIES.keys()),
        default=list(CATEGORIES.keys()),
        format_func=lambda c: CATEGORY_DISPLAY.get(c, c),
    )

if not any(api_keys.values()):
    st.info(
        "💡 Add at least one provider key above to load the briefing. "
        "Supplying all three (NewsAPI.org, APITube.io, NewsData.io) gives the widest coverage."
    )
    st.stop()


# ---------------------------------------------------------
# 9. DATA INGESTION & FILTERING
# ---------------------------------------------------------

active_keys = tuple(sorted((p, k) for p, k in api_keys.items() if k))
params_key = (lookback_days, min_relevance, fuzzy_threshold,
              tuple(sorted(selected_categories)), active_keys)

if ("news_loaded" not in st.session_state) or (st.session_state.get("params_key") != params_key):
    with st.spinner("Compiling the audit intelligence briefing..."):
        articles, errors, stats = load_news(
            tuple(sorted(api_keys.items())),
            lookback_days,
            min_relevance,
            fuzzy_threshold,
            tuple(sorted(selected_categories)),
        )

    st.session_state.news = articles
    st.session_state.news_errors = errors
    st.session_state.news_stats = stats
    st.session_state.news_loaded = True
    st.session_state.params_key = params_key
    st.session_state.last_refresh = ist_now_str()

articles = st.session_state.get("news", [])
errors = st.session_state.get("news_errors", [])
stats = st.session_state.get("news_stats", {})

filtered = [a for a in articles if a["category"] in selected_categories] if selected_categories else []

with st.expander("🔎 Ingestion Diagnostics", expanded=False):
    if stats:
        pp = stats.get("per_provider", {})
        exhausted = set(stats.get("exhausted", []))
        rows = ""

        for pid, meta in npv.PROVIDERS.items():
            role = "primary" if meta["tier"] == 1 else "reserve"
            s = pp.get(pid, {})

            if not api_keys.get(pid):
                state, color = "not configured", "#9CA3AF"
            elif pid in exhausted:
                state, color = "quota reached", "#DC2626"
            elif s.get("used"):
                state, color = "active", "#16A34A"
            else:
                state, color = "idle (standby)", "#6B7280"

            rows += (
                f'<tr>'
                f'<td style="padding:5px 14px 5px 0;font-weight:600;">{meta["label"]}</td>'
                f'<td style="padding:5px 14px 5px 0;color:#6B7280;">{role}</td>'
                f'<td style="padding:5px 14px 5px 0;">{s.get("requests",0)} req</td>'
                f'<td style="padding:5px 14px 5px 0;">{s.get("articles",0)} articles</td>'
                f'<td style="color:{color};font-weight:600;">{state}</td>'
                f'</tr>'
            )

        d = stats.get("dedup", {})
        st.markdown(
            f"""
            <table style="font-size:12.5px;color:#111827;border-collapse:collapse;margin-bottom:10px;">
            {rows}
            </table>
            <div style="font-size:12.5px; color:#111827; line-height:1.9;">
            <b>{stats.get('raw',0)}</b> raw articles ·
            removed <b>{d.get('by_url',0)}</b> same-link, <b>{d.get('by_title',0)}</b> same-headline,
            <b>{d.get('by_fuzzy',0)}</b> near-duplicate ·
            <b>{stats.get('unique',0)}</b> unique stories ·
            <b>{stats.get('dropped_low_relevance',0)}</b> below relevance floor ·
            <b>{stats.get('kept',0)}</b> retained
            </div>
            """,
            unsafe_allow_html=True,
        )

        if stats.get("failover"):
            st.warning(
                "Primary providers hit their limits this run — the reserve "
                "provider supplied the briefing. Primaries resume automatically "
                "once their quota resets.",
                icon="⚠️",
            )

    for err in errors:
        st.markdown(f"<div style='font-size:12px; color:#B45309;'>• {err}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------
# 10. PAGE TITLE
# ---------------------------------------------------------

st.markdown('<div class="page-title">This week\'s briefing</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="page-subtitle">{len(filtered)} items &nbsp;·&nbsp; verified banking internal controls &amp; regulatory surveillance</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 11. RENDER HELPERS
# ---------------------------------------------------------

def render_featured(article):
    color = CATEGORY_COLORS.get(article["category"], "#374151")
    label = CATEGORY_DISPLAY.get(article["category"], article["category"])
    rel_time = format_relative_time(article["publishedAt"])

    if article["image_url"]:
        bg = f'linear-gradient(180deg, rgba(17,24,39,0) 35%, rgba(17,24,39,0.88) 100%), url(\'{article["image_url"]}\')'
    else:
        bg = 'linear-gradient(135deg, #1E3A8A, #2563EB)'

    st.markdown(f"""
    <div class="featured-hero" style="background-image: {bg};">
        <div class="featured-badge" style="background: {color};">{label}</div>
        <div class="featured-text">
            <div class="featured-title">{article['title']}</div>
            <div class="featured-meta">By {article['source']} &nbsp;·&nbsp; {rel_time}</div>
        </div>
        <a href="{article['url']}" target="_blank" class="featured-link-overlay"></a>
    </div>
    """, unsafe_allow_html=True)


def render_insight_card(article):
    color = CATEGORY_COLORS.get(article["category"], "#374151")
    label = CATEGORY_DISPLAY.get(article["category"], article["category"])
    rel_time = format_relative_time(article["publishedAt"])
    description_text = article["description"] or "Independent institutional briefing coverage. Select below to review the full verified source documentation."

    # Category-tinted newspaper placeholder, painted as the <img>'s own background.
    # If the remote image is missing, dead, or hotlink-blocked (403), the browser
    # discards the src and this placeholder remains visible — no more blank boxes.
    fallback = placeholder_data_uri(color)
    # An empty src="" makes some browsers re-request the page, so omit it entirely.
    src_attr = f'src="{article["image_url"]}" ' if article["image_url"] else ""

    thumb_html = (
        f'<img class="insight-thumb" {src_attr}alt="" loading="lazy" '
        f'referrerpolicy="no-referrer" '
        f'style="background-image: url(&quot;{fallback}&quot;);" '
        f'onerror="this.onerror=null; this.removeAttribute(\'src\');" />'
    )

    st.markdown(f"""
    <div class="insight-card">
        {thumb_html}
        <div class="insight-content">
            <div class="insight-meta-row">
                <span class="badge" style="background: {color};">{label}</span>
                <span class="insight-date">{rel_time}</span>
            </div>
            <a href="{article['url']}" target="_blank" class="insight-title-link">
                <div class="insight-title">{article['title']}</div>
            </a>
            <div class="insight-desc">{description_text}</div>
            <div class="insight-footer">
                <a href="{article['url']}" target="_blank" class="read-link">Read source ↗</a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_feed(rows, show_featured=True):
    if not rows:
        st.markdown("""
        <div class="empty-state-panel">
            <div style="font-size: 18px; font-weight: 700; color: #111827;">No briefing stories found</div>
            <div style="font-size: 13.5px; color: #4B5563; margin-top: 6px;">Try expanding the lookback window or lowering the relevance floor above.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    if show_featured:
        st.markdown('<div class="section-heading">Featured Analysis</div>', unsafe_allow_html=True)
        render_featured(rows[0])
        rest = rows[1:]
    else:
        rest = rows

    if rest:
        st.markdown('<div class="section-heading">Latest Insights</div>', unsafe_allow_html=True)
        for art in rest:
            render_insight_card(art)


# ---------------------------------------------------------
# 12. MAIN LAYOUT
# ---------------------------------------------------------

col_main, col_side = st.columns([2.3, 1], gap="large")

with col_main:
    if not filtered:
        render_feed(filtered)
    else:
        tab_labels = ["All Insights"] + [CATEGORY_DISPLAY.get(c, c) for c in selected_categories]
        tabs = st.tabs(tab_labels)

        with tabs[0]:
            render_feed(filtered, show_featured=True)

        for tab, category in zip(tabs[1:], selected_categories):
            with tab:
                cat_rows = [a for a in filtered if a["category"] == category]
                render_feed(cat_rows, show_featured=False)

with col_side:
    render_market_panel()
    render_priority_alerts(filtered)
    render_risk_radar(filtered)
    render_source_panel(filtered)

    active_categories = ", ".join(CATEGORY_DISPLAY.get(c, c) for c in selected_categories) or "None selected"
    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">⚙️ Active Filters</div>
        <div class="filter-row"><span>Categories</span><span class="filter-value">{active_categories}</span></div>
        <div class="filter-row"><span>Lookback</span><span class="filter-value">Last {lookback_days}d</span></div>
        <div class="filter-row"><span>Relevance floor</span><span class="filter-value">{min_relevance}</span></div>
    </div>
    """, unsafe_allow_html=True)

    if filtered:
        today_count = sum(1 for a in filtered if format_relative_time(a["publishedAt"]) == "Today")
        unique_sources = len(set(a["source"] for a in filtered))
    else:
        today_count, unique_sources = 0, 0

    st.markdown(f"""
    <div class="side-panel">
        <div class="side-panel-title">📊 Feed Pulse</div>
        <div class="pulse-row"><span>Total Stories</span><span class="pulse-value">{len(filtered)}</span></div>
        <div class="pulse-row"><span>Published Today</span><span class="pulse-value">{today_count}</span></div>
        <div class="pulse-row"><span>Unique Sources</span><span class="pulse-value">{unique_sources}</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cta-panel">
        <div class="cta-title">Audit Intelligence Brief</div>
        <div class="cta-desc">Export this briefing as a CSV for Audit Committee and Chief Risk Officer distribution.</div>
    </div>
    """, unsafe_allow_html=True)
    if filtered:
        df_export = pd.DataFrame(filtered)
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Briefing CSV",
            data=csv,
            file_name=f"audit_intel_briefing_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_csv_sidebar",
        )


# ---------------------------------------------------------
# 13. FOOTER
# ---------------------------------------------------------

st.markdown("""
<div class="app-footer">
    <div>
        <div class="footer-brand"><span>📡</span> Audit Intelligence</div>
        <div class="footer-tagline">Curated intelligence feed for Audit Committees and Chief Risk Officers across banking and financial services.</div>
    </div>
    <div class="footer-links">
        <span>About Us</span>
        <span>Contact</span>
        <span>Privacy Policy</span>
        <span>Terms of Service</span>
    </div>
</div>
<div class="footer-copyright">© 2026 Audit Intelligence &middot; Internal tool &middot; Not for external distribution</div>
""", unsafe_allow_html=True)
