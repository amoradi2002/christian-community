from flask import Blueprint, jsonify, request
from bot.alerts.manager import AlertManager
from bot.strategies.store import list_strategies
from bot.engine.performance import get_strategy_stats, get_open_positions
from bot.config.settings import CONFIG

api_bp = Blueprint("api", __name__)


@api_bp.route("/signals")
def get_signals():
    alert_mgr = AlertManager()
    alerts = alert_mgr.get_alert_history(limit=20)
    return jsonify(alerts)


@api_bp.route("/strategies")
def get_strategies():
    strategies = list_strategies(active_only=False)
    return jsonify(strategies)


@api_bp.route("/performance")
def get_performance():
    stats = get_strategy_stats()
    positions = get_open_positions()
    return jsonify({"stats": stats, "open_positions": positions})


@api_bp.route("/prices")
def get_prices():
    """Get real-time prices - uses Alpaca if configured, falls back to Yahoo."""
    provider = CONFIG.get("data", {}).get("provider", "yfinance")
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])
    symbol = request.args.get("symbol")

    if provider == "alpaca":
        try:
            from bot.data.alpaca_provider import fetch_alpaca_realtime, fetch_alpaca_snapshot
            if symbol:
                price = fetch_alpaca_realtime(symbol.upper())
                return jsonify(price if price else {"error": f"Could not fetch {symbol}"})
            # Batch fetch all watchlist prices (single API call)
            return jsonify(fetch_alpaca_snapshot(watchlist))
        except (ImportError, ValueError):
            pass  # Fall through to yfinance

    from bot.data.fetcher import fetch_realtime_price
    if symbol:
        price = fetch_realtime_price(symbol.upper())
        return jsonify(price if price else {"error": f"Could not fetch {symbol}"})

    prices = {}
    for sym in watchlist:
        price = fetch_realtime_price(sym)
        if price:
            prices[sym] = price
    return jsonify(prices)


# --- Options API ---

