"""Motyw „warm glass” (referencja: ciepłe tło, rozmyte kule/pierścienie, szklane panele).

Styl jest w całości lokalny: gradienty i kształty rysuje CSS, bez obrazów i bez sieci.
`inject()` wołamy na starcie każdego przebiegu skryptu; zmiana motywu wymaga tylko rerunu.
Kolory bazowe dla widżetów (tabele, inputy) ustawia `.streamlit/config.toml` — ten plik
wymaga restartu serwera, więc po samej zmianie CSS wystarczy odświeżyć stronę.
"""

# ruff: noqa: E501 - długie linie CSS w bloku tekstowym; to nie kod Pythona.
from __future__ import annotations

import streamlit as st

# Paleta z referencji: wyciszone różowo-beżowe tło, jasne pomarańczowe kule i koralowe
# pierścienie, szkło ledwie widoczne; atrament w brązach dla czytelności tabel i formularzy.
INK = "#2f170d"
INK_SOFT = "rgba(47, 23, 13, 0.64)"
GLASS = "rgba(255, 244, 236, 0.24)"
GLASS_STRONG = "rgba(255, 246, 238, 0.4)"
LINE = "rgba(255, 255, 255, 0.55)"
ACCENT = "#f2601d"
ACCENT_2 = "#ff9a5c"

DECOR = """
<div class="vt-decor" aria-hidden="true">
  <span class="vt-orb vt-orb-a"></span>
  <span class="vt-orb vt-orb-b"></span>
  <span class="vt-orb vt-orb-c"></span>
  <span class="vt-ring vt-ring-a"></span>
  <span class="vt-ring vt-ring-b"></span>
</div>
"""

