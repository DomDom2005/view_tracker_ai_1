"""Motyw „warm glass” (referencja: ciepłe tło, rozmyte kule/pierścienie, szklane panele).

Styl jest w całości lokalny: gradienty i kształty rysuje CSS, bez obrazów i bez sieci.
`inject()` wołamy na starcie każdego przebiegu skryptu; zmiana motywu wymaga tylko rerunu.
Kolory bazowe dla widżetów (tabele, inputy) ustawia `.streamlit/config.toml` — ten plik
wymaga restartu serwera, więc po samej zmianie CSS wystarczy odświeżyć stronę.
"""

# ruff: noqa: E501 - długie linie CSS w bloku tekstowym; to nie kod Pythona.
from __future__ import annotations

import streamlit as st

# Paleta: ciepłe piaski i pomarańcze, atrament w brązach (czytelność na jasnym szkle).
INK = "#3b1b0c"
INK_SOFT = "rgba(59, 27, 12, 0.66)"
GLASS = "rgba(255, 255, 255, 0.42)"
GLASS_STRONG = "rgba(255, 255, 255, 0.66)"
LINE = "rgba(255, 255, 255, 0.65)"
ACCENT = "#d94f14"
ACCENT_2 = "#ff8a3d"

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

/* --- tło: ciepły gradient + rozmyte kule i pierścienie --- */
[data-testid="stAppViewContainer"], .stApp {{
  background:
    radial-gradient(900px 620px at 12% 6%, rgba(255, 255, 255, 0.55), transparent 62%),
    radial-gradient(760px 760px at 92% 10%, rgba(255, 150, 72, 0.85), transparent 63%),
    radial-gradient(820px 820px at 82% 96%, rgba(222, 84, 24, 0.72), transparent 64%),
    radial-gradient(620px 620px at 4% 92%, rgba(255, 193, 132, 0.85), transparent 61%),
    linear-gradient(134deg, #fbe5d1 0%, #f6c49e 42%, #ef9b63 100%);
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
  filter: blur(26px);
  opacity: 0.85;
  animation: vt-float 26s ease-in-out infinite alternate;
}}
.vt-orb-a {{
  width: 320px; height: 320px; border-radius: 50%;
  left: -90px; top: 16%;
  background: radial-gradient(circle at 34% 30%, #ffd9b0, #ff8b3d 58%, rgba(255, 120, 40, 0.25));
}}
.vt-orb-b {{
  width: 520px; height: 520px; border-radius: 50%;
  right: -160px; top: -140px;
  background: radial-gradient(circle at 40% 38%, #ffb877, #f26a22 60%, rgba(226, 84, 24, 0.2));
  animation-delay: -8s;
}}
.vt-orb-c {{
  width: 240px; height: 240px; border-radius: 50%;
  left: 58%; bottom: -80px;
  background: radial-gradient(circle at 38% 32%, #ffc48f, #e85f1d 62%, rgba(214, 74, 18, 0.2));
  animation-delay: -14s;
}}
.vt-ring {{
  border-radius: 50%;
  filter: blur(7px);
  background: transparent;
}}
.vt-ring-a {{
  width: 190px; height: 190px;
  left: 22%; top: 5%;
  border: 22px solid rgba(255, 214, 176, 0.95);
  box-shadow: 0 0 60px rgba(255, 170, 110, 0.7) inset;
  transform: rotate(-18deg);
}}
.vt-ring-b {{
  width: 150px; height: 150px;
  right: 20%; bottom: 4%;
  border: 20px solid rgba(255, 186, 128, 0.9);
  box-shadow: 0 0 50px rgba(240, 120, 50, 0.6) inset;
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
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.28));
  border: 1px solid var(--vt-line);
  border-radius: var(--vt-radius);
  box-shadow: 0 24px 70px rgba(120, 48, 12, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(22px) saturate(140%);
  -webkit-backdrop-filter: blur(22px) saturate(140%);
}}
@supports not (backdrop-filter: blur(2px)) {{
  .block-container {{ background: rgba(255, 245, 236, 0.9); }}
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
  background: linear-gradient(150deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.34));
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
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.26));
  border: 1px solid var(--vt-line);
  border-radius: 20px;
  box-shadow: 0 14px 36px rgba(120, 48, 12, 0.1);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}}
[data-testid="stExpander"] details {{
  background: rgba(255, 255, 255, 0.4);
  border: 1px solid var(--vt-line);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
[data-testid="stExpander"] summary:hover {{ color: var(--vt-accent); }}

/* --- przyciski --- */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.55);
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
  background: rgba(255, 255, 255, 0.34);
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
/* Pola wyboru: domyślnie pomarańczowa ramka, po fokusie grubsza (bez skoku layoutu). */
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="select"] > div {{
  background: rgba(255, 255, 255, 0.66);
  border: 1px solid var(--vt-accent) !important;
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(217, 79, 20, 0.12);
  color: var(--vt-ink);
  transition: border-color 120ms ease, box-shadow 120ms ease;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}}
[data-baseweb="input"]:hover > div,
[data-baseweb="textarea"]:hover > div,
[data-baseweb="select"]:hover > div {{
  border-color: var(--vt-accent) !important;
  box-shadow: 0 0 0 2px rgba(217, 79, 20, 0.16);
}}
[data-baseweb="input"]:focus-within > div,
[data-baseweb="textarea"]:focus-within > div,
[data-baseweb="select"]:focus-within > div {{
  border: 2px solid var(--vt-accent) !important;
  box-shadow: 0 0 0 4px rgba(217, 79, 20, 0.18);
}}
/* otwarte menu selecta/multiselecta też dostaje grubszą ramkę */
[data-baseweb="select"] > div[aria-expanded="true"] {{
  border: 2px solid var(--vt-accent) !important;
  box-shadow: 0 0 0 4px rgba(217, 79, 20, 0.18);
}}
[data-testid="stDateInput"] [data-baseweb="input"]:focus-within > div,
[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within > div,
[data-testid="stMultiSelect"] [data-baseweb="select"]:focus-within > div {{
  border-width: 2px !important;
}}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {{
  color: var(--vt-ink);
}}
[data-testid="stWidgetLabel"] p {{ color: var(--vt-ink-soft); font-weight: 600; }}
[data-testid="stCheckbox"] label p, [data-testid="stToggle"] label p {{ color: var(--vt-ink); }}

/* --- tabele: jasny szklany kafel wokół siatki --- */
[data-testid="stDataFrame"] {{
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--vt-line);
  border-radius: 16px;
  padding: 0.35rem;
  box-shadow: 0 10px 28px rgba(120, 48, 12, 0.1);
}}
[data-testid="stTable"] table {{ border-radius: 16px; overflow: hidden; }}

/* --- pasek boczny --- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, rgba(255, 246, 238, 0.86), rgba(255, 233, 214, 0.72));
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
