"""Streamlit dashboard for the Pokemon card price tracker -- styled edition.

Visual system mirrors the original HTML report artifact:
IBM Plex Mono + Public Sans, dark grid background, yellow accents,
chase-list summary cards, custom market matrix, narrative sections.

Run:  streamlit run app.py
Data: reads data/latest_summary.json + data/history_prices.json (written by
      update_prices.py) and chasing_list.json (for PriceCharting source URLs).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_FILE = BASE_DIR / "data" / "latest_summary.json"
HISTORY_FILE = BASE_DIR / "data" / "history_prices.json"
CHASING_FILE = BASE_DIR / "chasing_list.json"

st.set_page_config(page_title="Pokemon Card Tracker", page_icon="🃏", layout="wide")

# ---------------------------------------------------------------- data ----
@st.cache_data(ttl=300)
def load_summary():
    try:
        return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


@st.cache_data(ttl=300)
def load_history():
    try:
        df = pd.read_json(HISTORY_FILE, encoding="utf-8")
    except (FileNotFoundError, ValueError):
        return pd.DataFrame()
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


@st.cache_data(ttl=300)
def load_chasing():
    try:
        return json.loads(CHASING_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cards": []}


summary = load_summary()
history = load_history()
chasing = load_chasing()
pc_url_by_id = {c.get("card_id"): c.get("pricecharting_url", "")
                for c in chasing.get("cards", [])}

# ------------------------------------------------------------- helpers ----
def fmt_usd(v):
    return f"${v:,.2f}" if v is not None else "—"


def fmt_hkd(v):
    return f"HK${v:,.0f}" if v is not None else "—"


def hkt_str(iso_ts):
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hkt = dt.astimezone(timezone(timedelta(hours=8)))
        return hkt.strftime("%-d %b %Y · %H:%M HKT")
    except Exception:
        return iso_ts


def trend_for(card_id, grade):
    """(label, css_class, pct) from price history, or ('n/a','info', None)."""
    h = history[(history["card_id"] == card_id)
                & (history["grade"] == grade)
                & history["price_usd"].notna()].sort_values("timestamp")
    if len(h) < 2:
        return "n/a", "info", None
    first, last = float(h.iloc[0]["price_usd"]), float(h.iloc[-1]["price_usd"])
    if not first:
        return "n/a", "info", None
    pct = (last - first) / first * 100
    if pct > 2:
        return f"▲ {pct:+.1f}%", "up", pct
    if pct < -2:
        return f"▼ {pct:+.1f}%", "down", pct
    return f"▬ {pct:+.1f}%", "flat", pct


GRADE_LABEL = {"raw": "RAW", "psa9": "PSA 9", "psa10": "PSA 10"}

# ----------------------------------------------------------------- css ----
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Public+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0e14; --panel:#11151f; --panel-2:#151b29;
  --line:rgba(255,255,255,.07);
  --text:#e9ecf3; --muted:#9aa3b5; --faint:#6b7484;
  --accent:#ffd23f; --accent-dim:rgba(255,210,63,.14);
  --green:#3ddc84; --green-dim:rgba(61,220,132,.12);
  --red:#ff6b6b; --red-dim:rgba(255,107,107,.12);
  --blue:#5aa9ff; --blue-dim:rgba(90,169,255,.12);
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  --sans:'Public Sans',system-ui,sans-serif;
}
.stApp{
  background-color:var(--bg);
  background-image:linear-gradient(var(--line) 1px,transparent 1px),
                   linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:44px 44px;
  color:var(--text); font-family:var(--sans);
}
.block-container{padding-top:2rem;max-width:1200px;}
h1,h2,h3{font-family:var(--sans);color:var(--text);}
/* ---------- hero ---------- */
.hero{
  border:1px solid var(--accent); border-radius:14px;
  background:linear-gradient(180deg,rgba(255,210,63,.07),rgba(255,210,63,.015)),var(--panel);
  padding:28px 30px; margin-bottom:26px; position:relative; overflow:hidden;
}
.snapshot-pill{
  display:inline-block; font-family:var(--mono); font-size:11px; font-weight:600;
  letter-spacing:.14em; color:#0b0e14; background:var(--accent);
  padding:5px 12px; border-radius:999px; margin-bottom:14px;
}
.hero h1{font-size:34px; font-weight:800; margin:0 0 8px; letter-spacing:-.01em;}
.hero .lede{color:var(--muted); font-size:15px; max-width:720px; margin:0 0 16px; line-height:1.55;}
.meta-bar{display:flex; flex-wrap:wrap; gap:8px 22px; border-top:1px solid var(--line);
  padding-top:14px; font-family:var(--mono); font-size:12px; color:var(--muted);}
.meta-bar b{color:var(--text); font-weight:600;}
/* ---------- section titles ---------- */
.sec-title{font-size:20px; font-weight:700; margin:30px 0 4px;}
.sec-sub{color:var(--muted); font-size:13.5px; margin-bottom:16px;}
/* ---------- chase cards ---------- */
.chase-grid{display:grid; grid-template-columns:repeat(3,1fr); gap:16px;}
.card-summary{
  display:flex; gap:14px; background:var(--panel); border:1px solid var(--line);
  border-radius:12px; padding:16px; align-items:flex-start;
}
.card-summary img.thumb{
  width:108px; aspect-ratio:3/4; object-fit:cover; border-radius:8px;
  border:1px solid var(--line); flex-shrink:0; background:var(--panel-2);
}
.card-meta{min-width:0; flex:1;}
.card-name{font-weight:700; font-size:16px; line-height:1.25;}
.card-sub{font-family:var(--mono); font-size:11px; color:var(--muted); margin:4px 0 10px; line-height:1.5;}
.price-strip{display:flex; gap:10px; margin-bottom:10px;}
.price-cell{flex:1; background:var(--panel-2); border:1px solid var(--line);
  border-radius:8px; padding:8px 10px; min-width:0;}
.price-cell .g{font-family:var(--mono); font-size:10px; letter-spacing:.1em; color:var(--faint); display:block;}
.price-cell .u{font-family:var(--mono); font-weight:700; font-size:14.5px; display:block; margin-top:2px;}
.price-cell .h{font-family:var(--mono); font-size:11.5px; color:var(--green); display:block; margin-top:1px;}
.ai-badge{background:var(--blue-dim); border:1px solid rgba(90,169,255,.35);
  border-radius:8px; padding:8px 10px; font-size:12.5px; color:#cfe3ff; line-height:1.5;}
/* ---------- table ---------- */
.table-shell{background:var(--panel); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; overflow-x:auto;}
table.matrix{width:100%; border-collapse:collapse; font-size:13.5px; min-width:760px;}
table.matrix thead th{
  font-family:var(--mono); font-size:11px; font-weight:600; letter-spacing:.12em;
  text-transform:uppercase; color:var(--muted); background:#0d1119;
  padding:12px 14px; text-align:left; border-bottom:1px solid var(--line); white-space:nowrap;
}
table.matrix tbody td{padding:12px 14px; border-bottom:1px solid var(--line); vertical-align:middle;}
table.matrix tbody tr:last-child td{border-bottom:none;}
table.matrix tbody tr:hover{background:rgba(255,255,255,.02);}
.cname{font-weight:600;}
.cnum{font-family:var(--mono); font-size:11px; color:var(--faint); margin-top:2px;}
.badge{display:inline-block; font-family:var(--mono); font-size:11px; font-weight:700;
  border:1px solid var(--line); border-radius:6px; padding:3px 8px; letter-spacing:.06em;}
.badge.en{color:var(--accent); border-color:rgba(255,210,63,.4);}
.badge.jp{color:var(--blue); border-color:rgba(90,169,255,.4);}
.grade-tag{font-family:var(--mono); font-size:11.5px; color:var(--muted); white-space:nowrap;}
.usd{font-family:var(--mono); font-weight:700; font-size:14.5px;}
.hkd{font-family:var(--mono); font-size:11.5px; color:var(--green); margin-top:2px;}
a.src{font-family:var(--mono); font-size:12px; color:var(--accent); text-decoration:none; white-space:nowrap;}
a.src:hover{text-decoration:underline;}
.trend{display:inline-block; font-family:var(--mono); font-size:11.5px; font-weight:600;
  border-radius:6px; padding:4px 9px; white-space:nowrap;}
.trend.up{background:var(--green-dim); color:var(--green);}
.trend.down{background:var(--red-dim); color:var(--red);}
.trend.flat{background:rgba(255,255,255,.06); color:var(--muted);}
.trend.info{background:var(--blue-dim); color:var(--blue);}
/* ---------- narrative ---------- */
.narr-grid{display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:6px;}
.narr-card{background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:20px 22px;}
.narr-card h3{font-size:15px; margin:0 0 10px; display:flex; align-items:center; gap:8px;}
.narr-card h3 .dot{width:8px; height:8px; border-radius:50%; background:var(--accent); display:inline-block;}
.narr-card ul{margin:0; padding-left:18px; color:var(--muted); font-size:13.5px; line-height:1.65;}
.narr-card li{margin-bottom:6px;}
.narr-card li b{color:var(--text);}
.narr-card p{color:var(--muted); font-size:13.5px; line-height:1.65; margin:0 0 8px;}
.narr-card p b{color:var(--text);}
.footer{margin:34px 0 10px; padding-top:16px; border-top:1px solid var(--line);
  font-family:var(--mono); font-size:11.5px; color:var(--faint); line-height:1.7;}
/* ---------- responsive ---------- */
@media (max-width:980px){
  .chase-grid{grid-template-columns:1fr 1fr;}
  .narr-grid{grid-template-columns:1fr;}
  .hero h1{font-size:27px;}
}
@media (max-width:640px){ .chase-grid{grid-template-columns:1fr;} }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ hero ---
if not summary:
    st.markdown('<div class="hero"><div class="snapshot-pill">● MARKET SNAPSHOT</div>'
                '<h1>Pokémon Card Tracker</h1>'
                '<p class="lede">No data yet — run <code>python update_prices.py</code> first.</p></div>',
                unsafe_allow_html=True)
    st.stop()

cards = summary["cards"]
hkd_rate = summary.get("hkd_rate", 7.8)
gen = summary.get("generated_at", "")

st.markdown(f"""
<div class="hero">
  <div class="snapshot-pill">● MARKET SNAPSHOT</div>
  <h1>Pokémon Card Tracker</h1>
  <p class="lede">Live PriceCharting benchmarks across English &amp; Japanese printings —
  raw, PSA 9 and PSA 10 — with USD/HKD reference pricing and daily AI market reads.</p>
  <div class="meta-bar">
    <span>📅 <b>{hkt_str(gen)}</b></span>
    <span>💱 <b>US$1 = HK${hkd_rate}</b></span>
    <span>🗂 <b>{len(cards)} cards · 3 grades · EN/JP</b></span>
    <span>📊 <b>PriceCharting benchmarks</b></span>
  </div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------ chase list ---
