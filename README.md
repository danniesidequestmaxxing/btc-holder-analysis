# BTC Holder Breakdown

Live dashboard visualizing the distribution of Bitcoin's circulating supply
across centralized exchanges, public-company treasuries, and everything else
("retail / unknown").

Powered entirely by **free public APIs with CORS enabled** — no backend, no API
keys, no signup:

- **mempool.space** — per-address BTC balances for curated CEX cold wallets.
- **CoinGecko** — public-company BTC treasuries + circulating supply.

Two ways to run it:

## Option 1 — Deploy on Vercel (static, zero config)

The entire app is a single `index.html` at the repo root. Vercel auto-detects
and serves it as a static site.

**One-click:**
1. Go to <https://vercel.com/new>.
2. Import this repo (`danniesidequestmaxxing/btc-holder-analysis`).
3. Accept all defaults (Framework Preset: **Other**, no build command, output
   directory: `./`).
4. Deploy. Done.

**Or from the CLI:**
```bash
npm i -g vercel
vercel        # preview deploy
vercel --prod # production
```

Local preview (no build step needed):
```bash
python -m http.server 8000
# then open http://localhost:8000
```

## Option 2 — Local Streamlit (Python)

Same data, same logic, Python/Streamlit UI instead of HTML.

```bash
pip install -r requirements.txt
streamlit run main.py
```

Opens at <http://localhost:8501>.

## How it works

1. Browser (or Streamlit) sums BTC balances for a curated set of CEX cold
   wallets via mempool.space.
2. Pulls public-company BTC treasuries from CoinGecko's
   `/companies/public_treasury/bitcoin` endpoint.
3. Computes the "Other / Retail / Unknown" bucket as the residual of
   circulating supply minus everything tracked above.
4. Renders a Plotly donut and a top-10 entities table.

## Extending coverage

CEX reserves are scattered across hundreds of wallets — numbers are only as
complete as `CEX_WALLETS`. To improve coverage, add more labeled cold-wallet
addresses (e.g. from
[BitInfoCharts](https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html))
to the dict:

- **Static version:** top of `index.html` (`const CEX_WALLETS`).
- **Streamlit version:** top of `main.py` (`CEX_WALLETS`).

## Caveats

- ETFs and private funds are not represented in the institutional bucket —
  CoinGecko's endpoint only covers **public** companies.
- The "Other" slice is a residual and therefore includes everything we can't
  attribute, including lost coins and Satoshi's stash.
