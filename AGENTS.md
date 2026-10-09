# AGENTS.md — Project Operating Manual

> **Self-maintenance rule (crucial):** Whenever an AI assistant or developer
> alters the project architecture, data schemas, or workflow triggers, they
> **MUST update this file in the same commit** to keep the specification
> accurate. Stale docs are worse than no docs.

This document is the persistent project memory for `dav-pokemon-tcg`. Any
future AI assistant or developer should read it before touching the codebase.

---

## 1. Project Mission & Architecture Overview

**Mission:** An automated, near-zero-cost Pokémon TCG price tracker. A
scheduled scraper collects market prices for a curated chase list, and a
Streamlit dashboard presents them with EN/JP comparisons, trend charts, and
daily AI market commentary.

**High-level data flow:**

```
GitHub Actions (cron)
        │  .github/workflows/tracker.yml
        ▼
update_prices.py ──scrapes──▶ public PriceCharting product pages
        │                          (no token, no login)
        ├─▶ data/history_prices.json   (APPEND-ONLY)
        └─▶ data/latest_summary.json   (OVERWRITTEN snapshot)
        │  git add + commit + push (needs `permissions: contents: write`)
        ▼
Streamlit Cloud ──reads──▶ app.py renders data/*.json live
```

**Cost-efficiency principles (do not regress these):**

- **No PriceCharting API token.** Prices come from scraping *public* product
  pages with `requests` + BeautifulSoup. There is deliberately no
  `PRICECHARTING_API_TOKEN` anywhere in the project.
- **LLM calls are rationed.** OpenRouter is invoked **only** on runs with the
  `--with-analysis` flag (once daily at 09:00 UTC). Each call produces a 2–3
  sentence market summary per card. Plain runs (`0 */4 * * *`) consume
  **zero** LLM tokens and *retain* the previous AI insights in the snapshot.

**Schedules** (`.github/workflows/tracker.yml`):

| Cron | Command | Purpose |
|---|---|---|
| `0 */4 * * *` | `python update_prices.py` | Numeric price update, 0 LLM tokens |
| `0 9 * * *` | `python update_prices.py --with-analysis` | Numeric update + fresh AI commentary |

Manual runs are possible via `workflow_dispatch` (with an optional
`with_analysis` boolean).

---

## 2. Repository File Map & Responsibilities

```
.
├── AGENTS.md                  ← this file (project memory — keep current!)
├── README.md                  ← public-facing overview, links here
├── app.py                     ← Streamlit dashboard (styled frontend)
├── update_prices.py           ← scraper + pipeline (GitHub Actions entrypoint)
├── chasing_list.json          ← SINGLE SOURCE OF TRUTH for tracked cards
├── requirements.txt           ← streamlit, pandas, requests, beautifulsoup4
├── .env.example               ← documents env vars (never commit real secrets)
├── push_update.sh             ← local helper: run pipeline, commit, push
├── data/
│   ├── history_prices.json    ← append-only price database
│   └── latest_summary.json    ← latest snapshot + AI insights (dashboard reads this)
└── .github/workflows/tracker.yml ← cron scheduler (permissions: contents: write)
```

### `app.py` — Streamlit frontend

- Styled dashboard; visual system is injected via
  `st.markdown(..., unsafe_allow_html=True)` (Google Fonts: IBM Plex Mono +
  Public Sans, `:root` theme variables, grid background).
- **Chase list is grouped by `card_name`.** Each topic renders ONE card tile
  with a single thumbnail and an **EN vs JP raw price pair**
  (`.price-pair` with vertical divider). A card with no JP variant renders
  "EN exclusive — no JP print". Therefore: **distinct topics need distinct
  `card_name` values** (e.g. `Psyduck & Slowpoke GX Alt Art` vs
  `Psyduck & Slowpoke GX Full Art`), or tiles merge and the layout breaks.
- **Market Matrix is a pure HTML `<table>`** (`.table-shell` / `.matrix`),
  with EN/JP badges, bold USD + green HKD, PriceCharting source links, and
  trend badges computed from history.
- **STRICT RULE: never downgrade the matrix to an unstyled `st.dataframe`.**
  The custom table is a deliberate design decision (dark headers, badges,
  links, trend tags).
