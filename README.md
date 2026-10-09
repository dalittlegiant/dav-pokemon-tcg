# dav-pokemon-tcg 🃏

Automated Pokémon TCG price tracker: a scheduled scraper collects Raw / PSA 9 /
PSA 10 market prices from public PriceCharting pages, and a Streamlit dashboard
presents them with EN/JP comparisons, trend charts, and daily AI market reads.

**Live dashboard:** Streamlit Cloud (auto-deploys from `main`)

## How it works

```
GitHub Actions (cron) → update_prices.py → data/*.json → Streamlit app.py
```

- Price update every 4 hours (`0 */4 * * *`) — zero LLM cost, pure scraping
- AI market commentary once daily (`0 9 * * *`) via `--with-analysis` (OpenRouter)

## For AI assistants & developers

📖 **[AGENTS.md](AGENTS.md)** — the project's operating manual: architecture,
file map, schemas, SOPs for adding cards, and the self-maintenance rule.
**Read it before changing anything.**

## Quick start

```bash
pip install -r requirements.txt
python update_prices.py                  # numeric update
python update_prices.py --with-analysis  # + AI commentary (needs OPENROUTER_API_KEY)
streamlit run app.py                     # dashboard
```

See `.env.example` for configuration. Never commit secrets — use GitHub
Repository Secrets for Actions.
