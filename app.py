"""Streamlit dashboard for the Pokemon card price tracker.

Run:  streamlit run app.py
Data: reads data/latest_summary.json + data/history_prices.json (written by update_prices.py)
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_FILE = BASE_DIR / "data" / "latest_summary.json"
HISTORY_FILE = BASE_DIR / "data" / "history_prices.json"

st.set_page_config(page_title="Pokemon Card Tracker", page_icon="🃏", layout="wide")


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
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


summary = load_summary()
history = load_history()

st.title("🃏 Pokemon Card Tracker")
if not summary:
    st.warning("No data yet -- run `python update_prices.py` first.")
    st.stop()
st.caption(f"Last updated {summary.get('generated_at', '?')}  ·  "
           f"US$1 = HK${summary.get('hkd_rate', 7.8)}")

cards = summary["cards"]

# ---------------- My chase list (mirrors the report page) ----------------
st.header("My chase list")
cols = st.columns(3)
for i, card in enumerate(cards):
    with cols[i % 3]:
        with st.container(border=True):
            if card.get("image_url"):
                st.image(card["image_url"], use_container_width=True)
            st.subheader(card["card_name"])
            st.caption(f"{card['set_name']} · {card['set_number']} · "
                       f"{card['language']} · {card['variant']}")
            for grade, g in card["grades"].items():
                if g["price_usd"]:
                    st.write(f"**{grade.upper()}**  "
                             f"${g['price_usd']:,.2f} / HK${g['price_hkd']:,.0f}")
                else:
                    st.write(f"**{grade.upper()}**  —")
            if card.get("analysis"):
                st.info(f"🤖 {card['analysis']}")
            with st.expander("Price History & Trend"):
                h = history[(history["card_id"] == card["card_id"])
                            & history["price_usd"].notna()]
                if h.empty:
                    st.write("No history yet -- check back after a few runs.")
                else:
                    grades = sorted(h["grade"].unique())
                    sel = st.multiselect("Grades", grades, default=grades,
                                         key=f"grades-{card['card_id']}")
                    if sel:
                        pivot = (h[h["grade"].isin(sel)]
                                 .pivot_table(index="timestamp", columns="grade",
                                              values="price_usd"))
                        st.line_chart(pivot)

# ---------------- Market matrix ----------------
st.header("Market matrix")
rows = []
for card in cards:
    for grade, g in card["grades"].items():
        rows.append({
            "Card": f"{card['card_name']} ({card['set_number']})",
            "Lang": card["language"],
            "Grade": grade.upper(),
            "USD": g["price_usd"],
            "HKD": g["price_hkd"],
            "Source": g["source"],
            "Updated": g["timestamp"],
        })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