CSS = f"""
<style>
:root {{
  --vt-ink: {INK};
  --vt-ink-soft: {INK_SOFT};
  --vt-glass: {GLASS};
  --vt-glass-strong: {GLASS_STRONG};
  --vt-line: {LINE};
  --vt-accent: {ACCENT};
  --vt-accent-2: {ACCENT_2};
  --vt-radius: 26px;
}}

/* --- tło: wyciszony różowo-beżowy gradient + kule i pierścienie jak w referencji --- */
[data-testid="stAppViewContainer"], .stApp {{
  background:
    radial-gradient(1000px 700px at 8% 2%, rgba(255, 246, 238, 0.55), transparent 60%),
    radial-gradient(840px 840px at 92% 6%, rgba(255, 138, 74, 0.8), transparent 62%),
    radial-gradient(940px 940px at 86% 102%, rgba(233, 83, 26, 0.62), transparent 66%),
    radial-gradient(700px 700px at 0% 90%, rgba(255, 180, 132, 0.55), transparent 62%),
    linear-gradient(135deg, #e2c6b6 0%, #d2a996 44%, #bd8b77 100%);
  background-attachment: fixed;
}}

.vt-decor {{
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}}
.vt-orb, .vt-ring {{
  position: absolute;
  display: block;
  filter: blur(30px);
  opacity: 0.78;
  animation: vt-float 26s ease-in-out infinite alternate;
}}
.vt-orb-a {{
  width: 300px; height: 300px; border-radius: 50%;
  left: -95px; top: 17%;
  background: radial-gradient(circle at 34% 30%, #ffe3c6, #ff8f4a 58%, rgba(255, 124, 56, 0.22));
}}
.vt-orb-b {{
  width: 540px; height: 540px; border-radius: 50%;
  right: -170px; top: -150px;
  background: radial-gradient(circle at 40% 38%, #ffb27a, #f4661f 60%, rgba(214, 70, 18, 0.18));
  animation-delay: -8s;
}}
.vt-orb-c {{
  width: 250px; height: 250px; border-radius: 50%;
  left: 57%; bottom: -85px;
  background: radial-gradient(circle at 38% 32%, #ffc79a, #e85a1c 62%, rgba(206, 68, 16, 0.18));
  animation-delay: -14s;
}}
.vt-ring {{
  border-radius: 50%;
  filter: blur(6px);
  background: transparent;
}}
.vt-ring-a {{
  width: 200px; height: 200px;
  left: 21%; top: 4%;
  border: 24px solid rgba(255, 203, 166, 0.95);
  box-shadow: 0 0 60px rgba(255, 166, 110, 0.75) inset;
  transform: rotate(-18deg);
}}
.vt-ring-b {{
  width: 160px; height: 160px;
  right: 19%; bottom: 3%;
  border: 21px solid rgba(255, 186, 138, 0.92);
  box-shadow: 0 0 50px rgba(238, 116, 52, 0.62) inset;
  transform: rotate(24deg);
  animation-delay: -11s;
}}
@keyframes vt-float {{
  from {{ transform: translate3d(0, 0, 0) rotate(-18deg); }}
  to   {{ transform: translate3d(18px, -26px, 0) rotate(-10deg); }}
}}
@media (prefers-reduced-motion: reduce) {{
  .vt-orb, .vt-ring {{ animation: none; }}
}}

/* --- szklany panel treści --- */
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ right: 1rem; }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
.block-container {{
  margin-top: 1.4rem;
  margin-bottom: 2.4rem;
  padding: 2.4rem 2.6rem 2.8rem;
  background: linear-gradient(160deg, rgba(255, 247, 240, 0.34), rgba(255, 240, 230, 0.16));
  border: 1px solid var(--vt-line);
  border-radius: var(--vt-radius);
  box-shadow: 0 22px 60px rgba(90, 40, 18, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(22px) saturate(140%);
  -webkit-backdrop-filter: blur(22px) saturate(140%);
}}
@supports not (backdrop-filter: blur(2px)) {{
  .block-container {{ background: rgba(236, 214, 199, 0.94); }}
}}

/* --- typografia --- */
html, body, [class*="css"] {{
  font-family: "Segoe UI", "Inter", system-ui, -apple-system, sans-serif;
  color: var(--vt-ink);
}}
[data-testid="stHeading"] h1, h1 {{
  letter-spacing: -0.025em;
  font-weight: 700;
  color: var(--vt-ink);
}}
[data-testid="stHeading"] h2, [data-testid="stHeading"] h3, h2, h3 {{
  color: var(--vt-ink);
  letter-spacing: -0.01em;
}}
[data-testid="stMarkdown"] p, [data-testid="stMarkdown"] li {{
  color: var(--vt-ink);
}}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
  color: var(--vt-ink-soft);
}}
.vt-kicker {{
  text-transform: uppercase;
  letter-spacing: 0.32em;
  font-size: 0.68rem;
  font-weight: 600;
  color: rgba(59, 27, 12, 0.7);
  margin-bottom: 0.55rem;
}}
.vt-rule {{
  height: 1px;
  margin: 0.9rem 0 1.3rem;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.15));
}}
.vt-brand {{
  text-transform: uppercase;
  letter-spacing: 0.3em;
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--vt-ink);
  padding: 0.2rem 0 0.1rem;
}}
.vt-brand span {{ color: var(--vt-accent); }}

/* --- kafle, kontenery z ramką, expandery: szkło --- */
[data-testid="stMetric"] {{
  background: linear-gradient(150deg, rgba(255, 248, 242, 0.3), rgba(255, 240, 230, 0.16));
  border: 1px solid var(--vt-line);
  border-radius: 18px;
  padding: 0.9rem 1rem;
  box-shadow: 0 10px 30px rgba(120, 48, 12, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}}
[data-testid="stMetricLabel"] {{ color: var(--vt-ink-soft); }}
[data-testid="stMetricValue"] {{ color: var(--vt-ink); letter-spacing: -0.02em; }}
[data-testid="stMetricDelta"] {{ font-weight: 600; }}

[data-testid="stVerticalBlockBorderWrapper"] {{
  background: linear-gradient(160deg, rgba(255, 248, 242, 0.36), rgba(255, 240, 230, 0.16));
  border: 1px solid var(--vt-line);
  border-radius: 20px;
  box-shadow: 0 14px 36px rgba(120, 48, 12, 0.1);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}}
[data-testid="stExpander"] details {{
  background: rgba(255, 247, 240, 0.28);
  border: 1px solid var(--vt-line);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
[data-testid="stExpander"] summary:hover {{ color: var(--vt-accent); }}

/* --- przyciski --- */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  background: rgba(255, 247, 240, 0.36);
  color: var(--vt-ink);
  font-weight: 600;
  padding: 0.45rem 1.25rem;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {{
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(120, 48, 12, 0.18);
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: linear-gradient(135deg, var(--vt-accent-2), var(--vt-accent));
  border-color: rgba(255, 255, 255, 0.55);
  color: #fff8f2;
  box-shadow: 0 12px 28px rgba(180, 62, 16, 0.35);
}}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.05); }}

/* --- taby --- */
[data-testid="stTabs"] {{ margin-top: 0.5rem; }}
[data-testid="stTabs"] [role="tablist"] {{
  gap: 0.35rem;
  padding: 0.3rem;
  background: rgba(255, 248, 242, 0.26);
  border: 1px solid var(--vt-line);
  border-radius: 999px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
[data-testid="stTabs"] button[role="tab"] {{
  border-radius: 999px;
  color: var(--vt-ink-soft);
  padding: 0.35rem 1rem;
}}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  background: rgba(255, 255, 255, 0.92);
  color: var(--vt-accent);
  font-weight: 700;
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}

/* --- formularze --- */
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="select"] > div {{
  background: rgba(255, 250, 244, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 12px;
  color: var(--vt-ink);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {{
  color: var(--vt-ink);
}}
[data-testid="stWidgetLabel"] p {{ color: var(--vt-ink-soft); font-weight: 600; }}
[data-testid="stCheckbox"] label p, [data-testid="stToggle"] label p {{ color: var(--vt-ink); }}

/* --- tabele: jasny szklany kafel wokół siatki --- */
[data-testid="stDataFrame"] {{
  background: rgba(255, 250, 246, 0.7);
  border: 1px solid var(--vt-line);
  border-radius: 16px;
  padding: 0.35rem;
  box-shadow: 0 10px 28px rgba(120, 48, 12, 0.1);
}}
[data-testid="stTable"] table {{ border-radius: 16px; overflow: hidden; }}

/* --- pasek boczny --- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, rgba(255, 246, 238, 0.72), rgba(240, 213, 195, 0.56));
  border-right: 1px solid rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}}
[data-testid="stSidebar"] [data-testid="stMarkdown"] p {{ color: var(--vt-ink); }}
[data-testid="stSidebarNav"] a {{
  border-radius: 12px;
  color: var(--vt-ink);
}}
[data-testid="stSidebarNav"] a:hover {{ background: rgba(255, 255, 255, 0.6); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: rgba(255, 255, 255, 0.9);
  color: var(--vt-accent);
  font-weight: 700;
}}

/* --- komunikaty: delikatne szkło zamiast krzyczących banerów --- */
[data-testid="stAlert"] {{
  border-radius: 16px;
  border: 1px solid var(--vt-line);
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
[data-testid="stAlert"] p {{ color: var(--vt-ink); }}
</style>
"""


def inject() -> None:
    """Wstrzyknij dekoracje tła i arkusz stylów (wywoływane raz na przebieg)."""
    st.markdown(DECOR, unsafe_allow_html=True)
    st.markdown(CSS, unsafe_allow_html=True)
