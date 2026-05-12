# ui/styles.py — KSM Smart Freight — Enhanced dark theme
import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        /* ══════════════════════════════════════════════════════════════════════
           BACKGROUND — deep midnight with animated gradient mesh + truck image
           ══════════════════════════════════════════════════════════════════════ */
        .stApp {
            background:
                linear-gradient(125deg,
                    rgba(2,6,23,0.97)   0%,
                    rgba(7,18,55,0.95)  25%,
                    rgba(10,30,80,0.93) 50%,
                    rgba(5,20,50,0.95)  75%,
                    rgba(2,8,30,0.97)  100%),
                url('https://images.unsplash.com/photo-1519003722824-194d4455a60c?ixlib=rb-4.0.3&auto=format&fit=crop&w=2400&q=80');
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }

        /* Subtle animated gradient overlay for depth */
        .stApp::before {
            content: '';
            position: fixed;
            inset: 0;
            background:
                radial-gradient(ellipse 80% 50% at 20% 40%, rgba(37,99,235,0.07) 0%, transparent 60%),
                radial-gradient(ellipse 60% 40% at 80% 70%, rgba(5,150,105,0.06) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }

        /* ══════════════════════════════════════════════════════════════════════
           MAIN CONTENT CONTAINER
           ══════════════════════════════════════════════════════════════════════ */
        .main .block-container {
            background: rgba(7,15,40,0.55);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border-radius: 20px;
            border: 1px solid rgba(96,165,250,0.12);
            padding: 2rem 2.5rem;
            box-shadow:
                0 0 0 1px rgba(96,165,250,0.06),
                0 24px 48px rgba(0,0,0,0.5),
                inset 0 1px 0 rgba(255,255,255,0.04);
        }

        /* ══════════════════════════════════════════════════════════════════════
           TYPOGRAPHY
           ══════════════════════════════════════════════════════════════════════ */
        .stApp, .stApp p, .stApp label, .stApp div, .stApp span {
            color: #cbd5e1 !important;
        }
        h1 { color: #60a5fa !important; font-weight: 800 !important;
             letter-spacing: -0.5px !important; }
        h2 { color: #93c5fd !important; font-weight: 700 !important; }
        h3 { color: #bfdbfe !important; font-weight: 600 !important; }
        h4 { color: #dbeafe !important; }

        /* ══════════════════════════════════════════════════════════════════════
           SIDEBAR — glossy deep navy panel
           ══════════════════════════════════════════════════════════════════════ */
        [data-testid="stSidebar"] {
            background:
                linear-gradient(180deg,
                    rgba(2,6,23,0.98)  0%,
                    rgba(10,22,65,0.97) 40%,
                    rgba(7,15,45,0.98) 100%) !important;
            border-right: 1px solid rgba(96,165,250,0.15);
            box-shadow: 4px 0 24px rgba(0,0,0,0.4);
        }
        [data-testid="stSidebar"] * { color: #e0e7ff !important; }
        [data-testid="stSidebar"] .stSelectbox label { color: #93c5fd !important; }
        [data-testid="stSidebar"] hr {
            border-color: rgba(96,165,250,0.15) !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           METRIC CARDS
           ══════════════════════════════════════════════════════════════════════ */
        [data-testid="stMetric"] {
            background: linear-gradient(135deg,
                rgba(15,30,80,0.8) 0%,
                rgba(30,58,138,0.6) 100%);
            padding: 18px 20px;
            border-radius: 14px;
            border: 1px solid rgba(96,165,250,0.25);
            box-shadow:
                0 4px 20px rgba(0,0,0,0.4),
                0 0 0 1px rgba(96,165,250,0.08),
                inset 0 1px 0 rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 28px rgba(37,99,235,0.3);
        }
        [data-testid="stMetricLabel"]  { color: #93c5fd !important; font-weight: 600 !important; font-size: 12px !important; text-transform: uppercase; letter-spacing: 0.5px; }
        [data-testid="stMetricValue"]  { color: #ffffff !important; font-size: 1.6rem !important; font-weight: 800 !important; }
        [data-testid="stMetricDelta"]  { font-size: 13px !important; }

        /* ══════════════════════════════════════════════════════════════════════
           INPUTS — frosted glass style
           ══════════════════════════════════════════════════════════════════════ */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stTextArea > div > textarea,
        .stSelectbox > div > div,
        .stDateInput > div > div > input,
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea {
            background: rgba(7,15,40,0.7) !important;
            border: 1px solid rgba(96,165,250,0.3) !important;
            border-radius: 10px !important;
            color: #e2e8f0 !important;
            backdrop-filter: blur(8px);
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }
        .stTextInput > div > div > input:focus,
        .stNumberInput > div > div > input:focus,
        .stTextArea > div > textarea:focus {
            border-color: rgba(96,165,250,0.7) !important;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.15) !important;
        }
        .stSelectbox > div > div > div { color: #e2e8f0 !important; }
        label { color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important; }

        /* ══════════════════════════════════════════════════════════════════════
           BUTTONS
           ══════════════════════════════════════════════════════════════════════ */
        .stButton > button,
        .stFormSubmitButton > button {
            background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
            color: white !important;
            border: 1px solid rgba(96,165,250,0.35) !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            letter-spacing: 0.3px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 14px rgba(37,99,235,0.35);
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%) !important;
            box-shadow: 0 6px 22px rgba(59,130,246,0.5);
            transform: translateY(-1px);
        }
        button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background: linear-gradient(135deg, #047857 0%, #059669 50%, #10b981 100%) !important;
            box-shadow: 0 4px 16px rgba(16,185,129,0.4) !important;
            border-color: rgba(52,211,153,0.4) !important;
        }
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
            box-shadow: 0 6px 24px rgba(16,185,129,0.55) !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           TABS
           ══════════════════════════════════════════════════════════════════════ */
        .stTabs [data-baseweb="tab-list"] {
            background: rgba(7,15,40,0.7) !important;
            border-radius: 12px !important;
            padding: 4px !important;
            border: 1px solid rgba(96,165,250,0.15);
            gap: 4px;
        }
        .stTabs [data-baseweb="tab"] {
            color: #64748b !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease;
            padding: 8px 16px !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #93c5fd !important;
            background: rgba(37,99,235,0.15) !important;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%) !important;
            color: white !important;
            box-shadow: 0 2px 10px rgba(37,99,235,0.4);
        }

        /* ══════════════════════════════════════════════════════════════════════
           DATAFRAMES
           ══════════════════════════════════════════════════════════════════════ */
        .stDataFrame,
        [data-testid="stDataFrame"] {
            background: rgba(7,15,40,0.6) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(96,165,250,0.15) !important;
            overflow: hidden;
        }
        [data-testid="stDataFrame"] th {
            background: rgba(30,58,138,0.7) !important;
            color: #93c5fd !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           EXPANDERS
           ══════════════════════════════════════════════════════════════════════ */
        .streamlit-expanderHeader {
            background: rgba(15,30,80,0.5) !important;
            border-radius: 10px !important;
            border: 1px solid rgba(96,165,250,0.2) !important;
            color: #bfdbfe !important;
            transition: background 0.2s ease;
        }
        .streamlit-expanderHeader:hover {
            background: rgba(30,58,138,0.5) !important;
        }
        .streamlit-expanderContent {
            border: 1px solid rgba(96,165,250,0.12) !important;
            border-top: none !important;
            border-radius: 0 0 10px 10px !important;
            background: rgba(7,15,40,0.4) !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           ALERTS — themed to dark background
           ══════════════════════════════════════════════════════════════════════ */
        .stSuccess {
            background: rgba(6,78,59,0.55) !important;
            border-color: rgba(16,185,129,0.6) !important;
            color: #a7f3d0 !important;
            border-radius: 10px !important;
        }
        .stWarning {
            background: rgba(78,54,6,0.55) !important;
            border-color: rgba(245,158,11,0.6) !important;
            color: #fde68a !important;
            border-radius: 10px !important;
        }
        .stError {
            background: rgba(78,6,6,0.55) !important;
            border-color: rgba(220,38,38,0.6) !important;
            color: #fca5a5 !important;
            border-radius: 10px !important;
        }
        .stInfo {
            background: rgba(6,42,78,0.55) !important;
            border-color: rgba(59,130,246,0.5) !important;
            color: #bfdbfe !important;
            border-radius: 10px !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           DIVIDERS
           ══════════════════════════════════════════════════════════════════════ */
        hr {
            border: none !important;
            border-top: 1px solid rgba(96,165,250,0.15) !important;
            margin: 16px 0 !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           RISK / STATUS CARDS (custom classes used in the app)
           ══════════════════════════════════════════════════════════════════════ */
        .health-card {
            background: linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%);
            padding: 20px; border-radius: 16px; color: white; margin: 10px 0;
            box-shadow: 0 8px 28px rgba(124,58,237,0.3);
        }
        .risk-high {
            background: rgba(127,29,29,0.5);
            border-left: 4px solid #ef4444;
            padding: 12px 16px; border-radius: 10px;
        }
        .risk-medium {
            background: rgba(78,54,6,0.5);
            border-left: 4px solid #f59e0b;
            padding: 12px 16px; border-radius: 10px;
        }
        .risk-low {
            background: rgba(6,50,36,0.5);
            border-left: 4px solid #10b981;
            padding: 12px 16px; border-radius: 10px;
        }

        /* ══════════════════════════════════════════════════════════════════════
           PLOTLY CHARTS — keep transparent
           ══════════════════════════════════════════════════════════════════════ */
        .js-plotly-plot .plotly,
        .plot-container {
            background: transparent !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           SCROLLBAR — thin accent
           ══════════════════════════════════════════════════════════════════════ */
        ::-webkit-scrollbar       { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: rgba(7,15,40,0.4); }
        ::-webkit-scrollbar-thumb {
            background: rgba(96,165,250,0.35);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(96,165,250,0.6);
        }

        /* ══════════════════════════════════════════════════════════════════════
           COMMAND BAR — glass panel
           ══════════════════════════════════════════════════════════════════════ */
        .cmd-bar-wrap {
            background: rgba(7,15,40,0.65);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(96,165,250,0.18);
            border-radius: 16px;
            padding: 16px 20px;
            margin-bottom: 8px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.35);
        }

        /* ══════════════════════════════════════════════════════════════════════
           SPINNER
           ══════════════════════════════════════════════════════════════════════ */
        .stSpinner > div { border-top-color: #3b82f6 !important; }

        /* ══════════════════════════════════════════════════════════════════════
           SLIDER
           ══════════════════════════════════════════════════════════════════════ */
        [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
            background: #3b82f6 !important;
            border-color: #60a5fa !important;
        }

        /* ══════════════════════════════════════════════════════════════════════
           CAPTION / SMALL TEXT
           ══════════════════════════════════════════════════════════════════════ */
        .stCaption, small { color: #64748b !important; font-size: 12px !important; }

        /* ══════════════════════════════════════════════════════════════════════
           RADIO / CHECKBOX
           ══════════════════════════════════════════════════════════════════════ */
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label { color: #cbd5e1 !important; }

        </style>
        """,
        unsafe_allow_html=True,
    )