- Each tile has `st.expander("Price History & Trend")` with a series
  multiselect (defaults to EN RAW + JP RAW) rendering `st.line_chart`.
- Narrative sections below the table: *Discrepancies & relative value*
  (dynamic EN/JP premium lines) and *Reading the snapshot / Methodology*.

### `update_prices.py` — scraper & pipeline

- For each card, fetches its `pricecharting_url` and parses the page's
  `table#price_data`. **Grades are matched by header text, not `<td>` ids**
  (PriceCharting reuses legacy video-game ids): `Ungraded` → `raw`,
  `Grade 9` → `psa9`, `PSA 10` → `psa10`.
- Polite crawling: browser-like User-Agent, 1.5 s delay between cards,
  3 attempts with backoff per card. **One card failing must never kill the
  run** (failures are logged, other cards continue).
- `fetch_tcgplayer()` / `fetch_ebay_sold()` are explicit stubs until
  authorized API access exists.
- **Deduplication:** a record is skipped when the exact same
  `card_id + grade + price_usd` was already logged within the last
  **1 hour** (`DEDUP_WINDOW_HOURS`). `history_prices.json` is otherwise
  append-only; `latest_summary.json` is overwritten each run.
- Plain runs preserve the previous `analysis` text per card (token
  conservation); `--with-analysis` refreshes it via OpenRouter.

### `chasing_list.json` — single source of truth for cards

Edit this file to add/remove cards. **No Python changes needed.** Schema per
entry:

| Key | Meaning | Example |
|---|---|---|
| `card_id` | Unique slug: `{name}-{number}-{lang}` | `charizard-ex-151-sir-en` |
| `card_name` | **Grouping key** for the dashboard tile | `Psyduck & Slowpoke GX Alt Art` |
| `grades` | Always `["raw", "psa9", "psa10"]` | — |
| `image_url` | Card thumbnail (see SOP §3) | `https://images.pokemontcg.io/…` |
| `language` | `EN` or `JP` | `EN` |
| `pricecharting_url` | Canonical public product page (see SOP §3) | `https://www.pricecharting.com/game/…` |
| `set_name` | Human-readable set | `Unified Minds` |
| `set_number` | Printed number | `218/236` |
| `variant` | Art/rarity descriptor | `Alternate Art` |

Top-level `fx.usd_to_hkd` is the default FX rate (env `USD_TO_HKD` overrides).

### `data/latest_summary.json` vs `data/history_prices.json`

- `latest_summary.json` — **snapshot**, overwritten every run. Fields:
  `generated_at`, `hkd_rate`, `analysis_model`, `cards[]` (each with
  `grades.{raw,psa9,psa10} → {price_usd, price_hkd, source, timestamp}`,
  plus `analysis`). **The dashboard reads only this file** (plus history for
  trends).
- `history_prices.json` — **append-only database** of
  `{timestamp, card_id, grade, price_usd, price_hkd, source}` records.
  Never rewrite history; the 1-hour dedup keeps it clean.

### `.github/workflows/tracker.yml`

- Cron scheduler (see §1). **Must declare `permissions: contents: write`**
  or the data-commit step fails.
- Secrets (Repository Secrets, never hardcoded): `OPENROUTER_API_KEY`
  (required for `--with-analysis`), `OPENROUTER_MODEL` (optional).
- Commit step stages **only** the two data files, commits with a UTC
  timestamp, pushes to `main`. Note: GitHub PATs need the `workflow` scope
  to create/update files under `.github/workflows/` — without it, add the
  file manually via the web UI.

---

## 3. Standard Operating Procedures

### SOP: Adding a new chase card

