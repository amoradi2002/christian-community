"""
Finviz data provider - stock screener, fundamentals, insider trades, and news.

Uses the finvizfinance package for data access.
Free tier: delayed data, basic screener.
Finviz Elite: real-time data, advanced screener, backtesting.
"""

import json
from datetime import datetime
from dataclasses import dataclass, field

from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.technical import Technical
from finvizfinance.insider import Insider
from finvizfinance.news import News

from bot.db.database import get_connection


@dataclass
class StockFundamentals:
    """Fundamental data for a stock from Finviz."""
    symbol: str
    company: str = ""
    sector: str = ""
    industry: str = ""
    country: str = ""
    market_cap: str = ""
    pe: float = 0.0
    forward_pe: float = 0.0
    peg: float = 0.0
    ps: float = 0.0
    pb: float = 0.0
    dividend_yield: str = ""
    eps: float = 0.0
    eps_next_y: float = 0.0
    eps_growth_this_y: str = ""
    eps_growth_next_y: str = ""
    revenue_growth: str = ""
    profit_margin: str = ""
    roe: str = ""
    roa: str = ""
    debt_equity: float = 0.0
    short_float: str = ""
    short_ratio: float = 0.0
    analyst_recommendation: float = 0.0  # 1=Strong Buy, 5=Sell
    target_price: float = 0.0
    rsi_14: float = 0.0
    beta: float = 0.0
    sma_20: str = ""
    sma_50: str = ""
    sma_200: str = ""
    relative_volume: float = 0.0
    avg_volume: str = ""
    earnings_date: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class InsiderTrade:
    """Insider trading activity."""
    ticker: str = ""
    owner: str = ""
    relationship: str = ""
    date: str = ""
    transaction: str = ""
    cost: float = 0.0
    shares: int = 0
    value: float = 0.0
    shares_total: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def get_stock_fundamentals(symbol: str) -> StockFundamentals:
    """
    Get comprehensive fundamentals for a stock from Finviz.
    Includes valuation, growth, profitability, analyst ratings.
    """
    try:
        stock = finvizfinance(symbol)
        fundament = stock.ticker_fundament()

        def safe_float(val, default=0.0):
            if val is None or val == "-" or val == "":
                return default
            try:
                return float(str(val).replace("%", "").replace(",", ""))
            except (ValueError, TypeError):
                return default

        return StockFundamentals(
            symbol=symbol,
            company=fundament.get("Company", ""),
            sector=fundament.get("Sector", ""),
            industry=fundament.get("Industry", ""),
            country=fundament.get("Country", ""),
            market_cap=fundament.get("Market Cap", ""),
            pe=safe_float(fundament.get("P/E")),
            forward_pe=safe_float(fundament.get("Forward P/E")),
            peg=safe_float(fundament.get("PEG")),
            ps=safe_float(fundament.get("P/S")),
            pb=safe_float(fundament.get("P/B")),
            dividend_yield=fundament.get("Dividend %", ""),
            eps=safe_float(fundament.get("EPS (ttm)")),
            eps_next_y=safe_float(fundament.get("EPS next Y")),
            eps_growth_this_y=fundament.get("EPS this Y", ""),
            eps_growth_next_y=fundament.get("EPS next Y", ""),
            revenue_growth=fundament.get("Sales Q/Q", ""),
            profit_margin=fundament.get("Profit Margin", ""),
            roe=fundament.get("ROE", ""),
            roa=fundament.get("ROA", ""),
            debt_equity=safe_float(fundament.get("Debt/Eq")),
            short_float=fundament.get("Short Float", ""),
            short_ratio=safe_float(fundament.get("Short Ratio")),
            analyst_recommendation=safe_float(fundament.get("Recom")),
            target_price=safe_float(fundament.get("Target Price")),
            rsi_14=safe_float(fundament.get("RSI (14)")),
            beta=safe_float(fundament.get("Beta")),
            sma_20=fundament.get("SMA20", ""),
            sma_50=fundament.get("SMA50", ""),
            sma_200=fundament.get("SMA200", ""),
            relative_volume=safe_float(fundament.get("Rel Volume")),
            avg_volume=fundament.get("Avg Volume", ""),
            earnings_date=fundament.get("Earnings", ""),
        )
    except Exception as e:
        print(f"Finviz fundamentals error for {symbol}: {e}")
        return StockFundamentals(symbol=symbol)