@api_bp.route("/options/chain")
def get_options_chain():
    """Get options chain for a symbol. ?symbol=AAPL&expiry_max=2025-04-18"""
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "symbol parameter required"}), 400

    try:
        from bot.data.options import get_options_chain
        chain = get_options_chain(
            symbol,
            expiry_min=request.args.get("expiry_min"),
            expiry_max=request.args.get("expiry_max"),
            option_type=request.args.get("type"),
        )
        return jsonify(chain.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Options data unavailable: {e}"}), 500


@api_bp.route("/options/recommend")
def recommend_options():
    """
    Get options strategy recommendations. ?symbol=AAPL&direction=bullish&confidence=0.8&dte=30
    """
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "symbol parameter required"}), 400

    direction = request.args.get("direction", "bullish")
    if direction not in ("bullish", "bearish", "neutral"):
        return jsonify({"error": "direction must be bullish, bearish, or neutral"}), 400

    try:
        from bot.engine.options_strategies import OptionsEngine
        engine = OptionsEngine()
        setups = engine.recommend(
            symbol=symbol,
            direction=direction,
            confidence=float(request.args.get("confidence", 0.7)),
            target_dte=int(request.args.get("dte", 30)),
        )
        return jsonify({
            "symbol": symbol,
            "direction": direction,
            "strategies": [s.to_dict() for s in setups],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/options/quote")
def get_option_quote():
    """Get quote for specific contract. ?contract=AAPL250321C00170000"""
    contract = request.args.get("contract", "")
    if not contract:
        return jsonify({"error": "contract parameter required"}), 400

    try:
        from bot.data.options import get_option_quote
        quote = get_option_quote(contract)
        return jsonify(quote.to_dict() if quote else {"error": "Quote not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Trading API ---

@api_bp.route("/account")
def get_account():
    """Get Alpaca account info (balance, buying power)."""
    try:
        from bot.engine.trader import get_account_info
        return jsonify(get_account_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/positions")
def get_trading_positions():
    """Get all open trading positions from Alpaca."""
    try:
        from bot.engine.trader import get_positions
        return jsonify(get_positions())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/orders", methods=["GET"])
def list_orders():
    """Get recent orders. ?status=open|closed|all"""
    try:
        from bot.engine.trader import get_orders
        status = request.args.get("status", "open")
        return jsonify(get_orders(status=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/trade/stock", methods=["POST"])
def trade_stock():
    """
    Place a stock order with risk management. JSON body:
    {"symbol": "AAPL", "price": 175.50, "side": "buy", "confidence": 0.8}

    If qty is omitted, the risk manager calculates optimal position size.
    If qty is provided, it overrides risk-based sizing.
    """
    trading_cfg = CONFIG.get("trading", {})
    if not trading_cfg.get("enabled", False):
        return jsonify({"error": "Trading is disabled. Set trading.enabled=true in config.yaml"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    symbol = data.get("symbol", "").upper()
    side = data.get("side", "")
    if not symbol or not side:
        return jsonify({"error": "symbol and side are required"}), 400

    try:
        from bot.engine.trader import place_stock_order
        from bot.engine.risk_manager import RiskManager

        rm = RiskManager()
        qty = data.get("qty")

        # If no qty provided, calculate from risk profile
        if qty is None and side.lower() == "buy":
            price = float(data.get("price", data.get("limit_price", 0)))
            if not price:
                return jsonify({"error": "Need price or limit_price for risk-based sizing"}), 400

            sizing = rm.calculate_position_size(
                symbol=symbol,
                price=price,
                confidence=float(data.get("confidence", 0.65)),
            )

            if not sizing["can_trade"]:
                return jsonify({"error": sizing["reason"], "sizing": sizing}), 403

            qty = sizing["shares"]
            # Include risk info in response
            risk_info = sizing
        else:
            qty = float(qty or 1)
            risk_info = None

        result = place_stock_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=data.get("order_type", trading_cfg.get("default_order_type", "market")),
            limit_price=data.get("limit_price"),
            stop_price=data.get("stop_price"),
            time_in_force=data.get("time_in_force", "day"),
        )

        response = result.to_dict()
        if risk_info:
            response["risk_sizing"] = risk_info

        status_code = 200 if result.success else 400
        return jsonify(response), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/trade/option", methods=["POST"])
def trade_option():
    """
    Place an options order. JSON body:
    {"contract": "AAPL250321C00170000", "qty": 1, "side": "buy", "limit_price": 5.50}
    """
    trading_cfg = CONFIG.get("trading", {})
    if not trading_cfg.get("enabled", False):
        return jsonify({"error": "Trading is disabled. Set trading.enabled=true in config.yaml"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    required = ["contract", "qty", "side"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        from bot.engine.trader import place_option_order
        from bot.engine.risk_manager import RiskManager

        rm = RiskManager()
        side = data["side"].lower()
        qty = int(data["qty"])
        limit_price = data.get("limit_price")

        # Risk check for buying options
        if side == "buy" and limit_price:
            cost_per_contract = float(limit_price) * 100
            total_cost = cost_per_contract * qty
            sizing = rm.calculate_options_size(
                premium_per_contract=float(limit_price),
                confidence=float(data.get("confidence", 0.65)),
            )
            if not sizing["can_trade"]:
                return jsonify({"error": sizing["reason"], "sizing": sizing}), 403
            # Cap qty at what risk manager allows
            qty = min(qty, sizing["contracts"])
            risk_info = sizing
        else:
            risk_info = None

        result = place_option_order(
            contract_symbol=data["contract"],
            qty=qty,
            side=side,
            order_type=data.get("order_type", "limit"),
            limit_price=limit_price,
            time_in_force=data.get("time_in_force", "day"),
        )

        response = result.to_dict()
        if risk_info:
            response["risk_sizing"] = risk_info

        status_code = 200 if result.success else 400
        return jsonify(response), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/orders/<order_id>", methods=["DELETE"])
def cancel_order_route(order_id):
    """Cancel an open order."""
    try:
        from bot.engine.trader import cancel_order
        success = cancel_order(order_id)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Unusual Whales API ---

@api_bp.route("/flow")
def get_flow():
    """Get unusual options flow. ?ticker=AAPL&min_premium=100000"""
    try:
        from bot.data.unusual_whales import get_options_flow, get_cached_flow
        ticker = request.args.get("ticker")
        min_premium = int(request.args.get("min_premium", 100000))

        try:
            flows = get_options_flow(ticker=ticker, min_premium=min_premium)
        except ValueError:
            flows = get_cached_flow(ticker=ticker)

        return jsonify([f.to_dict() for f in flows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/alerts")
def get_whale_alerts():
    """Get whale-level flow alerts (>$500k). ?sentiment=bullish"""
    try:
        from bot.data.unusual_whales import get_flow_alerts
        sentiment = request.args.get("sentiment")
        min_premium = int(request.args.get("min_premium", 500000))
        flows = get_flow_alerts(min_premium=min_premium, sentiment=sentiment)
        return jsonify([f.to_dict() for f in flows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/sentiment")
def get_market_sentiment():
    """Get market-wide flow sentiment."""
    try:
        from bot.data.unusual_whales import get_flow_sentiment
        return jsonify(get_flow_sentiment())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/flow/sentiment/<ticker>")
def get_stock_flow_sentiment(ticker):
    """Get flow sentiment for a specific ticker."""
    try:
        from bot.data.unusual_whales import get_ticker_sentiment
        return jsonify(get_ticker_sentiment(ticker))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/darkpool")
def get_darkpool():
    """Get dark pool trades. ?ticker=AAPL"""
    try:
        from bot.data.unusual_whales import get_dark_pool
        ticker = request.args.get("ticker")
        trades = get_dark_pool(ticker=ticker)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/congress")
def get_congress():
    """Get congressional trades. ?ticker=AAPL&party=Democrat"""
    try:
        from bot.data.unusual_whales import get_congress_trades
        ticker = request.args.get("ticker")
        party = request.args.get("party")
        trades = get_congress_trades(ticker=ticker, party=party)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Finviz API ---

@api_bp.route("/fundamentals/<symbol>")
def get_fundamentals(symbol):
    """Get stock fundamentals from Finviz."""
    try:
        from bot.data.finviz_provider import get_stock_fundamentals
        data = get_stock_fundamentals(symbol.upper())
        return jsonify(data.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/screener")
def run_screener():
    """
    Run Finviz stock screener.
    ?signal=top_gainers or ?signal=oversold or ?signal=unusual_volume
    """
    try:
        from bot.data.finviz_provider import screen_stocks
        signal = request.args.get("signal", "")
        results = screen_stocks(signal=signal)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/insider")
def get_insider():
    """Get insider trades. ?symbol=AAPL"""
    try:
        from bot.data.finviz_provider import get_insider_trades
        symbol = request.args.get("symbol")
        trades = get_insider_trades(symbol=symbol)
        return jsonify([t.to_dict() for t in trades])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/news")
def get_news():
    """Get market or stock news. ?symbol=AAPL"""
    try:
        symbol = request.args.get("symbol")
        if symbol:
            from bot.data.finviz_provider import get_stock_news
            return jsonify(get_stock_news(symbol.upper()))
        else:
            from bot.data.finviz_provider import get_market_news
            return jsonify(get_market_news())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Earnings API ---

@api_bp.route("/earnings/calendar")
def earnings_calendar():
    """Get upcoming earnings calendar. ?days=7"""
    try:
        from bot.data.earnings import get_earnings_calendar
        days = int(request.args.get("days", 7))
        events = get_earnings_calendar(days_ahead=days)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/whisper/<symbol>")
def earnings_whisper(symbol):
    """Get whisper number for a stock."""
    try:
        from bot.data.earnings import get_earnings_whisper
        event = get_earnings_whisper(symbol.upper())
        if event:
            return jsonify(event.to_dict())
        return jsonify({"error": f"No whisper data for {symbol}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/history/<symbol>")
def earnings_history(symbol):
    """Get past earnings history. ?quarters=8"""
    try:
        from bot.data.earnings import get_earnings_history
        quarters = int(request.args.get("quarters", 8))
        events = get_earnings_history(symbol.upper(), quarters=quarters)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/earnings/watchlist")
def earnings_watchlist():
    """Check which watchlist stocks have upcoming earnings. ?days=30"""
    try:
        from bot.data.earnings import get_watchlist_earnings
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        days = int(request.args.get("days", 30))
        events = get_watchlist_earnings(watchlist, days_ahead=days)
        return jsonify([e.to_dict() for e in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Profile & Risk Management API ---

@api_bp.route("/profile", methods=["GET"])
def get_profile():
    """Get your trading profile and risk status."""
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        return jsonify(rm.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile", methods=["POST"])
def update_user_profile():
    """
    Update your trading profile. JSON body with any of:
    {"starting_capital": 1000, "risk_level": "moderate", "risk_per_trade_pct": 2, ...}
    """
    try:
        from bot.engine.risk_manager import update_profile
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        # Whitelist of fields users can update
        allowed = {
            "starting_capital", "current_capital", "risk_per_trade_pct",
            "max_portfolio_pct", "max_open_positions", "risk_level",
            "max_day_trades", "max_swing_trades",
            "daily_loss_limit_pct", "weekly_loss_limit_pct",
            "options_max_pct", "min_risk_reward",
            "preferred_strategies",
        }
        filtered = {k: v for k, v in data.items() if k in allowed}

        if not filtered:
            return jsonify({"error": f"No valid fields. Allowed: {sorted(allowed)}"}), 400

        # If setting starting capital for first time, also set current and peak
        if "starting_capital" in filtered and "current_capital" not in filtered:
            filtered["current_capital"] = filtered["starting_capital"]
            filtered["peak_capital"] = filtered["starting_capital"]

        profile = update_profile(**filtered)
        return jsonify(profile.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile/sync", methods=["POST"])
def sync_profile_with_broker():
    """Sync your profile capital with actual Alpaca account balance."""
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        rm.update_capital_from_broker()
        return jsonify(rm.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/risk/calculate", methods=["POST"])
def calculate_risk():
    """
    Calculate position size for a trade. JSON body:
    {"symbol": "AAPL", "price": 175.50, "confidence": 0.8}
    """
    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        data = request.get_json()
        if not data or "symbol" not in data or "price" not in data:
            return jsonify({"error": "Need symbol and price"}), 400

        result = rm.calculate_position_size(
            symbol=data["symbol"],
            price=float(data["price"]),
            stop_loss_pct=data.get("stop_loss_pct"),
            confidence=float(data.get("confidence", 0.65)),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Day Trade Scanner API ---

@api_bp.route("/scan/day")
def run_day_scan():
    """Run day trade scan with intraday data."""
    try:
        from bot.engine.analyzer import Analyzer
        analyzer = Analyzer()
        interval = request.args.get("interval", CONFIG.get("data", {}).get("intraday_interval", "5m"))
        results = analyzer.run_day_scan(interval=interval)
        return jsonify({
            "signals": {sym: [s.to_dict() for s in sigs] for sym, sigs in results.items()},
            "total": sum(len(s) for s in results.values()),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/scan/swing")
def run_swing_scan():
    """Run swing trade scan with daily data."""
    try:
        from bot.engine.analyzer import Analyzer
        analyzer = Analyzer()
        results = analyzer.run_swing_scan()
        return jsonify({
            "signals": {sym: [s.to_dict() for s in sigs] for sym, sigs in results.items()},
            "total": sum(len(s) for s in results.values()),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/scan/pillars")
def check_pillars():
    """
    Check a stock against the 5 Pillars of day trade selection.
    ?symbol=XYZ&price=8.50&change=12.5&rvol=6.2&catalyst=FDA+approval&float=3.5
    """
    try:
        from bot.engine.day_scanner import check_five_pillars
        symbol = request.args.get("symbol", "").upper()
        if not symbol:
            return jsonify({"error": "symbol required"}), 400

        candidate = check_five_pillars(
            symbol=symbol,
            price=float(request.args.get("price", 0)),
            day_change_pct=float(request.args.get("change", 0)),
            relative_volume=float(request.args.get("rvol", 0)),
            catalyst=request.args.get("catalyst", ""),
            float_shares_m=float(request.args.get("float", 0)),
        )
        return jsonify(candidate.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Candlestick Patterns API ---

@api_bp.route("/candles/<symbol>")
def get_candle_patterns(symbol):
    """Detect candlestick patterns for a symbol. ?interval=1d"""
    try:
        from bot.data.candle_patterns import detect_patterns
        from bot.engine.analyzer import _fetch_candles

        interval = request.args.get("interval", "1d")
        candles = _fetch_candles(symbol.upper(), interval=interval)
        if len(candles) < 5:
            return jsonify({"error": "Not enough data"}), 400

        patterns = detect_patterns(candles[-5:])
        return jsonify({
            "symbol": symbol.upper(),
            "interval": interval,
            "patterns": [{"name": p.name, "direction": p.direction,
                          "strength": p.strength, "description": p.description}
                         for p in patterns],
            "latest_candle": {
                "open": candles[-1].open, "high": candles[-1].high,
                "low": candles[-1].low, "close": candles[-1].close,
                "volume": candles[-1].volume,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Sector Rotation API ---

@api_bp.route("/sectors")
def get_sectors():
    """Get sector rotation analysis."""
    try:
        from bot.engine.sector_rotation import SECTOR_ETFS, analyze_sector_rotation
        from bot.engine.analyzer import _fetch_candles

        sector_data = {}
        all_symbols = list(SECTOR_ETFS.keys()) + ["SPY"]

        for symbol in all_symbols:
            try:
                candles = _fetch_candles(symbol, interval="1d", days=5)
                if len(candles) >= 2:
                    change = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
                    sector_data[symbol] = {"change_pct": round(change, 2)}
            except Exception:
                pass

        if not sector_data:
            return jsonify({"error": "Could not fetch sector data"}), 500

        report = analyze_sector_rotation(sector_data)
        return jsonify(report.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/sectors/check/<symbol>")
def check_sector_alignment(symbol):
    """Check if a trade aligns with sector rotation. ?action=BUY"""
    try:
        from bot.engine.sector_rotation import check_sector_alignment as _check
        from bot.engine.analyzer import _fetch_candles
        from bot.engine.sector_rotation import SECTOR_ETFS

        action = request.args.get("action", "BUY")
        sector_data = {}
        for sym in list(SECTOR_ETFS.keys()) + ["SPY"]:
            try:
                candles = _fetch_candles(sym, interval="1d", days=5)
                if len(candles) >= 2:
                    change = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
                    sector_data[sym] = {"change_pct": round(change, 2)}
            except Exception:
                pass

        result = _check(symbol.upper(), action, sector_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Trade Journal API ---

@api_bp.route("/journal", methods=["GET"])
def get_journal():
    """Get trade journal entries. ?status=closed&style=day&limit=50"""
    try:
        from bot.engine.trade_journal import get_trades
        entries = get_trades(
            status=request.args.get("status"),
            symbol=request.args.get("symbol"),
            style=request.args.get("style"),
            limit=int(request.args.get("limit", 50)),
        )
        return jsonify([e.to_dict() for e in entries])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/journal/log", methods=["POST"])
def log_journal_trade():
    """
    Log a new trade to the journal. JSON body:
    {"symbol": "AAPL", "style": "day", "direction": "long", "setup": "Pullback",
     "entry_price": 175.50, "shares": 10, "stop_loss": 173.00, "target": 180.00,
     "catalyst": "Earnings beat", "why_entered": "Clean pullback to VWAP"}
    """
    try:
        from bot.engine.trade_journal import log_trade, JournalEntry

        data = request.get_json()
        if not data or "symbol" not in data:
            return jsonify({"error": "JSON body with symbol required"}), 400

        entry = JournalEntry(
            symbol=data["symbol"].upper(),
            style=data.get("style", ""),
            direction=data.get("direction", "long"),
            setup=data.get("setup", ""),
            catalyst=data.get("catalyst", ""),
            catalyst_tier=data.get("catalyst_tier", ""),
            entry_price=float(data.get("entry_price", 0)),
            entry_time=data.get("entry_time", ""),
            shares=float(data.get("shares", 0)),
            stop_loss=float(data.get("stop_loss", 0)),
            target=float(data.get("target", 0)),
            risk_reward_planned=float(data.get("risk_reward", 0)),
            why_entered=data.get("why_entered", ""),
            candle_pattern=data.get("candle_pattern", ""),
            sector=data.get("sector", ""),
        )

        # Calculate R:R if not provided
        if entry.risk_reward_planned == 0 and entry.stop_loss > 0 and entry.target > 0:
            risk = abs(entry.entry_price - entry.stop_loss)
            reward = abs(entry.target - entry.entry_price)
            entry.risk_reward_planned = round(reward / risk, 1) if risk > 0 else 0

        entry_id = log_trade(entry)
        return jsonify({"id": entry_id, "status": "logged"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/journal/<int:entry_id>/close", methods=["POST"])
def close_journal_trade(entry_id):
    """
    Close an open trade. JSON body:
    {"exit_price": 180.00, "why_exited": "Hit target", "lesson": "Patience pays",
     "emotion": "Calm", "process_score": 4, "result_score": 5}
    """
    try:
        from bot.engine.trade_journal import close_trade

        data = request.get_json()
        if not data or "exit_price" not in data:
            return jsonify({"error": "Need exit_price"}), 400

        entry = close_trade(
            entry_id=entry_id,
            exit_price=float(data["exit_price"]),
            exit_time=data.get("exit_time", ""),
            why_exited=data.get("why_exited", ""),
            what_did_right=data.get("what_did_right", ""),
            what_id_change=data.get("what_id_change", ""),
            lesson=data.get("lesson", ""),
            emotion=data.get("emotion", ""),
            process_score=int(data.get("process_score", 0)),
            result_score=int(data.get("result_score", 0)),
        )
        return jsonify(entry.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/journal/review")
def journal_review():
    """Get weekly trade journal review. ?weeks_ago=0"""
    try:
        from bot.engine.trade_journal import weekly_review
        weeks = int(request.args.get("weeks_ago", 0))
        review = weekly_review(weeks_ago=weeks)
        return jsonify(review)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Catalyst Grading API ---

@api_bp.route("/catalyst/grade", methods=["POST"])
def grade_catalyst():
    """Grade a catalyst. JSON body: {"text": "FDA approved new drug for..."}"""
    try:
        from bot.engine.day_scanner import grade_catalyst as _grade, CATALYST_TIERS
        data = request.get_json()
        if not data or "text" not in data:
            return jsonify({"error": "Need text field"}), 400

        tier = _grade(data["text"])
        info = CATALYST_TIERS.get(tier, {})
        return jsonify({
            "tier": tier,
            "name": info.get("name", "Skip"),
            "description": info.get("description", "No catalyst or unrecognized"),
            "reliability": info.get("reliability", "Do not trade"),
            "tradeable": tier in ("S", "A"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Portfolio & Paper Trading API ---

@api_bp.route("/portfolio/positions")
def get_paper_positions():
    """Get open paper trading positions."""
    try:
        from bot.engine.paper_trader import PaperTrader
        pt = PaperTrader()
        return jsonify(pt.get_open_positions())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/summary")
def get_portfolio_summary():
    """Get paper trading performance summary."""
    try:
        from bot.engine.paper_trader import PaperTrader
        pt = PaperTrader()
        return jsonify(pt.get_performance_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/equity-curve")
def get_equity_curve():
    """Get equity curve data for charting."""
    try:
        from bot.engine.paper_trader import PaperTrader
        pt = PaperTrader()
        history = pt.get_trade_history(limit=200)
        # Build cumulative equity curve
        starting = CONFIG.get("paper_trading", {}).get("starting_capital", 10000)
        curve = [{"date": "start", "value": starting}]
        running = starting
        for trade in reversed(history):
            running += trade.get("pnl_dollars", 0)
            curve.append({"date": trade.get("closed_at", ""), "value": round(running, 2)})
        return jsonify(curve)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/daily-pnl")
def get_daily_pnl():
    """Get daily P&L for last 7 days."""
    try:
        from bot.engine.daily_pnl import DailyPnLTracker
        tracker = DailyPnLTracker()
        return jsonify(tracker.get_weekly_daily_pnl())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/exposure")
def get_sector_exposure():
    """Get sector exposure of open positions."""
    try:
        from bot.engine.paper_trader import PaperTrader
        from bot.engine.sector_rotation import get_sector_for_stock
        pt = PaperTrader()
        positions = pt.get_open_positions()
        exposure = {}
        for p in positions:
            sector = get_sector_for_stock(p["symbol"]) or "Unknown"
            value = p.get("quantity", 0) * p.get("entry_price", 0)
            exposure[sector] = exposure.get(sector, 0) + value
        return jsonify(exposure)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/correlation")
def get_correlation():
    """Get correlation matrix for watchlist."""
    try:
        from bot.engine.correlation import calculate_correlation_matrix, check_portfolio_correlation
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        if len(watchlist) < 2:
            return jsonify({"error": "Need 2+ symbols"}), 400
        matrix = calculate_correlation_matrix(watchlist[:10])
        alerts = check_portfolio_correlation(watchlist[:10])
        return jsonify({
            "matrix": matrix,
            "alerts": [{"symbol_a": a.symbol_a, "symbol_b": a.symbol_b,
                        "correlation": a.correlation, "risk_level": a.risk_level,
                        "message": a.message} for a in alerts],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/portfolio/strategy-stats")
def get_strategy_performance():
    """Get strategy performance stats."""
    try:
        from bot.engine.strategy_tracker import get_strategy_stats
        return jsonify(get_strategy_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Pre-Market & Calendar API ---

@api_bp.route("/premarket")
def get_premarket():
    """Run pre-market scan."""
    try:
        from bot.engine.premarket_scanner import scan_premarket, should_run_premarket
        movers = scan_premarket()
        return jsonify({
            "is_premarket": should_run_premarket(),
            "movers": [{"symbol": m.symbol, "gap_pct": m.gap_pct, "volume_ratio": m.volume_ratio,
                        "catalyst": m.catalyst, "price": m.price, "prev_close": m.prev_close,
                        "direction": m.direction, "meets_5_pillars": m.meets_5_pillars,
                        "notes": m.notes} for m in movers],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/premarket/earnings")
def get_earnings():
    """Get stocks reporting earnings today."""
    try:
        from bot.engine.premarket_scanner import get_earnings_today
        return jsonify(get_earnings_today())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/calendar")
def get_econ_calendar():
    """Get economic calendar."""
    try:
        from bot.engine.economic_calendar import get_upcoming_events, get_trading_caution
        days = int(request.args.get("days", 14))
        events = get_upcoming_events(days_ahead=days)
        caution = get_trading_caution()
        return jsonify({
            "caution": caution,
            "events": [{"date": e.date, "time": e.time, "event": e.event,
                        "importance": e.importance, "impact": e.impact,
                        "trading_note": e.trading_note} for e in events],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- News Sentiment API ---

@api_bp.route("/sentiment/<symbol>")
def get_sentiment(symbol):
    """Get news sentiment for a symbol."""
    try:
        from bot.engine.news_sentiment import fetch_news_sentiment
        return jsonify(fetch_news_sentiment(symbol.upper()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Knowledge Base API ---

@api_bp.route("/knowledge")
def get_knowledge():
    """Get knowledge base evolution summary."""
    try:
        from bot.learning.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        return jsonify(kb.get_evolution_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/knowledge/search")
def search_knowledge():
    """Search the knowledge base. ?q=RSI+oversold"""
    try:
        from bot.learning.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        query = request.args.get("q", "")
        if not query:
            return jsonify({"error": "q parameter required"}), 400
        return jsonify(kb.search_knowledge(query))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/knowledge/ingest", methods=["POST"])
def ingest_knowledge():
    """Ingest content into knowledge base. JSON: {"url": "..."} or {"title": "...", "content": "..."}"""
    try:
        from bot.learning.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        if "url" in data:
            result = kb.ingest_youtube(data["url"])
        elif "content" in data:
            result = kb.ingest_text(
                title=data.get("title", "API entry"),
                content=data["content"],
                source_type=data.get("source_type", "manual"),
                source_url=data.get("source_url", ""),
                confidence=float(data.get("confidence", 0.8)),
            )
        else:
            return jsonify({"error": "Need 'url' or 'content' field"}), 400

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/knowledge/rules/<setup>")
def get_rules_for_setup(setup):
    """Get learned rules for a setup type."""
    try:
        from bot.learning.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        return jsonify(kb.get_rules_for_setup(setup))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/health")
def health():
    provider = CONFIG.get("data", {}).get("provider", "yfinance")
    trading_enabled = CONFIG.get("trading", {}).get("enabled", False)

    # Count available strategies
    from bot.strategies.registry import StrategyRegistry
    reg = StrategyRegistry()
    reg.load_builtins()

    return jsonify({
        "status": "ok",
        "data_provider": provider,
        "trading_enabled": trading_enabled,
        "strategies": {
            "total": len(reg.get_all()),
            "day": len(reg.get_by_style("day")),
            "swing": len(reg.get_by_style("swing")),
            "general": len(reg.get_by_style("general")),
        },
        "features": [
            "day_trading", "swing_trading", "options",
            "candle_patterns", "sector_rotation", "trade_journal",
            "5_pillars_scanner", "catalyst_grading", "risk_management",
            "paper_trading", "strategy_tracker", "alert_cooldowns",
            "daily_pnl_tracker", "premarket_scanner", "economic_calendar",
            "news_sentiment", "correlation_matrix", "portfolio_dashboard",
            "telegram_bot", "email_digest", "websocket_streaming",
            "knowledge_base", "interactive_cli",
        ],
    })
