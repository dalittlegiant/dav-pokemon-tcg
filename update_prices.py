#!/usr/bin/env python3
"""
update_prices.py -- Pokemon card price tracking pipeline (no API tokens required).

Usage:
    python update_prices.py                  # numeric update only (0 LLM tokens)
    python update_prices.py --with-analysis  # also refresh AI insights via OpenRouter

Reads:
    chasing_list.json          # cards to track -- edit freely, no code changes needed.
                               # Each card needs a `pricecharting_url`: the public
                               # PriceCharting product page for that card.

Writes (data/):
    data/history_prices.json   # APPEND-ONLY: every run adds timestamped records.
                               # Deduplication: a record is skipped when the exact
                               # same card_id + grade + price was already logged
                               # within the last 1 hour.
    data/latest_summary.json   # OVERWRITTEN: latest snapshot + AI insights.

How prices are fetched:
    Public PriceCharting product pages are scraped with requests + BeautifulSoup
    (no login, no API token). The page's #price_data table is mapped by header:
        "Ungraded" -> raw | "Grade 9" -> psa9 | "PSA 10" -> psa10

Secrets -- environment variables only, never hardcoded:
    OPENROUTER_API_KEY         # required only with --with-analysis
    OPENROUTER_MODEL           # optional, default "openai/gpt-4o-mini"
    USD_TO_HKD                 # optional, default 7.8
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CHASING_LIST = BASE_DIR / "chasing_list.json"
DATA_DIR = BASE_DIR / "data"
HISTORY_FILE = DATA_DIR / "history_prices.json"
SUMMARY_FILE = DATA_DIR / "latest_summary.json"

# PriceCharting #price_data table headers -> our grade names.
GRADE_TO_PC_HEADER = {"raw": "Ungraded", "psa9": "Grade 9", "psa10": "PSA 10"}

DEDUP_WINDOW_HOURS = 1
REQUEST_DELAY_SECONDS = 1.5  # be polite to PriceCharting

HTTP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def parse_price(text):
    """'$1,379.75' -> 1379.75 ; '-', '' or missing -> None."""
    if not text:
        return None
    t = text.strip().replace("$", "").replace(",", "")
    if t in ("", "-", "N/A", "n/a"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fetch_pricecharting(url):
    """Scrape a public PriceCharting product page.

    Returns {grade: (price_usd|None, source|None)}. Grades come from the
    page's #price_data table, matched by header text (robust against the
    legacy td ids PriceCharting reuses from video games).
    """
    resp = None
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
            resp.raise_for_status()
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))  # backoff: 2s, 4s
    if resp is None:
        raise last_exc
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="price_data")
    if not table or not table.find("thead") or not table.find("tbody"):
        return {}
    headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
    cells = table.find("tbody").find_all("td")
    out = {}
    for grade, wanted in GRADE_TO_PC_HEADER.items():
        price, source = None, None
        for header, cell in zip(headers, cells):
            if header == wanted:
                span = cell.find("span", class_="price")
                price = parse_price(span.get_text() if span else "")
                source = "PriceCharting" if price is not None else None
                break
        out[grade] = (price, source)
    return out


def fetch_tcgplayer(card):
    """STUB -- TCGplayer requires partner API keys. Returns {} until configured."""
    return {}


def fetch_ebay_sold(card):
    """STUB -- eBay Browse API needs OAuth app credentials. Returns {} until configured."""
    return {}


def collect_prices(chasing, hkd_rate):
    ts = now_iso()
    records, latest = [], {}
    cards = chasing.get("cards", [])
    for idx, card in enumerate(cards):
        cid = card["card_id"]
        fetched = {}
        url = card.get("pricecharting_url")
        if url:
            try:
                fetched.update(fetch_pricecharting(url))
            except Exception as exc:  # one card failing must not kill the run
                print(f"[warn] PriceCharting scrape failed for {cid}: {exc}", file=sys.stderr)
        else:
            print(f"[warn] no pricecharting_url for {cid}; skipping", file=sys.stderr)
        fetched.update(fetch_tcgplayer(card))
        fetched.update(fetch_ebay_sold(card))

        latest[cid] = {}
        for grade in card.get("grades", []):
            price_usd, source = fetched.get(grade, (None, None))
            price_hkd = round(price_usd * hkd_rate, 2) if price_usd else None
            records.append({
                "timestamp": ts, "card_id": cid, "grade": grade,
                "price_usd": price_usd, "price_hkd": price_hkd, "source": source,
            })
            latest[cid][grade] = {
                "price_usd": price_usd, "price_hkd": price_hkd,
                "source": source, "timestamp": ts,
            }
        if idx < len(cards) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)
    return records, latest


def already_logged(history, card_id, grade, price_usd, window_hours=DEDUP_WINDOW_HOURS):
    """True if the exact same card_id + grade + price was logged within the window.

    History is chronological, so we scan newest-first and stop at the window edge.
    """
    if price_usd is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    for rec in reversed(history):
        try:
            ts = datetime.fromisoformat(rec["timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            break
        if (rec.get("card_id") == card_id
                and rec.get("grade") == grade
                and rec.get("price_usd") == price_usd):
            return True
    return False


def trend_context(history, card_id, grade, max_points=12):
    pts = [r for r in history
           if r["card_id"] == card_id and r["grade"] == grade and r.get("price_usd")]
    pts = pts[-max_points:]
    if len(pts) < 2:
        return "insufficient history"
    first, last = pts[0]["price_usd"], pts[-1]["price_usd"]
    pct = (last - first) / first * 100 if first else 0
    return f"{len(pts)} pts, ${first:,.0f} -> ${last:,.0f} ({pct:+.1f}%)"


def analyze_with_openrouter(chasing, latest, history):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[warn] OPENROUTER_API_KEY not set; skipping analysis.", file=sys.stderr)
        return {}
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    insights = {}
    for card in chasing.get("cards", []):
        cid = card["card_id"]
        lines = []
        for grade in card.get("grades", []):
            g = latest[cid][grade]
            price = f"${g['price_usd']:,.2f}" if g["price_usd"] else "n/a"
            lines.append(f"- {grade}: {price} | trend: {trend_context(history, cid, grade)}")
        prompt = (
            f"You are a Pokemon TCG market analyst. Card: {card['card_name']} "
            f"({card['set_name']} {card['set_number']}, {card['language']}, {card.get('variant', '')}).\n"
            "Latest prices:\n" + "\n".join(lines) + "\n"
            "In 2-3 sharp sentences: price trend, likely driver, one-line outlook. "
            "No financial advice, no filler."
        )
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": "pokemon-card-tracker",
                         "X-Title": "Pokemon Card Tracker"},
                json={"model": model,
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 220},
                timeout=60,
            )
            resp.raise_for_status()
            insights[cid] = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print(f"[warn] OpenRouter failed for {cid}: {exc}", file=sys.stderr)
            insights[cid] = None
    return insights


def main():
    ap = argparse.ArgumentParser(description="Pokemon card price tracking pipeline")
    ap.add_argument("--with-analysis", action="store_true",
                    help="refresh AI market insights via OpenRouter (daily run)")
    args = ap.parse_args()

    chasing = load_json(CHASING_LIST, None)
    if not chasing:
        sys.exit("chasing_list.json not found or invalid -- aborting.")
    hkd_rate = float(os.getenv("USD_TO_HKD",
                               chasing.get("fx", {}).get("usd_to_hkd", 7.8)))

    history = load_json(HISTORY_FILE, [])
    prev_summary = load_json(SUMMARY_FILE, {})
    prev_insights = {c.get("card_id"): c.get("analysis")
                     for c in prev_summary.get("cards", [])}

    records, latest = collect_prices(chasing, hkd_rate)

    # APPEND-ONLY with deduplication: skip a record when the exact same
    # card_id + grade + price was already logged within the last hour.
    appended, skipped = 0, 0
    for rec in records:
        if already_logged(history, rec["card_id"], rec["grade"], rec["price_usd"]):
            skipped += 1
            continue
        history.append(rec)
        appended += 1
    save_json(HISTORY_FILE, history)

    insights = analyze_with_openrouter(chasing, latest, history) if args.with_analysis else {}

    cards_out = []
    for card in chasing.get("cards", []):
        cid = card["card_id"]
        cards_out.append({
            "card_id": cid,
            "card_name": card["card_name"],
            "set_name": card["set_name"],
            "set_number": card["set_number"],
            "language": card["language"],
            "variant": card.get("variant", ""),
            "image_url": card.get("image_url", ""),
            "grades": latest[cid],
            # retain previous insight on plain runs to conserve tokens
            "analysis": insights.get(cid) or prev_insights.get(cid),
        })

    save_json(SUMMARY_FILE, {
        "generated_at": now_iso(),
        "hkd_rate": hkd_rate,
        "analysis_model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
                          if args.with_analysis else prev_summary.get("analysis_model"),
        "cards": cards_out,
    })

    n_ok = sum(1 for r in records if r["price_usd"])
    print(f"done: {n_ok}/{len(records)} prices fetched; "
          f"+{appended} appended, {skipped} dedup-skipped; "
          f"history now {len(history)} records.")


if __name__ == "__main__":
    main()