def get_stock_news(symbol: str) -> list[dict]:
    """Get latest news headlines for a stock from Finviz."""
    try:
        stock = finvizfinance(symbol)
        news_df = stock.ticker_news()

        if news_df is None or news_df.empty:
            return []

        news = []
        for _, row in news_df.head(20).iterrows():
            news.append({
                "date": str(row.get("Date", "")),
                "title": row.get("Title", ""),
                "source": row.get("Source", ""),
                "link": row.get("Link", ""),
            })
        return news
    except Exception as e:
        print(f"Finviz news error for {symbol}: {e}")
        return []


def get_insider_trades(symbol: str | None = None) -> list[InsiderTrade]:
    """
    Get recent insider trading activity.
    If symbol is provided, filter for that stock.
    """
    try:
        insider = Insider()
        df = insider.get_insider()

        if df is None or df.empty:
            return []

        trades = []
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", ""))
            if symbol and ticker.upper() != symbol.upper():
                continue

            trade = InsiderTrade(
                ticker=ticker,
                owner=str(row.get("Owner", "")),
                relationship=str(row.get("Relationship", "")),
                date=str(row.get("Date", "")),
                transaction=str(row.get("Transaction", "")),
                cost=_safe_float(row.get("Cost")),
                shares=_safe_int(row.get("#Shares")),
                value=_safe_float(row.get("Value ($)")),
                shares_total=_safe_int(row.get("#Shares Total")),
            )
            trades.append(trade)

        return trades[:50]
    except Exception as e:
        print(f"Finviz insider trades error: {e}")
        return []


def screen_stocks(filters: dict | None = None, signal: str = "") -> list[dict]:
    """
    Run Finviz stock screener with filters.

    Common filters:
        {"Market Cap.": "Large ($10bln to $200bln)"}
        {"RSI (14)": "Oversold (30)"}
        {"Average Volume": "Over 1M"}
        {"Change": "Up 5%"}

    Common signals:
        "top_gainers", "top_losers", "new_high", "new_low",
        "most_volatile", "most_active", "unusual_volume",
        "overbought", "oversold", "upgrades", "downgrades"
    """
    try:
        overview = Overview()

        if filters:
            overview.set_filter(filters_dict=filters)

        if signal:
            overview.set_filter(signal=signal)

        df = overview.screener_view()

        if df is None or df.empty:
            return []

        results = []
        for _, row in df.head(50).iterrows():
            results.append({
                "ticker": row.get("Ticker", ""),
                "company": row.get("Company", ""),
                "sector": row.get("Sector", ""),
                "industry": row.get("Industry", ""),
                "market_cap": row.get("Market Cap", ""),
                "pe": row.get("P/E", ""),
                "price": row.get("Price", ""),
                "change": row.get("Change", ""),
                "volume": row.get("Volume", ""),
            })
        return results
    except Exception as e:
        print(f"Finviz screener error: {e}")
        return []


def screen_technical(signal: str = "oversold") -> list[dict]:
    """
    Run technical screener.
    Signals: "oversold", "overbought", "most_volatile", "most_active",
             "unusual_volume", "top_gainers", "top_losers"
    """
    try:
        tech = Technical()
        tech.set_filter(signal=signal)
        df = tech.screener_view()

        if df is None or df.empty:
            return []

        results = []
        for _, row in df.head(30).iterrows():
            results.append({
                "ticker": row.get("Ticker", ""),
                "price": row.get("Price", ""),
                "change": row.get("Change", ""),
                "volume": row.get("Volume", ""),
                "rsi": row.get("RSI", ""),
                "sma_20": row.get("20-Day Simple Moving Average", ""),
                "sma_50": row.get("50-Day Simple Moving Average", ""),
                "sma_200": row.get("200-Day Simple Moving Average", ""),
            })
        return results
    except Exception as e:
        print(f"Finviz technical screener error: {e}")
        return []


def get_market_news() -> list[dict]:
    """Get general market news from Finviz."""
    try:
        news = News()
        all_news = news.get_news()

        results = []
        if "news" in all_news:
            for _, row in all_news["news"].head(20).iterrows():
                results.append({
                    "date": str(row.get("Date", "")),
                    "title": row.get("Title", ""),
                    "source": row.get("Source", ""),
                    "link": row.get("Link", ""),
                })
        return results
    except Exception as e:
        print(f"Finviz market news error: {e}")
        return []


def cache_fundamentals(symbol: str, fundamentals: StockFundamentals):
    """Cache fundamentals to database for quick access."""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO fundamentals_cache
               (symbol, data_json, updated_at)
               VALUES (?, ?, ?)""",
            (symbol, json.dumps(fundamentals.to_dict()), datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _safe_float(val, default=0.0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return default