st.markdown('<div class="sec-title">My chase list</div>'
            '<div class="sec-sub">One card per tile — image, reference pricing and the latest AI read.</div>',
            unsafe_allow_html=True)

cols = st.columns(3)
for i, card in enumerate(cards):
    with cols[i % 3]:
        img = (f'<img class="thumb" src="{card["image_url"]}" loading="lazy"/>'
               if card.get("image_url") else '<div class="thumb"></div>')
        cells = []
        for grade in ("raw", "psa9", "psa10"):
            g = card["grades"].get(grade, {})
            cells.append(
                f'<div class="price-cell"><span class="g">{GRADE_LABEL.get(grade, grade)}</span>'
                f'<span class="u">{fmt_usd(g.get("price_usd"))}</span>'
                f'<span class="h">{fmt_hkd(g.get("price_hkd"))}</span></div>')
        ai = (f'<div class="ai-badge">🤖 {card["analysis"]}</div>'
              if card.get("analysis") else "")
        st.markdown(f"""
<div class="card-summary">
  {img}
  <div class="card-meta">
    <div class="card-name">{card['card_name']}</div>
    <div class="card-sub">{card['set_name']} · {card['set_number']} · {card['language']} · {card['variant']}</div>
    <div class="price-strip">{''.join(cells)}</div>
    {ai}
  </div>
</div>
""", unsafe_allow_html=True)
        with st.expander("Price History & Trend"):
            h = history[(history["card_id"] == card["card_id"])
                        & history["price_usd"].notna()]
            if h.empty:
                st.write("No history yet — check back after a few runs.")
            else:
                grades = sorted(h["grade"].unique())
                sel = st.multiselect("Grades", grades, default=grades,
                                     key=f"grades-{card['card_id']}")
                if sel:
                    pivot = (h[h["grade"].isin(sel)]
                             .pivot_table(index="timestamp", columns="grade",
                                          values="price_usd"))
                    st.line_chart(pivot)

