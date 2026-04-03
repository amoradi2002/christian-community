"""
Trading Bot Tool Definitions — callable functions the AI agent can use.

Each tool has:
  - name: unique identifier
  - description: what it does (shown to the AI)
  - parameters: JSON schema for inputs
  - handler: Python function that executes it
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Tool Registry ────────────────────────────────────────────

TOOLS = []
_HANDLERS = {}


def tool(name: str, description: str, parameters: dict):
    """Decorator to register a function as an agent tool."""
    def decorator(func):
        TOOLS.append({
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": parameters.get("properties", {}),
                "required": parameters.get("required", []),
            },
        })
        _HANDLERS[name] = func
        return func
    return decorator


def execute_tool(name: str, args: dict) -> str:
    """Execute a registered tool by name."""
    handler = _HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = handler(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return json.dumps({"error": str(e)})


# ─── Market Data Tools ────────────────────────────────────────

@tool(
    name="get_price",
    description="Get the current price and key stats for a stock symbol. Returns last price, change %, volume, 52-week range.",
    parameters={
        "properties": {
            "symbol": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, SPY)"},
        },
        "required": ["symbol"],
    },
)
def get_price(symbol: str) -> dict:
    from bot.config.settings import CONFIG
    symbol = symbol.upper().strip()
    provider = CONFIG.get("data", {}).get("provider", "yfinance")

    if provider == "alpaca":
        from bot.data.alpaca_provider import fetch_alpaca_bars
        candles = fetch_alpaca_bars(symbol, interval="1d", days=5)
    else:
        from bot.data.fetcher import fetch_market_data
        candles = fetch_market_data(symbol, period="5d", interval="1d")

    if not candles or len(candles) < 2:
        return {"error": f"No data for {symbol}"}

    latest = candles[-1]
    prev = candles[-2]
    change_pct = ((latest.close - prev.close) / prev.close) * 100

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    return {
        "symbol": symbol,
        "price": round(latest.close, 2),
        "change_pct": round(change_pct, 2),
        "open": round(latest.open, 2),
        "high": round(latest.high, 2),
        "low": round(latest.low, 2),
        "volume": latest.volume,
        "5d_high": round(max(highs), 2),
        "5d_low": round(min(lows), 2),
    }


@tool(
    name="scan_market",
    description="Run a full market scan across the watchlist. Returns signals with entry, stop, target, confidence. Use style='day' for day trades, 'swing' for swing trades, or 'all' for everything.",
    parameters={
        "properties": {
            "style": {"type": "string", "description": "Scan style: 'all', 'day', or 'swing'", "default": "all"},
        },
        "required": [],
    },
)
def scan_market(style: str = "all") -> dict:
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()

    if style == "day":
        signals = analyzer.run_day_scan()
    elif style == "swing":
        signals = analyzer.run_swing_scan()
    else:
        signals = analyzer.run_scan()

    if not signals:
        return {"signals": [], "message": "No signals found right now."}

    results = []
    for sig in signals[:10]:
        results.append({
            "symbol": sig.symbol,
            "action": sig.action,
            "strategy": sig.strategy_name,
            "confidence": round(sig.confidence, 2),
            "entry": round(sig.entry_price, 2) if sig.entry_price else None,
            "stop": round(sig.stop_loss, 2) if sig.stop_loss else None,
            "target": round(sig.target_price, 2) if sig.target_price else None,
            "risk_reward": round(sig.risk_reward, 2) if sig.risk_reward else None,
        })

    return {"signals": results, "count": len(signals)}


@tool(
    name="check_sentiment",
    description="Analyze news sentiment for a stock. Returns overall sentiment (bullish/bearish/neutral), score, and top headlines.",
    parameters={
        "properties": {
            "symbol": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["symbol"],
    },
)
def check_sentiment(symbol: str) -> dict:
    from bot.engine.news_sentiment import fetch_news_sentiment
    symbol = symbol.upper().strip()
    result = fetch_news_sentiment(symbol)
    headlines = []
    for h in result.get("headlines", [])[:8]:
        headlines.append({
            "headline": h["headline"][:120],
            "score": round(h["score"], 3),
        })
    return {
        "symbol": symbol,
        "overall": result.get("overall_label", "neutral"),
        "score": round(result.get("overall_score", 0), 3),
        "recommendation": result.get("recommendation", ""),
        "headline_count": len(result.get("headlines", [])),
        "top_headlines": headlines,
    }


@tool(
    name="check_regime",
    description="Detect the current market regime (bull trend, bear trend, volatile, ranging, crash, etc). Shows what strategies work best right now and how to adjust position sizing.",
    parameters={"properties": {}, "required": []},
)
def check_regime() -> dict:
    from bot.engine.regime import detect_market_regime
    analysis = detect_market_regime()
    return {
        "regime": analysis.regime.value,
        "confidence": round(analysis.confidence, 2),
        "trend_strength": round(analysis.trend_strength, 2),
        "volatility_percentile": round(analysis.volatility_percentile, 1),
        "risk_multiplier": round(analysis.risk_adjustment, 2),
        "description": analysis.description,
        "recommended_strategies": analysis.recommended_strategies,
    }


@tool(
    name="run_intelligence",
    description="Run the intelligence scanner — whale flow, earnings calendar, insider buys, unusual volume, dark pool. Returns actionable alerts.",
    parameters={"properties": {}, "required": []},
)
def run_intelligence() -> dict:
    from bot.engine.intelligence_scanner import run_intelligence_scan
    alerts = run_intelligence_scan()
    if not alerts:
        return {"alerts": [], "message": "No intelligence alerts right now."}
    results = []
    for a in alerts[:15]:
        results.append({
            "type": a.get("type", ""),
            "message": a.get("message", ""),
            "watchlist": a.get("in_watchlist", False),
        })
    return {"alerts": results, "count": len(alerts)}


@tool(
    name="run_backtest",
    description="Backtest a strategy on a symbol to see historical performance. Returns win rate, return %, Sharpe ratio, max drawdown, and trade count.",
    parameters={
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol to backtest on (e.g. SPY, AAPL)"},
            "strategy_name": {"type": "string", "description": "Strategy name to test. Leave empty to test all strategies.", "default": ""},
        },
        "required": ["symbol"],
    },
)
def run_backtest(symbol: str, strategy_name: str = "") -> dict:
    from bot.backtest.engine import run_backtest as _run_backtest
    from bot.strategies.registry import StrategyRegistry

    symbol = symbol.upper().strip()
    registry = StrategyRegistry()
    registry.load_all()

    strategies = registry.get_all()
    if strategy_name:
        strategies = [s for s in strategies if strategy_name.lower() in s.name.lower()]
        if not strategies:
            return {"error": f"No strategy matching '{strategy_name}'"}

    results = []
    for strategy in strategies[:5]:
        try:
            result = _run_backtest(strategy, symbol)
            if result and result.get("total_trades", 0) > 0:
                results.append({
                    "strategy": strategy.name,
                    "symbol": symbol,
                    "total_trades": result["total_trades"],
                    "win_rate": round(result.get("win_rate", 0), 1),
                    "total_return_pct": round(result.get("total_return_pct", 0), 2),
                    "sharpe_ratio": round(result.get("sharpe_ratio", 0), 2),
                    "max_drawdown_pct": round(result.get("max_drawdown_pct", 0), 2),
                })
        except Exception as e:
            logger.error("Backtest error %s on %s: %s", strategy.name, symbol, e)

    if not results:
        return {"message": f"No trades generated for {symbol}. Try a different symbol or longer history."}

    return {"results": results, "symbol": symbol}


# ─── Knowledge Base Tools ─────────────────────────────────────

@tool(
    name="search_knowledge",
    description="Search the trading knowledge base for rules, strategies, and insights. Use this to find what the bot has learned about a topic.",
    parameters={
        "properties": {
            "query": {"type": "string", "description": "Search query (e.g. 'RSI oversold bounce', 'risk management', 'MACD crossover')"},
        },
        "required": ["query"],
    },
)
def search_knowledge(query: str) -> dict:
    from bot.learning.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    results = kb.search_knowledge(query, limit=5)
    if not results:
        return {"results": [], "message": f"No knowledge found for '{query}'. Ingest more content to build the knowledge base."}
    entries = []
    for r in results:
        entries.append({
            "title": r["title"],
            "source": r["source_type"],
            "confidence": r["confidence"],
            "strategies": r.get("strategies_extracted", []),
            "indicators": r.get("indicators_mentioned", []),
            "rules": r.get("key_rules", [])[:5],
        })
    return {"results": entries, "total": len(results)}


@tool(
    name="get_best_rules",
    description="Get the highest-confidence trading rules the bot has learned. These are validated rules from backtests, mentorships, and articles.",
    parameters={
        "properties": {
            "category": {"type": "string", "description": "Filter by category: entry_rules, exit_rules, risk_rules, psychology, or leave empty for all", "default": ""},
        },
        "required": [],
    },
)
def get_best_rules(category: str = "") -> dict:
    from bot.learning.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    if category:
        rules = kb.get_rules_by_category(category, limit=10)
    else:
        rules = kb.get_best_rules(min_confidence=0.5, limit=10)
    if not rules:
        return {"rules": [], "message": "No rules in knowledge base yet. Ingest content to build rules."}
    entries = []
    for r in rules:
        entries.append({
            "rule": r["rule_text"],
            "category": r.get("category", ""),
            "confidence": round(r["confidence"], 2),
            "validated": r.get("times_validated", 0),
            "profitable": r.get("times_profitable", 0),
            "source": r.get("source_title", ""),
        })
    return {"rules": entries}


@tool(
    name="knowledge_summary",
    description="Get a summary of everything the bot has learned — total entries, strategies discovered, indicators tracked, rule counts by category.",
    parameters={"properties": {}, "required": []},
)
def knowledge_summary() -> dict:
    from bot.learning.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    return kb.get_evolution_summary()


@tool(
    name="ingest_content",
    description="Teach the bot something new. Ingest a YouTube video URL or text content into the knowledge base. The bot extracts trading rules, strategies, and indicators automatically.",
    parameters={
        "properties": {
            "content": {"type": "string", "description": "YouTube URL or text content to ingest"},
            "title": {"type": "string", "description": "Title for text content (not needed for YouTube URLs)", "default": ""},
        },
        "required": ["content"],
    },
)
def ingest_content(content: str, title: str = "") -> dict:
    from bot.learning.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()

    if "youtube.com" in content or "youtu.be" in content:
        return kb.ingest_youtube(content)
    else:
        title = title or f"Agent ingestion {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return kb.ingest_text(title, content, source_type="agent")


# ─── Portfolio & Trading Tools ────────────────────────────────

@tool(
    name="get_portfolio",
    description="Show the current paper trading portfolio — open positions, P&L, win rate, and performance summary.",
    parameters={"properties": {}, "required": []},
)
def get_portfolio() -> dict:
    from bot.engine.paper_trader import PaperTrader
    pt = PaperTrader()
    positions = pt.get_open_positions()
    summary = pt.get_performance_summary()

    pos_list = []
    for p in positions:
        pos_list.append({
            "symbol": p["symbol"],
            "quantity": p["quantity"],
            "entry_price": round(p["entry_price"], 2),
            "strategy": p.get("strategy_name", ""),
        })

    return {
        "positions": pos_list,
        "position_count": len(positions),
        "total_trades": summary.get("total_trades", 0),
        "win_rate": round(summary.get("win_rate", 0), 1),
        "total_pnl": round(summary.get("total_pnl", 0), 2),
    }


@tool(
    name="get_broker_status",
    description="Check which brokers are connected and their status. Shows routing configuration (which broker handles options, day trades, swing trades).",
    parameters={"properties": {}, "required": []},
)
def get_broker_status() -> dict:
    from bot.config.settings import CONFIG
    routing = CONFIG.get("brokers", {}).get("routing", {})
    default = CONFIG.get("brokers", {}).get("default", "alpaca")

    result = {
        "default_broker": default,
        "routing": routing,
        "brokers": {},
    }

    try:
        from bot.brokers.manager import BrokerManager
        bm = BrokerManager()
        for name, broker in bm.brokers.items():
            result["brokers"][name] = {
                "connected": broker.is_connected(),
            }
        result["total_equity"] = round(bm.get_total_equity(), 2)
    except Exception as e:
        result["error"] = str(e)

    return result


@tool(
    name="check_earnings",
    description="Check upcoming earnings dates for a symbol or get all earnings this week.",
    parameters={
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol, or 'all' for this week's earnings", "default": "all"},
        },
        "required": [],
    },
)
def check_earnings(symbol: str = "all") -> dict:
    try:
        from bot.engine.economic_calendar import get_upcoming_events
        events = get_upcoming_events(days_ahead=14)
        earnings_events = [e for e in events if "earnings" in str(e).lower() or "report" in str(e).lower()]
        return {
            "upcoming_events": len(events),
            "earnings_events": len(earnings_events),
            "events": [{"date": str(e.date), "event": e.event, "importance": e.importance} for e in events[:10]],
        }
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="analyze_symbol",
    description="Full analysis of a symbol — price, sentiment, regime context, knowledge base rules, and any active signals. This is the most comprehensive single-symbol analysis.",
    parameters={
        "properties": {
            "symbol": {"type": "string", "description": "Stock ticker symbol to analyze"},
        },
        "required": ["symbol"],
    },
)
def analyze_symbol(symbol: str) -> dict:
    symbol = symbol.upper().strip()
    analysis = {"symbol": symbol}

    # Price
    try:
        analysis["price"] = get_price(symbol)
    except Exception as e:
        analysis["price_error"] = str(e)

    # Sentiment
    try:
        analysis["sentiment"] = check_sentiment(symbol)
    except Exception as e:
        analysis["sentiment_error"] = str(e)

    # Knowledge
    try:
        from bot.learning.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        rules = kb.get_rules_for_setup(symbol)
        analysis["known_rules"] = [r["rule_text"] for r in rules[:5]]
    except Exception:
        analysis["known_rules"] = []

    # Indicators
    try:
        from bot.config.settings import CONFIG
        provider = CONFIG.get("data", {}).get("provider", "yfinance")
        if provider == "alpaca":
            from bot.data.alpaca_provider import fetch_alpaca_bars
            candles = fetch_alpaca_bars(symbol, interval="1d", days=60)
        else:
            from bot.data.fetcher import fetch_market_data
            candles = fetch_market_data(symbol, period="60d", interval="1d")

        if candles and len(candles) >= 20:
            from bot.engine.indicators import calculate_indicators
            indicators = calculate_indicators(candles)
            analysis["indicators"] = {
                "rsi_14": round(indicators.rsi_14, 2) if indicators.rsi_14 else None,
                "sma_20": round(indicators.sma_20, 2) if indicators.sma_20 else None,
                "sma_50": round(indicators.sma_50, 2) if indicators.sma_50 else None,
                "macd_histogram": round(indicators.macd_histogram, 4) if indicators.macd_histogram else None,
                "atr_14": round(indicators.atr_14, 2) if indicators.atr_14 else None,
                "bb_upper": round(indicators.bb_upper, 2) if indicators.bb_upper else None,
                "bb_lower": round(indicators.bb_lower, 2) if indicators.bb_lower else None,
            }
    except Exception as e:
        analysis["indicators_error"] = str(e)

    return analysis


@tool(
    name="get_sector_rotation",
    description="Analyze sector rotation — which sectors are leading/lagging vs SPY. Helps identify where money is flowing.",
    parameters={"properties": {}, "required": []},
)
def get_sector_rotation() -> dict:
    from bot.engine.sector_rotation import SECTOR_ETFS, analyze_sector_rotation
    from bot.config.settings import CONFIG

    sector_data = {}
    provider = CONFIG.get("data", {}).get("provider", "yfinance")

    for symbol in list(SECTOR_ETFS.keys()) + ["SPY"]:
        try:
            if provider == "alpaca":
                from bot.data.alpaca_provider import fetch_alpaca_bars
                candles = fetch_alpaca_bars(symbol, interval="1d", days=5)
            else:
                from bot.data.fetcher import fetch_market_data
                candles = fetch_market_data(symbol, period="5d", interval="1d")

            if len(candles) >= 2:
                change = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
                vol_ratio = candles[-1].volume / candles[-2].volume if candles[-2].volume > 0 else 1.0
                sector_data[symbol] = {"change_pct": round(change, 2), "volume_ratio": round(vol_ratio, 2)}
        except Exception:
            continue

    if not sector_data:
        return {"error": "Could not fetch sector data"}

    report = analyze_sector_rotation(sector_data)
    return {
        "regime": report.market_regime,
        "spy_change": report.spy_change_pct,
        "top_sectors": [{"symbol": s.symbol, "name": s.name, "change": s.change_pct, "vs_spy": s.relative_to_spy} for s in report.top_sectors],
        "bottom_sectors": [{"symbol": s.symbol, "name": s.name, "change": s.change_pct, "vs_spy": s.relative_to_spy} for s in report.bottom_sectors],
        "recommendation": report.recommendation,
    }


@tool(
    name="get_watchlist",
    description="Get the current watchlist symbols.",
    parameters={"properties": {}, "required": []},
)
def get_watchlist() -> dict:
    from bot.config.settings import CONFIG
    symbols = CONFIG.get("bot", {}).get("watchlist", [])
    return {"watchlist": symbols, "count": len(symbols)}


@tool(
    name="get_premarket",
    description="Run the pre-market scanner — gap ups/downs, high volume movers, earnings today. Best used before market open.",
    parameters={"properties": {}, "required": []},
)
def get_premarket() -> dict:
    from bot.engine.premarket_scanner import scan_premarket, get_earnings_today
    movers = scan_premarket()
    earnings = get_earnings_today()

    mover_list = []
    for m in (movers or [])[:10]:
        if isinstance(m, dict):
            mover_list.append(m)
        else:
            mover_list.append(str(m))

    return {
        "movers": mover_list,
        "mover_count": len(movers or []),
        "earnings_today": earnings or [],
    }
