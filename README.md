# BTC Holder Breakdown

Live Streamlit dashboard visualizing the distribution of Bitcoin's circulating
supply across centralized exchanges, known institutional/whale entities, and
everything else ("retail / unknown").

Data sources:
- **Arkham Intelligence** — per-entity BTC balances (requires API key).
- **CoinGecko** — circulating supply (free, no key).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your ARKHAM_API_KEY
streamlit run main.py
```

The app opens at <http://localhost:8501>.

## How it works

- `main.py` fetches BTC balances for a configurable list of CEX and
  institutional/whale entities from Arkham, pulls the circulating supply from
  CoinGecko, and renders a Plotly donut plus a top-10 holders table.
- Responses are cached for 10 minutes via `st.cache_data` to limit API credit
  usage. Use the **Refresh data** button in the sidebar to force a re-fetch.

## Configuration

The entity slugs tracked live at the top of `main.py` in `CEX_ENTITIES` and
`WHALE_ENTITIES`. Edit them to follow different actors.