# ---------------------------------------------------------- market matrix --
st.markdown('<div class="sec-title">Market matrix</div>'
            '<div class="sec-sub">Every tracked grade, filterable. Prices are PriceCharting market benchmarks.</div>',
            unsafe_allow_html=True)

families = ["All"] + sorted({c["card_name"] for c in cards})
try:
    filt = st.pills("Filter by card", families, default="All")
except AttributeError:  # older Streamlit
    filt = st.radio("Filter by card", families, horizontal=True)

shown = [c for c in cards if filt == "All" or c["card_name"] == filt]

rows_html = []
for card in shown:
    url = pc_url_by_id.get(card["card_id"], "")
    src = (f'<a class="src" href="{url}" target="_blank">PriceCharting ↗</a>'
           if url else '<span class="grade-tag">PriceCharting</span>')
    for grade in ("raw", "psa9", "psa10"):
        g = card["grades"].get(grade, {})
        tlabel, tclass, _ = trend_for(card["card_id"], grade)
        lang_cls = "en" if card["language"] == "EN" else "jp"
        rows_html.append(f"""
<tr>
  <td><div class="cname">{card['card_name']}</div>
      <div class="cnum">{card['set_number']} · {card['set_name']}</div></td>
  <td><span class="badge {lang_cls}">{card['language']}</span></td>
  <td><span class="grade-tag">{GRADE_LABEL.get(grade, grade)}</span></td>
  <td><div class="usd">{fmt_usd(g.get('price_usd'))}</div>
      <div class="hkd">{fmt_hkd(g.get('price_hkd'))}</div></td>
  <td><span class="trend {tclass}">{tlabel}</span></td>
  <td>{src}</td>
</tr>""")

