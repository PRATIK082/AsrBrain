"""AsrBrain cockpit theme — token-driven light/dark design system for Streamlit.

Two palettes (obsidian dark default, clean-room light), one inject(mode) entry.
Also fixes Streamlit native chrome (header/toolbar) which otherwise flashes white.
"""
from __future__ import annotations

import streamlit as st

DARK = dict(
    bg="#06090E", panel="#101724", panel2="#0B111C", border="#223047",
    ink="#EDF2F7", muted="rgba(237,242,247,.55)", accent="#00E5FF",
    accent_ink="#04121a", green="#34D399", amber="#FBBF24",
    input_bg="#0B111C", shadow="0 0 22px rgba(0,229,255,.28)",
    user_bg="#0B111C", user_border="rgba(0,229,255,.30)",
)

LIGHT = dict(
    bg="#F4F6FA", panel="#FFFFFF", panel2="#EAF0F7", border="#D5DFEA",
    ink="#0F1B2D", muted="rgba(15,27,45,.55)", accent="#0284C7",
    accent_ink="#FFFFFF", green="#059669", amber="#B45309",
    input_bg="#FFFFFF", shadow="0 6px 24px rgba(2,132,199,.18)",
    user_bg="#EAF3FA", user_border="rgba(2,132,199,.35)",
)


def _css(t: dict) -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ---------- native chrome (kills the white strip) ---------- */
header[data-testid="stHeader"] {{ background: transparent !important; }}
header[data-testid="stHeader"] button {{ color: {t['ink']} !important; }}
div[data-testid="stToolbar"] {{ color: {t['ink']} !important; }}
div[data-testid="stDecoration"] {{
  background: linear-gradient(90deg, {t['accent']}, transparent 70%) !important;
  height: 2px !important;
}}
.stAppViewContainer {{ background: {t['bg']} !important; }}

/* ---------- app frame ---------- */
.stApp {{ background: {t['bg']}; color: {t['ink']}; font-family: Inter, 'SF Pro Text', system-ui, sans-serif; }}
section[data-testid="stSidebar"] {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span {{ color: {t['ink']} !important; }}
section[data-testid="stMain"] {{ background: {t['bg']}; }}
.block-container {{ max-width: 1220px; padding-top: 0.6rem; }}

/* ---------- brand ---------- */
.asr-brand {{ display: flex; align-items: center; gap: 10px; padding: 4px 2px 10px; }}
.asr-name {{ font-weight: 800; font-size: 17px; letter-spacing: .2px; color: {t['ink']}; }}
.asr-sub {{ font-size: 10.5px; color: {t['muted']}; font-family: 'JetBrains Mono', monospace; letter-spacing: 1px; }}
.asr-appear {{ display: flex; gap: 6px; margin: 2px 0 8px; }}

/* ---------- hero ---------- */
.asr-hero {{ text-align: center; padding: 22px 10px 4px; }}
.asr-hero h1 {{ font-size: 40px; font-weight: 800; letter-spacing: -.5px; margin: 0; color: {t['ink']}; }}
.asr-hero h1 span {{ background: linear-gradient(90deg, {t['accent']}, #7DD3FC); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.asr-hero p {{ color: {t['muted']}; font-size: 14px; margin-top: 8px; }}
.asr-chips {{ display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 10px; }}
.asr-chip {{
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {t['amber']};
  border: 1px solid {t['border']}; background: {t['panel']};
  padding: 3px 10px; border-radius: 999px;
}}

/* ---------- pill tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{
  background: {t['panel']}; border: 1px solid {t['border']};
  border-radius: 999px; padding: 4px; gap: 2px; flex-wrap: wrap;
}}
.stTabs [data-baseweb="tab"] {{
  color: {t['ink']}; opacity: .55; border-radius: 999px !important;
  padding: 7px 15px !important; font-weight: 600; font-size: 13px; border: none !important;
}}
.stTabs [data-baseweb="tab"]:hover {{ opacity: .9; }}
.stTabs [aria-selected="true"] {{
  opacity: 1 !important; background: {t['accent']} !important; color: {t['accent_ink']} !important;
  box-shadow: {t['shadow']};
}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

/* ---------- chat blocks ---------- */
.asr-role {{
  font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 600;
  letter-spacing: 1.5px; color: {t['muted']}; margin-bottom: 6px;
}}
.stChatMessage {{ background: transparent !important; }}
.stChatMessage[data-testid="stChatMessage"] {{
  border: 1px solid {t['border']}; background: {t['panel']} !important;
  border-radius: 16px; padding: 12px 16px; margin-bottom: 12px;
  box-shadow: 0 2px 14px rgba(0,0,0,.18);
}}
.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
  background: {t['user_bg']} !important; border-color: {t['user_border']};
}}
.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
  border-left: 3px solid {t['accent']};
}}
.stChatMessage p, .stChatMessage li {{ color: {t['ink']}; font-size: 14px; }}
.stChatMessage code {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; }}
.stChatMessage pre {{ background: {t['panel2']} !important; border: 1px solid {t['border']}; border-radius: 10px; }}

