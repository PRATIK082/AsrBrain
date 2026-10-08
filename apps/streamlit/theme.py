"""AsrBrain cockpit theme — automotive obsidian design system for Streamlit.

Reference: clean AI-chat layout (left rail, centered hero + suggestion cards,
docked composer, right context panel), elevated to an automotive grade:
deep-obsidian surfaces, cyan streaming accents, safety-green verified states,
amber slot-filling chips, Inter-like UI type + JetBrains-Mono evidence type.
"""
from __future__ import annotations

import streamlit as st

BG = "#070A0F"
PANEL = "#121824"
PANEL_2 = "#0D1320"
BORDER = "#222D3F"
INK = "#F1F5F9"
CYAN = "#00F5FF"
GREEN = "#10B981"
AMBER = "#F59E0B"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ---------- app frame ---------- */
.stApp {{ background: {BG}; color: {INK}; font-family: Inter, 'SF Pro Text', system-ui, sans-serif; }}
section[data-testid="stSidebar"] {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label {{ color: {INK} !important; }}
section[data-testid="stMain"] {{ background: {BG}; }}
.block-container {{ max-width: 1060px; padding-top: 1.2rem; }}

/* ---------- brand ---------- */
.asr-brand {{ display: flex; align-items: center; gap: 10px; padding: 6px 2px 12px; }}
.asr-logo {{
  width: 34px; height: 34px; border-radius: 10px; flex: 0 0 34px;
  background: linear-gradient(135deg, {CYAN}, #2563EB);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; color: #04121a; font-size: 18px;
  box-shadow: 0 0 18px rgba(0,245,255,.35);
}}
.asr-name {{ font-weight: 800; font-size: 17px; letter-spacing: .2px; }}
.asr-sub {{ font-size: 11px; color: {INK}; opacity: .55; font-family: 'JetBrains Mono', monospace; }}

/* ---------- hero ---------- */
.asr-hero {{ text-align: center; padding: 26px 10px 6px; }}
.asr-hero h1 {{ font-size: 40px; font-weight: 800; letter-spacing: -.5px; margin: 0; }}
.asr-hero h1 span {{ background: linear-gradient(90deg, {CYAN}, #7DD3FC); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.asr-hero p {{ opacity: .6; font-size: 14px; margin-top: 8px; }}
.asr-chips {{ display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 10px; }}
.asr-chip {{
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {AMBER};
  border: 1px solid rgba(245,158,11,.4); background: rgba(245,158,11,.08);
  padding: 3px 10px; border-radius: 999px;
}}

/* ---------- suggestion cards ---------- */
.asr-cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 18px auto 0; max-width: 640px; }}
.asr-card {{
  border: 1px solid {BORDER}; background: {PANEL}; border-radius: 14px;
  padding: 13px 14px; text-align: left; transition: border-color .2s, transform .2s;
}}
.asr-card b {{ font-size: 13.5px; }}
.asr-card small {{ display: block; opacity: .55; font-size: 11.5px; margin-top: 3px; }}
.asr-ico {{
  width: 30px; height: 30px; border-radius: 9px; display: inline-flex;
  align-items: center; justify-content: center; font-size: 15px; margin-bottom: 8px;
}}

/* ---------- chat bubbles ---------- */
.stChatMessage {{ background: transparent !important; }}
.stChatMessage[data-testid="stChatMessage"] {{
  border: 1px solid {BORDER}; background: {PANEL} !important; border-radius: 14px;
  padding: 10px 14px; margin-bottom: 10px;
}}
.stChatMessage[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
  background: {PANEL_2} !important; border-color: rgba(0,245,255,.25);
}}
.stChatMessage p, .stChatMessage li {{ color: {INK}; font-size: 14px; }}
.stChatMessage code {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; }}
.stChatMessage pre {{ background: #04070c !important; border: 1px solid {BORDER}; border-radius: 10px; }}

/* ---------- composer ---------- */
.stChatInput {{ position: sticky; bottom: 0; }}
.stChatInput > div {{ background: {PANEL} !important; border: 1px solid {BORDER} !important; border-radius: 16px !important; }}
.stChatInput textarea {{ color: {INK} !important; }}
.stChatInput button {{ background: {CYAN} !important; color: #04121a !important; border-radius: 10px !important; }}

/* ---------- controls ---------- */
.stButton > button {{
  background: {PANEL_2}; color: {INK}; border: 1px solid {BORDER}; border-radius: 10px;
  font-weight: 600; font-size: 13px; transition: border-color .2s;
}}
.stButton > button:hover {{ border-color: {CYAN}; color: {INK}; }}
.stButton > button[kind="primary"] {{ background: {CYAN} !important; color: #04121a !important; border: none; }}
.stTextInput > div > div > input, .stSelectbox > div > div, .stTextArea textarea {{
  background: {PANEL_2} !important; color: {INK} !important; border: 1px solid {BORDER} !important; border-radius: 10px !important;
}}
.stExpander {{ border: 1px solid {BORDER} !important; border-radius: 12px !important; background: {PANEL} !important; }}
.stExpander summary {{ color: {INK} !important; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{ color: {INK}; opacity: .6; }}
.stTabs [aria-selected="true"] {{ opacity: 1 !important; color: {CYAN} !important; }}
.stStatusWidget {{ background: {PANEL} !important; border: 1px solid {BORDER}; border-radius: 12px; }}
code, .stMarkdown code {{ font-family: 'JetBrains Mono', monospace !important; }}
.asr-foot {{ text-align: center; font-size: 11px; opacity: .4; padding: 14px 0 4px; }}
.asr-verdict-ok {{ color: {GREEN}; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
.asr-verdict-warn {{ color: {AMBER}; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
@media (max-width: 640px) {{ .asr-cards {{ grid-template-columns: 1fr; }} .asr-hero h1 {{ font-size: 30px; }} }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand() -> None:
    st.markdown(
        '<div class="asr-brand"><div class="asr-logo">A</div>'
        '<div><div class="asr-name">AsrBrain</div>'
        '<div class="asr-sub">AUTOSAR COPILOT · v2</div></div></div>',
        unsafe_allow_html=True,
    )


def hero(scope: str, files: int) -> None:
    st.markdown(
        '<div class="asr-hero"><h1>AUTOSAR Copilot, <span>engineered.</span></h1>'
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
            if st.button(f"{title}", key=f"quick_{i}", use_container_width=True,
                         help=prompt):
                return prompt
    st.caption(" · ".join(f"{icon} {t}" for icon, t, _ in QUICK))
    return None