st.markdown(f"""
<div class="table-shell">
<table class="matrix">
<thead><tr>
  <th>Card</th><th>Lang</th><th>Grade</th><th>Market price</th><th>Trend</th><th>Source</th>
</tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------------------- narrative --
def _price(card_id, grade):
    for c in cards:
        if c["card_id"] == card_id:
            return c["grades"].get(grade, {}).get("price_usd")
    return None


def _gap_line(en_id, jp_id, label):
    parts = []
    for grade in ("raw", "psa9", "psa10"):
        en, jp = _price(en_id, grade), _price(jp_id, grade)
        if en and jp:
            pct = (jp - en) / en * 100
            cheaper = "JP" if pct < 0 else "EN"
            parts.append(
                f"<li><b>{label} · {GRADE_LABEL[grade]}</b> — JP {fmt_usd(jp)} vs "
                f"EN {fmt_usd(en)} (<b>{pct:+.1f}%</b>): "
                f"{'Japanese' if cheaper == 'JP' else 'English'} printing is the cheaper entry.</li>")
    return "".join(parts)


disc_items = (_gap_line("charizard-ex-151-sir-en", "charizard-ex-151-sar-jp", "Charizard ex")
              + _gap_line("umbreon-vmax-alt-en", "umbreon-vmax-hr-jp", "Umbreon VMAX"))
if not disc_items:
    disc_items = ("<li>EN/JP comparison needs at least one successful price fetch per "
                  "printing — check back after the next pipeline run.</li>")
disc_items += ("<li><b>Pikachu with Grey Felt Hat</b> has no Japanese variant — "
               "the English SVP promo is the only market.</li>"
               "<li>Premiums reflect different printings and populations, not pure "
               "arbitrage — always compare pop reports and fees before acting.</li>")

st.markdown(f"""
<div class="narr-grid">
  <div class="narr-card">
    <h3><span class="dot"></span>Discrepancies &amp; relative value</h3>
    <ul>{disc_items}</ul>
  </div>
  <div class="narr-card">
    <h3><span class="dot"></span>Reading the snapshot</h3>
    <p><b>Market price</b> is PriceCharting's benchmark from confirmed eBay/TCGplayer
    <b>sold</b> listings — not asking prices. Asks run hotter, especially on low-pop slabs.</p>
    <p><b>Grading economics:</b> a PSA 9→10 gap has to clear grading fees (~$25–150+ per
    card), shipping both ways, and months of waiting before it means anything.</p>
    <h3 style="margin-top:14px"><span class="dot"></span>Methodology &amp; limitations</h3>
    <p>Scraped from public PriceCharting product pages (no login); history appends every
    pipeline run with 1-hour dedup. Thin markets (e.g. PSA 9 on some cards) can swing on
    a single sale — treat small samples with care.</p>
  </div>
</div>
<div class="footer">
  Educational reference only — not financial advice. · Data: PriceCharting · Built {hkt_str(gen)}
</div>
""", unsafe_allow_html=True)
