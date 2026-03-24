"""
Unusual Whales data provider - options flow, dark pool, whale alerts, congress trades.

Requires an Unusual Whales API token (available with paid subscription).
Get your token at: https://unusualwhales.com/api

Provides:
- Real-time options flow (large/unusual trades)
- Dark pool activity
- Congressional trading data
- Market-wide flow sentiment
"""

import os
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import requests

from bot.db.database import get_connection


BASE_URL = "https://api.unusualwhales.com/api"

_HEADERS_TEMPLATE = {
    "Accept": "application/json",
    "User-Agent": "AI-Trading-Bot/1.0",
}


@dataclass
class OptionsFlow:
    """A single unusual options flow entry."""
    id: str = ""
    ticker: str = ""
    date: str = ""
    time: str = ""
    sentiment: str = ""       # "bullish", "bearish", "neutral"
    option_type: str = ""     # "call" or "put"
    strike: float = 0.0
    expiration: str = ""
    premium: float = 0.0      # Total premium paid
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: float = 0.0
    underlying_price: float = 0.0
    is_sweep: bool = False
    is_block: bool = False
    is_split: bool = False

    @property
    def size_label(self) -> str:
        if self.premium >= 1_000_000:
            return "WHALE"
        elif self.premium >= 500_000:
            return "LARGE"
        elif self.premium >= 100_000:
            return "NOTABLE"
        return "NORMAL"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["size_label"] = self.size_label
        return d


