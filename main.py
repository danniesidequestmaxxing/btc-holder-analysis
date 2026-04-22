"""Streamlit dashboard: BTC holder breakdown using free public APIs.

Data sources (no API keys required):
  * mempool.space  — per-address Bitcoin balances for curated CEX cold wallets
  * CoinGecko      — public company BTC treasuries + circulating supply
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/bitcoin"
COINGECKO_TREASURY_URL = "https://api.coingecko.com/api/v3/companies/public_treasury/bitcoin"
MEMPOOL_ADDR_URL = "https://mempool.space/api/address/{addr}"

CACHE_TTL = 600  # 10 minutes
REQUEST_TIMEOUT = 15
FALLBACK_CIRCULATING_SUPPLY = 19_800_000.0

CATEGORY_CEX = "Top CEXs"
CATEGORY_WHALE = "Known Institutional/Whale Entities"
CATEGORY_OTHER = "Other On-chain (Retail/Unknown)"

# Curated list of publicly-known CEX cold-wallet addresses. This is a
# best-effort starting point — extend it using labeled addresses from
# BitInfoCharts or similar sources to improve coverage.
CEX_WALLETS: dict[str, list[str]] = {
    "Binance": [
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
        "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h",
        "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",
    ],
    "Bitfinex": [
        "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
    ],
    "Robinhood": [
        "bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2",
    ],
    "Kraken": [
        "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfc27a4",
    ],
    "Bitstamp": [
        "bc1qa5wkgaew2dkv56kfvj49j0av5nml45x9ek9hz6",
    ],
}


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_address_balance(addr: str) -> tuple[float, str | None]:
    """Return (btc_balance, error) for a single on-chain address via mempool.space."""
    try:
        resp = requests.get(MEMPOOL_ADDR_URL.format(addr=addr), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        stats = data.get("chain_stats", {}) or {}
        sats = int(stats.get("funded_txo_sum", 0)) - int(stats.get("spent_txo_sum", 0))
        return sats / 1e8, None
    except Exception as exc:
        return 0.0, str(exc)


def fetch_cex_holdings() -> tuple[pd.DataFrame, list[str]]:
    """Aggregate per-exchange BTC by summing configured cold-wallet addresses."""
    errors: list[str] = []
    rows: list[dict] = []
    for exchange, addrs in CEX_WALLETS.items():
        total = 0.0
        ok_count = 0
        for addr in addrs:
            btc, err = fetch_address_balance(addr)
            if err:
                errors.append(f"{exchange} / {addr[:10]}…: {err}")
                continue
            total += btc
            ok_count += 1
        if total > 0:
            rows.append(
                {
                    "name": exchange,
                    "btc": total,
                    "category": CATEGORY_CEX,
                    "source": f"{ok_count} cold wallet(s)",
                }
            )
    return pd.DataFrame(rows), errors


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_public_treasuries() -> tuple[pd.DataFrame, str | None]:
    """Public-company BTC treasuries from CoinGecko."""
    try:
        resp = requests.get(COINGECKO_TREASURY_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return pd.DataFrame(), str(exc)

    rows: list[dict] = []
    for c in data.get("companies", []) or []:
        holdings = float(c.get("total_holdings") or 0)
        if holdings <= 0:
            continue
        rows.append(
            {
                "name": c.get("name") or c.get("symbol") or "Unknown",
                "btc": holdings,
                "category": CATEGORY_WHALE,
                "source": c.get("symbol") or "public filings",
            }
        )
    return pd.DataFrame(rows), None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_circulating_supply() -> tuple[float, bool]:
    """Return (supply_in_btc, is_live). Falls back to a constant on failure."""
    try:
        resp = requests.get(
            COINGECKO_COIN_URL,
            params={
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return float(resp.json()["market_data"]["circulating_supply"]), True
    except Exception:
        return FALLBACK_CIRCULATING_SUPPLY, False


def build_breakdown(holdings: pd.DataFrame, circulating_supply: float) -> pd.DataFrame:
    if holdings.empty:
        cex_btc = whale_btc = 0.0
    else:
        cex_btc = float(holdings.loc[holdings["category"] == CATEGORY_CEX, "btc"].sum())
        whale_btc = float(holdings.loc[holdings["category"] == CATEGORY_WHALE, "btc"].sum())
    other_btc = max(circulating_supply - cex_btc - whale_btc, 0.0)
    df = pd.DataFrame(
        [
            {"category": CATEGORY_CEX, "btc": cex_btc},
            {"category": CATEGORY_WHALE, "btc": whale_btc},
            {"category": CATEGORY_OTHER, "btc": other_btc},
        ]
    )
    total = df["btc"].sum() or 1.0
    df["pct"] = df["btc"] / total * 100
    return df


def render_donut(breakdown: pd.DataFrame) -> go.Figure:
    colors = {
        CATEGORY_CEX: "#f7931a",
        CATEGORY_WHALE: "#4c78a8",
        CATEGORY_OTHER: "#bab0ac",
    }
    fig = go.Figure(
        go.Pie(
            labels=breakdown["category"],
            values=breakdown["btc"],
            hole=0.55,
            marker=dict(colors=[colors[c] for c in breakdown["category"]]),
            hovertemplate="<b>%{label}</b><br>%{value:,.0f} BTC<br>%{percent}<extra></extra>",
            textinfo="label+percent",
        )
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        margin=dict(t=20, b=20, l=20, r=20),
        height=460,
    )
    return fig


def format_top_table(holdings: pd.DataFrame, circulating_supply: float) -> pd.DataFrame:
    cols = ["Rank", "Entity", "Category", "BTC", "% of Supply", "Source"]
    if holdings.empty:
        return pd.DataFrame(columns=cols)
    top = holdings.sort_values("btc", ascending=False).head(10).copy()
    top["Rank"] = range(1, len(top) + 1)
    top["Entity"] = top["name"]
    top["Category"] = top["category"]
    top["BTC"] = top["btc"].map(lambda x: f"{x:,.0f}")
    top["% of Supply"] = (top["btc"] / circulating_supply * 100).map(lambda x: f"{x:.2f}%")
    top["Source"] = top["source"]
    return top[cols]


def main() -> None:
    st.set_page_config(page_title="BTC Holder Breakdown", layout="wide", page_icon="₿")

    st.title("Bitcoin Holder Breakdown")
    st.caption(
        "Share of circulating BTC held by major CEXs, public-company treasuries, "
        "and everything else. Data: mempool.space + CoinGecko (no API keys)."
    )

    with st.sidebar:
        st.header("Controls")
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Cache TTL: {CACHE_TTL // 60} min")
        st.caption(
            f"Last loaded (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        st.divider()
        st.subheader("Tracked CEX wallets")
        for ex, addrs in CEX_WALLETS.items():
            st.caption(f"**{ex}:** {len(addrs)} address(es)")

    with st.spinner("Fetching on-chain balances..."):
        circulating_supply, supply_is_live = fetch_circulating_supply()
        cex_df, cex_errors = fetch_cex_holdings()
        whale_df, whale_error = fetch_public_treasuries()

    if not supply_is_live:
        st.warning(
            f"CoinGecko request failed — using fallback circulating supply of "
            f"{FALLBACK_CIRCULATING_SUPPLY:,.0f} BTC."
        )
    if whale_error:
        st.warning(f"CoinGecko public-treasury fetch failed: {whale_error}")
    if cex_errors:
        with st.sidebar:
            st.divider()
            st.subheader("Fetch issues")
            for e in cex_errors:
                st.caption(f"• {e}")

    frames = [df for df in (cex_df, whale_df) if not df.empty]
    holdings = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["name", "btc", "category", "source"])
    )

    breakdown = build_breakdown(holdings, circulating_supply)
    cex_btc = float(breakdown.loc[breakdown["category"] == CATEGORY_CEX, "btc"].iloc[0])
    whale_btc = float(breakdown.loc[breakdown["category"] == CATEGORY_WHALE, "btc"].iloc[0])

    c1, c2, c3 = st.columns(3)
    c1.metric("Circulating supply", f"{circulating_supply:,.0f} BTC")
    c2.metric(
        "On top CEXs (tracked)",
        f"{cex_btc:,.0f} BTC",
        f"{cex_btc / circulating_supply * 100:.2f}%",
    )
    c3.metric(
        "Public company treasuries",
        f"{whale_btc:,.0f} BTC",
        f"{whale_btc / circulating_supply * 100:.2f}%",
    )

    st.subheader("Supply distribution")
    st.plotly_chart(render_donut(breakdown), use_container_width=True)

    st.subheader("Top 10 tracked entities by BTC held")
    st.dataframe(
        format_top_table(holdings, circulating_supply),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Methodology & caveats"):
        st.markdown(
            """
**CEX holdings** are summed from a curated list of publicly-known cold-wallet
addresses via `mempool.space`. This undercounts — real CEX reserves are spread
across hundreds of wallets. Extend `CEX_WALLETS` in `main.py` (e.g. using
labeled addresses from BitInfoCharts) to improve coverage.

**Public-company treasuries** come from CoinGecko's
`/companies/public_treasury/bitcoin` endpoint (MicroStrategy, Tesla, Marathon
Digital, Block, etc.). ETFs and private funds are **not** included here.

**"Other On-chain"** is computed as circulating supply minus everything
tracked above, so it absorbs retail holders, lost coins, Satoshi's stash,
spot ETFs, miners, private whales, and any CEX wallets we haven't catalogued.
"""
        )

    st.caption("Sources: mempool.space REST API · CoinGecko public API. No keys required.")


if __name__ == "__main__":
    main()
