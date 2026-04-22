"""Streamlit dashboard: live breakdown of BTC circulating supply by holder type."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ARKHAM_BASE = "https://api.arkm.com"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/bitcoin"
CACHE_TTL = 600  # 10 minutes
REQUEST_TIMEOUT = 15
FALLBACK_CIRCULATING_SUPPLY = 19_800_000.0

CATEGORY_CEX = "Top CEXs"
CATEGORY_WHALE = "Known Institutional/Whale Entities"
CATEGORY_OTHER = "Other On-chain (Retail/Unknown)"

CEX_ENTITIES = [
    "binance",
    "coinbase",
    "kraken",
    "bitfinex",
    "okx",
    "bybit",
    "gemini",
    "bitstamp",
    "robinhood",
    "crypto-com",
]

WHALE_ENTITIES = [
    "microstrategy",
    "blackrock",
    "grayscale",
    "fidelity",
    "tesla",
    "ark-invest",
    "tether",
]


def _arkham_headers(api_key: str) -> dict[str, str]:
    return {"API-Key": api_key, "Accept": "application/json"}


def _extract_btc_balance(payload: dict, entity_id: str) -> tuple[float, float, str, str]:
    """Return (btc_amount, usd_value, entity_name, entity_type) from Arkham payload."""
    balances = payload.get("balances", {}) or {}
    entities = payload.get("entities", {}) or {}

    entity_meta = entities.get(entity_id, {}) or {}
    name = entity_meta.get("name") or entity_id.replace("-", " ").title()
    ent_type = entity_meta.get("type") or ""

    entity_balances = balances.get(entity_id)
    if entity_balances is None:
        # Some responses key balances differently; fall back to first value.
        if balances:
            entity_balances = next(iter(balances.values()))
        else:
            entity_balances = []

    btc_amount = 0.0
    usd_value = 0.0
    if isinstance(entity_balances, list):
        for token in entity_balances:
            if not isinstance(token, dict):
                continue
            symbol = (token.get("symbol") or token.get("tokenSymbol") or "").upper()
            chain = (token.get("chain") or token.get("chainName") or "").lower()
            if symbol == "BTC" or chain == "bitcoin":
                btc_amount = float(token.get("balance") or token.get("amount") or 0) or btc_amount
                usd_value = float(token.get("usd") or token.get("usdValue") or 0) or usd_value
                break

    return btc_amount, usd_value, name, ent_type


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_circulating_supply() -> tuple[float, bool]:
    """Return (supply_in_btc, is_live). Falls back to a constant on failure."""
    try:
        resp = requests.get(
            COINGECKO_URL,
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
        data = resp.json()
        supply = float(data["market_data"]["circulating_supply"])
        return supply, True
    except Exception:
        return FALLBACK_CIRCULATING_SUPPLY, False


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_entity_balance(entity_id: str, api_key: str) -> dict | None:
    """Fetch a single entity's BTC balance. Returns None on error / missing data."""
    url = f"{ARKHAM_BASE}/balances/entity/{entity_id}"
    try:
        resp = requests.get(
            url,
            headers=_arkham_headers(api_key),
            params={"chains": "bitcoin"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"id": entity_id, "error": str(exc)}

    btc, usd, name, ent_type = _extract_btc_balance(payload, entity_id)
    if btc <= 0:
        return None
    return {
        "id": entity_id,
        "name": name,
        "type": ent_type,
        "btc": btc,
        "usd": usd,
    }


def fetch_all_holdings(api_key: str) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for entity_id in CEX_ENTITIES:
        result = fetch_entity_balance(entity_id, api_key)
        if result is None:
            errors.append(f"{entity_id}: no BTC balance returned")
            continue
        if "error" in result:
            errors.append(f"{entity_id}: {result['error']}")
            continue
        rows.append({**result, "category": CATEGORY_CEX})
    for entity_id in WHALE_ENTITIES:
        result = fetch_entity_balance(entity_id, api_key)
        if result is None:
            errors.append(f"{entity_id}: no BTC balance returned")
            continue
        if "error" in result:
            errors.append(f"{entity_id}: {result['error']}")
            continue
        rows.append({**result, "category": CATEGORY_WHALE})

    df = pd.DataFrame(rows, columns=["id", "name", "type", "btc", "usd", "category"])
    if not df.empty:
        df = df.sort_values("btc", ascending=False).reset_index(drop=True)
    return df, errors


def build_breakdown(holdings: pd.DataFrame, circulating_supply: float) -> pd.DataFrame:
    cex_btc = float(holdings.loc[holdings["category"] == CATEGORY_CEX, "btc"].sum()) if not holdings.empty else 0.0
    whale_btc = float(holdings.loc[holdings["category"] == CATEGORY_WHALE, "btc"].sum()) if not holdings.empty else 0.0
    tracked = cex_btc + whale_btc
    other_btc = max(circulating_supply - tracked, 0.0)

    rows = [
        {"category": CATEGORY_CEX, "btc": cex_btc},
        {"category": CATEGORY_WHALE, "btc": whale_btc},
        {"category": CATEGORY_OTHER, "btc": other_btc},
    ]
    df = pd.DataFrame(rows)
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
    if holdings.empty:
        return pd.DataFrame(columns=["Rank", "Entity", "Category", "BTC", "USD Value", "% of Supply"])
    top = holdings.head(10).copy()
    top["Rank"] = range(1, len(top) + 1)
    top["Entity"] = top["name"]
    top["Category"] = top["category"]
    top["BTC"] = top["btc"].map(lambda x: f"{x:,.0f}")
    top["USD Value"] = top["usd"].map(lambda x: f"${x:,.0f}" if x else "—")
    top["% of Supply"] = (top["btc"] / circulating_supply * 100).map(lambda x: f"{x:.2f}%")
    return top[["Rank", "Entity", "Category", "BTC", "USD Value", "% of Supply"]]


def main() -> None:
    st.set_page_config(page_title="BTC Holder Breakdown", layout="wide", page_icon="₿")

    api_key = os.getenv("ARKHAM_API_KEY")
    if not api_key:
        st.error(
            "ARKHAM_API_KEY is not set. Copy .env.example to .env and add your key, "
            "then restart the app."
        )
        st.stop()

    st.title("Bitcoin Holder Breakdown")
    st.caption(
        "Share of circulating BTC custodied by major CEXs, tracked institutions, "
        "and everything else. Data: Arkham Intelligence + CoinGecko."
    )

    with st.sidebar:
        st.header("Controls")
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Cache TTL: {CACHE_TTL // 60} min")
        st.caption(f"Last loaded (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        st.divider()
        st.subheader("Tracked entities")
        st.write(f"**CEXs ({len(CEX_ENTITIES)}):** " + ", ".join(CEX_ENTITIES))
        st.write(f"**Institutions/Whales ({len(WHALE_ENTITIES)}):** " + ", ".join(WHALE_ENTITIES))

    with st.spinner("Fetching on-chain balances..."):
        circulating_supply, supply_is_live = fetch_circulating_supply()
        holdings, errors = fetch_all_holdings(api_key)

    if not supply_is_live:
        st.warning(
            f"CoinGecko request failed — using fallback circulating supply of "
            f"{FALLBACK_CIRCULATING_SUPPLY:,.0f} BTC."
        )
    if errors:
        with st.sidebar:
            st.divider()
            st.subheader("Fetch issues")
            for e in errors:
                st.caption(f"• {e}")

    breakdown = build_breakdown(holdings, circulating_supply)
    cex_btc = float(breakdown.loc[breakdown["category"] == CATEGORY_CEX, "btc"].iloc[0])
    whale_btc = float(breakdown.loc[breakdown["category"] == CATEGORY_WHALE, "btc"].iloc[0])

    col1, col2, col3 = st.columns(3)
    col1.metric("Circulating supply", f"{circulating_supply:,.0f} BTC")
    col2.metric("On top CEXs", f"{cex_btc:,.0f} BTC", f"{cex_btc / circulating_supply * 100:.2f}%")
    col3.metric(
        "Institutions / whales",
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

    st.caption(
        "Sources: balances from Arkham Intelligence (`/balances/entity/{entity}`); "
        "circulating supply from CoinGecko. The 'Other' bucket is the residual "
        "after subtracting tracked entity balances from circulating supply."
    )


if __name__ == "__main__":
    main()