/* ---------- composer dock ---------- */
.stChatInput > div {{
  background: {t['panel']} !important; border: 1.5px solid {t['border']} !important;
  border-radius: 18px !important; box-shadow: 0 4px 20px rgba(0,0,0,.25);
}}
.stChatInput > div:focus-within {{ border-color: {t['accent']} !important; }}
.stChatInput textarea {{ color: {t['ink']} !important; }}
.stChatInput button {{
  background: {t['accent']} !important; color: {t['accent_ink']} !important;
  border-radius: 12px !important; box-shadow: {t['shadow']};
}}

/* ---------- controls ---------- */
.stButton > button {{
  background: {t['panel2']}; color: {t['ink']}; border: 1px solid {t['border']};
  border-radius: 10px; font-weight: 600; font-size: 13px;
}}
.stButton > button:hover {{ border-color: {t['accent']}; color: {t['ink']}; }}
.stButton > button[kind="primary"] {{ background: {t['accent']} !important; color: {t['accent_ink']} !important; border: none; }}
.stTextInput > div > div > input, .stSelectbox > div > div, .stTextArea textarea,
.stNumberInput > div > div > input {{
  background: {t['input_bg']} !important; color: {t['ink']} !important;
  border: 1px solid {t['border']} !important; border-radius: 10px !important;
}}
.stRadio label, .stCheckbox label {{ color: {t['ink']} !important; }}
.stExpander {{ border: 1px solid {t['border']} !important; border-radius: 12px !important; background: {t['panel']} !important; }}
.stExpander summary {{ color: {t['ink']} !important; }}
.stStatusWidget {{ background: {t['panel']} !important; border: 1px solid {t['border']}; border-radius: 12px; }}
code, .stMarkdown code {{ font-family: 'JetBrains Mono', monospace !important; }}
.asr-foot {{ text-align: center; font-size: 11px; color: {t['muted']}; padding: 14px 0 4px; }}
.asr-ok {{ color: {t['green']}; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
.asr-warn {{ color: {t['amber']}; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
/* ---------- large data: tables / code / media fit any width ---------- */
.stMarkdown table, .stChatMessage table {{
  display: block; width: max-content; max-width: 100%;
  overflow-x: auto; border-collapse: collapse;
  font-size: 12.5px; margin: 10px 0; border-radius: 10px;
}}
.stMarkdown th, .stMarkdown td, .stChatMessage th, .stChatMessage td {{
  padding: 7px 10px; border: 1px solid {t['border']}; text-align: left;
  vertical-align: top; overflow-wrap: anywhere; word-break: break-word;
  min-width: 80px;
}}
.stMarkdown th, .stChatMessage th {{
  background: {t['panel2']}; font-weight: 700; white-space: nowrap;
}}
.stMarkdown td code, .stChatMessage td code {{
  overflow-wrap: anywhere; word-break: break-all; white-space: normal;
}}
.stChatMessage pre {{ max-width: 100%; overflow-x: auto; }}
.stChatMessage img, .stMarkdown img {{ max-width: 100%; height: auto; border-radius: 10px; }}
.stChatMessage p, .stChatMessage li, .stMarkdown p {{ overflow-wrap: anywhere; }}
.stChatMessage .stMarkdown, section[data-testid="stMain"] .stMarkdown {{ min-width: 0; }}
@media (max-width: 900px) {{
  .block-container {{ max-width: 100%; padding-left: .8rem; padding-right: .8rem; }}
  .stMarkdown table, .stChatMessage table {{ font-size: 11.5px; }}
  .asr-hero h1 {{ font-size: 30px; }}
}}
@media (max-width: 640px) {{ .asr-cards {{ grid-template-columns: 1fr; }} .asr-hero h1 {{ font-size: 30px; }} }}
.asr-cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 18px auto 0; max-width: 640px; }}
</style>
"""


def inject(mode: str = "dark") -> None:
    st.markdown(_css(DARK if mode != "light" else LIGHT), unsafe_allow_html=True)


_LOGO_SVG = """<svg width="36" height="36" viewBox="0 0 36 36" fill="none">
<defs><linearGradient id="asg" x1="0" y1="0" x2="36" y2="36">
<stop offset="0" stop-color="#00E5FF"/><stop offset="1" stop-color="#2563EB"/>
</linearGradient></defs>
<rect x="1.5" y="1.5" width="33" height="33" rx="9" fill="url(#asg)"/>
<rect x="1.5" y="1.5" width="33" height="33" rx="9" stroke="rgba(255,255,255,.35)"/>
<path d="M18 8 L26 26 H23 L18 12.4 L13 26 H10 Z" fill="#04121A"/>
<circle cx="18" cy="24.6" r="0" fill="#04121A"/>
<circle cx="12.5" cy="10.5" r="1.3" fill="#04121A" opacity=".65"/>
<circle cx="23.5" cy="10.5" r="1.3" fill="#04121A" opacity=".65"/>
<path d="M12.5 11.8 V15 M23.5 11.8 V15" stroke="#04121A" stroke-width="1.1" opacity=".65"/>
</svg>"""


def brand() -> None:
    st.markdown(
        f'<div class="asr-brand">{_LOGO_SVG}'
        '<div><div class="asr-name">AsrBrain</div>'
        '<div class="asr-sub">AUTOMOTIVE INTELLIGENCE · V2</div></div></div>',
        unsafe_allow_html=True,
    )


def hero(scope: str, files: int) -> None:
    st.markdown(
        '<div class="asr-hero"><h1>AsrBrain, <span>engineered.</span></h1>'
        '<p>Ask about specs, ARXML topologies, code and migrations — every claim cited.</p>'
        f'<div class="asr-chips"><span class="asr-chip">SCOPE · {scope}</span>'
        f'<span class="asr-chip">PROJECT FILES · {files}</span>'
        '<span class="asr-chip">ABSTAIN &gt; HALLUCINATE</span></div></div>',
        unsafe_allow_html=True,
    )


QUICK = [
    ("🔌", "Explain a software component", "Explain the ports, interfaces and runnables of SWC BrakeCtrl from my ARXML"),
    ("⚖️", "Compare two releases", "Compare CanIf between 4.3.1 and 4.4.0 in a side-by-side table"),
    ("🧩", "Draft an RTE skeleton", "Draft a C/H RTE skeleton for my ARXML component with traceability"),
    ("🩺", "Troubleshoot a fault", "Walk me through a UDS DTC diagnostic sequence for a CAN timeout"),
]


def quick_cards() -> str | None:
    """Render 2x2 suggestion cards. Returns the chosen prompt, if any."""
    cols = st.columns(2)
    for i, (icon, title, prompt) in enumerate(QUICK):
        with cols[i % 2]:
            if st.button(f"{icon}  {title}", key=f"quick_{i}", use_container_width=True,
                         help=prompt):
                return prompt
    return None


def role_ribbon(role: str, meta: dict | None = None) -> None:
    """Role label ribbon at the top of a chat block."""
    meta = meta or {}
    if role == "user":
        st.markdown('<div class="asr-role">◆ YOU</div>', unsafe_allow_html=True)
    else:
        model = (meta.get("llm") or "").strip()
        tag = f" · {model}" if model else ""
        st.markdown(f'<div class="asr-role">⬢ ASRBRAIN{tag}</div>', unsafe_allow_html=True)