1. **Find the PriceCharting product URL.**
   - Search PriceCharting; **always use the canonical post-redirect URL**
     (copy it from the browser address bar after the page loads).
   - Known slug quirks (learned the hard way — verify, don't guess):
     - Unified Minds → `pokemon-unified-minds` (NOT `pokemon-sun-&-moon-unified-minds`)
     - Japanese Miracle Twins → `pokemon-japanese-miracle-twins` (plural)
     - Undaunted → `pokemon-undaunted`
     - Japanese promos → `pokemon-japanese-promo` (e.g. `slowpoke-28l-p`)
   - PriceCharting's own title may differ from the official card name
     (e.g. `#217`/`#218` are titled *"Psyduck & Slowpoke GX"*); record the
     official name in `card_name`, but keep the URL exactly as PriceCharting
     serves it.
   - **Verify the page actually contains `table#price_data`** (curl it and
     check). A 200 with a redirect to `/search-products` means the slug is
     wrong.
   - **Verify the Japanese print exists before assuming EN/JP parity.**
     Example: Undaunted #66 Slowpoke has no print in Reviving Legends (the
     JP equivalent set) — its true JP origin is the **028/L-P Domino's Pizza
     promo**. Check Bulbapedia's card page ("Japanese expansion" field) when
     in doubt.
2. **Find the image URL** (must return HTTP 200):
   - EN: `https://images.pokemontcg.io/{setid}/{number}_hires.png`
     (e.g. `sm11/218_hires.png`, `hgss3/66_hires.png`).
   - JP: `https://assets.tcgdex.net/ja/{ERA}/{SET}/{NUM}/high.png`
     (e.g. `ja/SM/SM11/096/high.png`). tcgdex lacks very old promos — the
     PriceCharting CDN image (`storage.googleapis.com/images.pricecharting.com/…`)
     is an acceptable fallback after verifying it loads.
   - If no image can be found: **leave `image_url` empty and continue** —
     never stall the task on one asset (dashboard renders a placeholder).
3. **Append the entry/entries to `chasing_list.json`** (EN and JP as separate
   entries sharing one `card_name` so the dashboard pairs them; use distinct
   `card_name`s for distinct art variants).
4. **Test locally:** `python update_prices.py` and confirm the new
   `card_id`s show real prices in `data/latest_summary.json`.
5. Commit `chasing_list.json` + regenerated `data/*.json`, push to `main`.

### SOP: Running updates

- **Locally:** `python update_prices.py` (numeric) or
  `python update_prices.py --with-analysis` (needs `OPENROUTER_API_KEY` in
  env). Or use `./push_update.sh` (runs pipeline, commits data, pushes).
- **Via GitHub Actions:** automatic on cron; or Actions tab →
  *Card price tracker* → *Run workflow* (toggle `with_analysis` for AI
  commentary). The daily 09:00 UTC run is the canonical source of AI
  insights — local runs without the key simply preserve existing ones.

### SOP: Secrets & security

- This is a **public** repo: never commit API keys, tokens, or PATs.
- `.env` and `.streamlit/secrets.toml` are git-ignored; use env vars locally
  and GitHub Secrets in Actions. The supplied GitHub PAT is for pushing
  only — pass it via environment variable, never embed it in the remote URL
  or any file. Rotate it if it was ever pasted in chat.

---

## 4. Current Inventory (as of 2026-10-10)

8 chase topics / 15 tracked variants:

| Topic | EN | JP |
|---|---|---|
| Charizard ex | 199/165 Scarlet & Violet 151 (SIR) | 201/165 Pokemon Card 151 (SAR) |
| Pikachu with Grey Felt Hat | 085 SVP Black Star Promos | — (EN exclusive) |
| Umbreon VMAX | 215/203 Evolving Skies (Alt Art) | 095/069 Eevee Heroes (HR) |
| Psyduck & Slowpoke GX Alt Art | 218/236 Unified Minds | 096/094 Miracle Twins |
| Slowpoke & Psyduck GX | 35/236 Unified Minds | 011/094 Miracle Twins |
| Psyduck & Slowpoke GX Full Art | 217/236 Unified Minds | 095/094 Miracle Twins |
| Slowpoke & Psyduck GX Rainbow | 239/236 Unified Minds | 107/094 Miracle Twins |
| Slowpoke | 66/90 Undaunted | 028/L-P L-P Promotional Cards (Domino's Pizza) |

---

## 5. Known Limitations / Roadmap

- TCGplayer and eBay sources are stubs (need partner/API credentials).
- PriceCharting scraping is brittle by nature: if `#price_data` changes,
  update the header-mapping in `update_prices.py`.
- AI insights depend on `OPENROUTER_API_KEY` being set as a repo secret;
  without it, commentary goes stale (dashboard degrades gracefully).
- No alerting on scrape failures beyond workflow logs.
