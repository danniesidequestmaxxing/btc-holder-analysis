# BTC Holder Breakdown

Live Streamlit dashboard visualizing the distribution of Bitcoin's circulating
supply across centralized exchanges, public-company treasuries, and everything
else ("retail / unknown").

Built on **free public APIs** — no keys, no signup:

- **mempool.space** — per-address BTC balances for curated CEX cold wallets.
- **CoinGecko** — public-company BTC treasuries + circulating supply.

## Setup

```bash
pip install -r requirements.txt
streamlit run main.py
```

Opens at <http://localhost:8501>.

## How it works

- `main.py` sums BTC balances for a curated set of CEX cold wallets via
  mempool.space, pulls public-company treasuries from CoinGecko's
  `/companies/public_treasury/bitcoin` endpoint, and computes a residual
  "Other / Retail / Unknown" bucket from circulating supply.
- Renders a Plotly donut and a top-10 entities table.
- All responses are cached for 10 minutes via `st.cache_data`. The sidebar
  **Refresh data** button clears the cache and re-fetches.

## Extending coverage

CEX reserves are scattered across hundreds of wallets — the numbers are only as
complete as `CEX_WALLETS` at the top of `main.py`. To improve coverage, add
more labeled cold-wallet addresses (e.g. from
[BitInfoCharts](https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html))
to that dict.

## Caveats

- ETFs and private funds are not represented in the institutional bucket —
  CoinGecko's endpoint only covers **public** companies.
- The "Other" slice is a residual and therefore includes everything we can't
  attribute, including lost coins and Satoshi's stash.