@dataclass
class DarkPoolTrade:
    """A dark pool trade entry."""
    ticker: str = ""
    date: str = ""
    price: float = 0.0
    size: int = 0
    notional_value: float = 0.0
    exchange: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class CongressTrade:
    """A congressional trading disclosure."""
    politician: str = ""
    party: str = ""
    chamber: str = ""       # "Senate" or "House"
    ticker: str = ""
    transaction: str = ""   # "Purchase" or "Sale"
    amount_range: str = ""  # e.g. "$1,001 - $15,000"
    date_disclosed: str = ""
    date_traded: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _get_headers() -> dict:
    """Build request headers with API token."""
    token = os.getenv("UNUSUAL_WHALES_TOKEN")
    if not token:
        raise ValueError(
            "UNUSUAL_WHALES_TOKEN not set. Get your API token at https://unusualwhales.com/api"
        )
    headers = _HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_get(endpoint: str, params: dict | None = None) -> dict | list | None:
    """Make authenticated GET request to Unusual Whales API."""
    try:
        headers = _get_headers()
        resp = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=15,
        )
        if resp.status_code == 401:
            print("Unusual Whales: Invalid or expired API token")
            return None
        if resp.status_code == 429:
            print("Unusual Whales: Rate limited, try again later")
            return None
        if resp.status_code != 200:
            print(f"Unusual Whales API error {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    except requests.RequestException as e:
        print(f"Unusual Whales request error: {e}")
        return None


# --- Options Flow ---

def get_options_flow(
    ticker: str | None = None,
    min_premium: int = 100000,
    limit: int = 50,
) -> list[OptionsFlow]:
    """
    Get unusual options flow.

    Args:
        ticker: Filter by specific stock (None = all tickers)
        min_premium: Minimum premium in dollars to filter (default $100k)
        limit: Max results to return
    """
    params = {"limit": limit}
    if ticker:
        params["ticker"] = ticker.upper()

    data = _api_get("stock/flow", params)
    if not data:
        # Try alternative endpoint
        data = _api_get("options/flow", params)

    if not data:
        return []

    flows_data = data.get("data", data) if isinstance(data, dict) else data

    flows = []
    for item in flows_data:
        if isinstance(item, dict):
            flow = OptionsFlow(
                id=str(item.get("id", "")),
                ticker=item.get("ticker", item.get("underlying_symbol", "")),
                date=item.get("date", item.get("executed_at", ""))[:10] if item.get("date") or item.get("executed_at") else "",
                time=item.get("time", item.get("executed_at", ""))[11:16] if item.get("executed_at") else "",
                sentiment=item.get("sentiment", item.get("put_call_sentiment", "")),
                option_type=item.get("option_type", item.get("put_call", "")).lower(),
                strike=_safe_float(item.get("strike", item.get("strike_price"))),
                expiration=item.get("expiration", item.get("expires_at", ""))[:10] if item.get("expiration") or item.get("expires_at") else "",
                premium=_safe_float(item.get("premium", item.get("total_premium"))),
                volume=_safe_int(item.get("volume")),
                open_interest=_safe_int(item.get("open_interest")),
                implied_volatility=_safe_float(item.get("implied_volatility", item.get("iv"))),
                delta=_safe_float(item.get("delta")),
                underlying_price=_safe_float(item.get("underlying_price", item.get("stock_price"))),
                is_sweep=bool(item.get("is_sweep", False)),
                is_block=bool(item.get("is_block", False)),
                is_split=bool(item.get("is_split", False)),
            )

            if flow.premium >= min_premium and flow.ticker:
                flows.append(flow)

    # Sort by premium descending
    flows.sort(key=lambda f: f.premium, reverse=True)
    _cache_flow(flows)
    return flows[:limit]


def get_flow_alerts(
    min_premium: int = 500000,
    sentiment: str | None = None,
) -> list[OptionsFlow]:
    """
    Get whale-level options flow alerts (>$500k premium).
    These are the big money moves to watch.
    """
    flows = get_options_flow(min_premium=min_premium, limit=100)

    if sentiment:
        flows = [f for f in flows if f.sentiment.lower() == sentiment.lower()]

    return flows


# --- Dark Pool ---

def get_dark_pool(ticker: str | None = None, limit: int = 50) -> list[DarkPoolTrade]:
    """Get recent dark pool trades."""
    params = {"limit": limit}
    if ticker:
        params["ticker"] = ticker.upper()

    data = _api_get("darkpool/recent", params)
    if not data:
        data = _api_get("stock/dark-pool", params)

    if not data:
        return []

    trades_data = data.get("data", data) if isinstance(data, dict) else data
    trades = []

    for item in trades_data:
        if isinstance(item, dict):
            trade = DarkPoolTrade(
                ticker=item.get("ticker", item.get("symbol", "")),
                date=str(item.get("date", item.get("executed_at", "")))[:10],
                price=_safe_float(item.get("price")),
                size=_safe_int(item.get("size", item.get("volume"))),
                notional_value=_safe_float(item.get("notional_value", item.get("total_value"))),
                exchange=item.get("exchange", item.get("venue", "")),
            )
            if trade.ticker:
                trades.append(trade)

    return trades[:limit]


# --- Congress Trading ---

def get_congress_trades(
    ticker: str | None = None,
    party: str | None = None,
    limit: int = 50,
) -> list[CongressTrade]:
    """
    Get congressional trading disclosures.

    Args:
        ticker: Filter by stock
        party: Filter by "Democrat" or "Republican"
        limit: Max results
    """
    params = {"limit": limit}
    if ticker:
        params["ticker"] = ticker.upper()

    data = _api_get("congress/trades", params)
    if not data:
        data = _api_get("politician/trades", params)

    if not data:
        return []

    trades_data = data.get("data", data) if isinstance(data, dict) else data
    trades = []

    for item in trades_data:
        if isinstance(item, dict):
            trade = CongressTrade(
                politician=item.get("politician", item.get("representative", "")),
                party=item.get("party", ""),
                chamber=item.get("chamber", item.get("house", "")),
                ticker=item.get("ticker", item.get("symbol", "")),
                transaction=item.get("transaction", item.get("type", "")),
                amount_range=item.get("amount", item.get("range", "")),
                date_disclosed=str(item.get("disclosure_date", item.get("date_disclosed", "")))[:10],
                date_traded=str(item.get("transaction_date", item.get("date_traded", "")))[:10],
            )

            if party and trade.party.lower() != party.lower():
                continue
            if trade.ticker:
                trades.append(trade)

    return trades[:limit]


# --- Market Sentiment ---

def get_flow_sentiment() -> dict:
    """
    Get market-wide options flow sentiment.
    Shows overall put/call ratio and flow direction.
    """
    data = _api_get("market/sentiment")
    if not data:
        data = _api_get("flow/sentiment")

    if not data:
        return {"error": "Could not fetch sentiment data"}

    sentiment = data.get("data", data) if isinstance(data, dict) else {}
    return {
        "overall_sentiment": sentiment.get("sentiment", "neutral"),
        "put_call_ratio": _safe_float(sentiment.get("put_call_ratio", sentiment.get("pcr")), 1.0),
        "bullish_flow_pct": _safe_float(sentiment.get("bullish_pct", sentiment.get("bullish_percentage"))),
        "bearish_flow_pct": _safe_float(sentiment.get("bearish_pct", sentiment.get("bearish_percentage"))),
        "total_premium": _safe_float(sentiment.get("total_premium")),
        "top_bullish": sentiment.get("top_bullish_tickers", []),
        "top_bearish": sentiment.get("top_bearish_tickers", []),
    }


def get_ticker_sentiment(ticker: str) -> dict:
    """Get options flow sentiment for a specific ticker."""
    data = _api_get(f"stock/{ticker.upper()}/flow-sentiment")
    if not data:
        # Compute from recent flow
        flows = get_options_flow(ticker=ticker, min_premium=50000, limit=50)
        if not flows:
            return {"ticker": ticker, "sentiment": "neutral", "flow_count": 0}

        bullish = sum(1 for f in flows if f.sentiment.lower() == "bullish")
        bearish = sum(1 for f in flows if f.sentiment.lower() == "bearish")
        total = len(flows)
        total_premium = sum(f.premium for f in flows)

        return {
            "ticker": ticker.upper(),
            "sentiment": "bullish" if bullish > bearish else "bearish" if bearish > bullish else "neutral",
            "bullish_count": bullish,
            "bearish_count": bearish,
            "flow_count": total,
            "total_premium": total_premium,
            "avg_premium": total_premium / total if total else 0,
        }

    return data.get("data", data) if isinstance(data, dict) else data


# --- Caching ---

def _cache_flow(flows: list[OptionsFlow]):
    """Cache flow data to database."""
    try:
        conn = get_connection()
        for flow in flows[:100]:
            conn.execute(
                """INSERT OR REPLACE INTO flow_cache
                   (flow_id, ticker, data_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (flow.id or f"{flow.ticker}_{flow.date}_{flow.strike}",
                 flow.ticker,
                 json.dumps(flow.to_dict()),
                 datetime.now().isoformat()),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_cached_flow(ticker: str | None = None, limit: int = 50) -> list[OptionsFlow]:
    """Get cached flow data."""
    try:
        conn = get_connection()
        if ticker:
            rows = conn.execute(
                "SELECT data_json FROM flow_cache WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
                (ticker.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data_json FROM flow_cache ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()

        return [OptionsFlow(**json.loads(r["data_json"])) for r in rows if r["data_json"]]
    except Exception:
        return []


def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    if val is None:
        return default
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default
