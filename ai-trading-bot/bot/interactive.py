"""
Interactive CLI - Talk to the bot in real-time

Commands:
    analyze AAPL         - Full analysis on any ticker
    scan                 - Run full scan
    day                  - Day trade scan
    swing                - Swing trade scan
    watchlist             - Show current watchlist
    add TSLA             - Add symbol to watchlist
    remove MSFT          - Remove symbol from watchlist
    rsi AAPL             - Check RSI + options signals
    candles AAPL         - Detect candlestick patterns
    pillars AAPL         - Check 5 Pillars (needs manual data)
    risk AAPL 175.50     - Calculate position size
    sectors              - Sector rotation report
    journal              - Weekly review
    log                  - Log a trade interactively
    profile              - Show your risk profile
    status               - Account status + open positions
    help                 - Show this help
    quit                 - Exit
"""

import yaml
from pathlib import Path

from bot.config.settings import CONFIG
from bot.db.database import init_db


def run_interactive():
    """Run the bot in interactive mode."""
    init_db()

    try:
        from bot.engine.trade_journal import init_journal_table
        init_journal_table()
    except Exception:
        pass

    print("\n=== AI Trading Bot — Interactive Mode ===")
    print("Type 'help' for commands. Your portfolio, your decisions.\n")

    _show_status_brief()

    while True:
        try:
            user_input = input("\nbot> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        parts = user_input.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd in ("quit", "exit", "q"):
                print("Goodbye!")
                break
            elif cmd == "help":
                _show_help()
            elif cmd in ("analyze", "a"):
                _analyze(args)
            elif cmd == "scan":
                _run_scan()
            elif cmd == "day":
                _run_day_scan()
            elif cmd == "swing":
                _run_swing_scan()
            elif cmd in ("watchlist", "wl"):
                _show_watchlist()
            elif cmd == "add":
                _add_to_watchlist(args)
            elif cmd == "remove":
                _remove_from_watchlist(args)
            elif cmd == "rsi":
                _check_rsi(args)
            elif cmd in ("candles", "candle"):
                _check_candles(args)
            elif cmd == "pillars":
                _check_pillars_interactive(args)
            elif cmd == "risk":
                _calculate_risk(args)
            elif cmd == "sectors":
                _run_sectors()
            elif cmd == "journal":
                _run_journal()
            elif cmd == "log":
                _log_trade_interactive()
            elif cmd == "profile":
                _show_profile()
            elif cmd == "status":
                _show_status()
            elif cmd == "intel":
                _run_intel()
            else:
                # Treat as a ticker
                if cmd.isalpha() and len(cmd) <= 5:
                    _analyze([cmd.upper()])
                else:
                    print(f"Unknown command: {cmd}. Type 'help' for commands.")
        except Exception as e:
            print(f"Error: {e}")


def _show_help():
    print("""
Commands:
  analyze AAPL      Full analysis (indicators + patterns + strategies)
  scan              Run full scan on watchlist
  day               Day trade scan (intraday)
  swing             Swing trade scan (daily)
  watchlist         Show current watchlist
  add TSLA          Add to watchlist
  remove MSFT       Remove from watchlist
  rsi AAPL          RSI analysis + options signals
  candles AAPL      Candlestick pattern detection
  pillars AAPL      Day trade 5 Pillars check
  risk AAPL 175     Position size calculator
  sectors           Sector rotation report
  journal           Weekly trade journal review
  log               Log a trade interactively
  profile           Show risk profile
  status            Account & position status
  intel             Intelligence scan (whales, earnings)
  help              Show this help
  quit              Exit

Tips:
  - Just type a ticker (e.g. AAPL) for quick analysis
  - Your watchlist updates are saved to config.yaml
""")


def _show_status_brief():
    """Quick status on startup."""
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])
    print(f"Watchlist: {', '.join(watchlist)}")

    try:
        from bot.engine.risk_manager import RiskManager
        rm = RiskManager()
        p = rm.profile
        print(f"Capital: ${p.current_capital:,.2f} | Risk: {p.risk_level} ({p.risk_per_trade_pct}%/trade) | "
              f"Daily P&L: ${p.daily_pnl:+.2f}")
    except Exception:
        pass


def _analyze(args):
    """Full analysis on a ticker."""
    if not args:
        print("Usage: analyze AAPL")
        return

    symbol = args[0].upper()
    interval = args[1] if len(args) > 1 else "1d"

    print(f"\nAnalyzing {symbol} ({interval})...")

    from bot.engine.analyzer import _fetch_candles
    from bot.data.indicators import compute_indicators
    from bot.data.candle_patterns import detect_patterns, get_pattern_summary
    from bot.data.models import MarketSnapshot
    from bot.strategies.registry import StrategyRegistry
    from bot.engine.sector_rotation import get_sector_for_stock

    candles = _fetch_candles(symbol, interval=interval)
    if len(candles) < 26:
        print(f"Not enough data for {symbol} ({len(candles)} candles)")
        return

    ind = compute_indicators(candles)
    patterns = detect_patterns(candles[-5:])
    latest = candles[-1]

    # Price info
    change_icon = "+" if ind.day_change_pct >= 0 else ""
    print(f"\n{'='*50}")
    print(f"  {symbol}  ${latest.close:.2f}  {change_icon}{ind.day_change_pct:.2f}%")
    print(f"{'='*50}")

    # Key indicators
    print(f"\n  Indicators:")
    print(f"    RSI:    {ind.rsi_14:.1f}  {'(OVERSOLD)' if ind.rsi_14 < 30 else '(OVERBOUGHT)' if ind.rsi_14 > 70 else ''}")
    print(f"    MACD:   {'Bullish' if ind.macd_line > ind.macd_signal else 'Bearish'} (line: {ind.macd_line:.4f}, signal: {ind.macd_signal:.4f})")
    print(f"    VWAP:   ${ind.vwap:.2f}  {'(above)' if latest.close > ind.vwap else '(below)'}")
    print(f"    8 EMA:  ${ind.ema_8:.2f}  {'(riding)' if abs(latest.close - ind.ema_8) / ind.ema_8 < 0.02 else ''}")
    if ind.sma_200 > 0:
        print(f"    200 SMA: ${ind.sma_200:.2f}  {'(above - bullish)' if latest.close > ind.sma_200 else '(below - bearish)'}")
    print(f"    RVOL:   {ind.relative_volume:.1f}x")
    print(f"    ATR:    ${ind.atr_14:.2f}")
    print(f"    BB:     ${ind.bb_lower:.2f} / ${ind.bb_middle:.2f} / ${ind.bb_upper:.2f}")

    # Candle patterns
    if patterns:
        print(f"\n  Candle Patterns:")
        for p in patterns:
            icon = "^" if p.direction == "bullish" else "v" if p.direction == "bearish" else "-"
            print(f"    {icon} {p.name} ({p.direction}) — {p.description}")
    else:
        print(f"\n  Candle Patterns: None detected")

    # Sector info
    sector = get_sector_for_stock(symbol)
    if sector:
        print(f"\n  Sector: {sector}")

    # Run strategies
    snapshot = MarketSnapshot(symbol=symbol, timeframe=interval, candles=candles, indicators=ind)
    registry = StrategyRegistry()
    registry.load_builtins()

    signals = []
    for strategy in registry.get_all():
        try:
            signal = strategy.analyze(snapshot)
            if signal and signal.confidence >= 0.5:
                signals.append(signal)
        except Exception:
            pass

    if signals:
        print(f"\n  Signals:")
        for s in signals:
            style = f"[{s.style}] " if s.style else ""
            setup = f"({s.setup}) " if s.setup else ""
            rr = f"R:R {s.risk_reward:.1f}:1 " if s.risk_reward else ""
            color_marker = ">>>" if s.action == "BUY" else "<<<" if s.action == "SELL" else "---"
            print(f"    {color_marker} {s.action} {style}{setup}— {s.strategy_name} ({s.confidence:.0%}) {rr}")
            if s.stop_loss:
                print(f"        Stop: ${s.stop_loss:.2f} | Target: ${s.target:.2f}")
            for r in s.reasons[:3]:
                print(f"        - {r}")
    else:
        print(f"\n  Signals: No trade signals at current levels")

    # Options RSI guidance
    print(f"\n  Options Guidance (RSI {ind.rsi_14:.1f}):")
    if ind.rsi_14 < 30:
        print(f"    -> Sell cash-secured puts or buy calls (oversold)")
    elif ind.rsi_14 > 70:
        print(f"    -> Sell covered calls or buy puts (overbought)")
    elif 40 < ind.rsi_14 < 60:
        print(f"    -> Neutral zone — iron condors work well here")
    else:
        print(f"    -> No strong RSI signal")

    print()


def _run_scan():
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    analyzer.run_scan()


def _run_day_scan():
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    interval = CONFIG.get("data", {}).get("intraday_interval", "5m")
    analyzer.run_day_scan(interval=interval)


def _run_swing_scan():
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    analyzer.run_swing_scan()


def _show_watchlist():
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])
    print(f"\nWatchlist ({len(watchlist)} symbols):")
    for sym in watchlist:
        print(f"  {sym}")
    print(f"\nUse 'add TSLA' or 'remove MSFT' to update.")


def _add_to_watchlist(args):
    if not args:
        print("Usage: add TSLA")
        return

    symbol = args[0].upper()
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])

    if symbol in watchlist:
        print(f"{symbol} is already in watchlist")
        return

    watchlist.append(symbol)
    CONFIG["bot"]["watchlist"] = watchlist
    _save_config()
    print(f"Added {symbol} to watchlist: {', '.join(watchlist)}")


def _remove_from_watchlist(args):
    if not args:
        print("Usage: remove MSFT")
        return

    symbol = args[0].upper()
    watchlist = CONFIG.get("bot", {}).get("watchlist", [])

    if symbol not in watchlist:
        print(f"{symbol} is not in watchlist")
        return

    watchlist.remove(symbol)
    CONFIG["bot"]["watchlist"] = watchlist
    _save_config()
    print(f"Removed {symbol}. Watchlist: {', '.join(watchlist)}")


def _save_config():
    """Save current config back to config.yaml."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(CONFIG, f, default_flow_style=False, sort_keys=False)


def _check_rsi(args):
    """RSI analysis with options guidance."""
    if not args:
        print("Usage: rsi AAPL")
        return

    symbol = args[0].upper()
    print(f"\nRSI Analysis: {symbol}")

    from bot.engine.analyzer import _fetch_candles
    from bot.data.indicators import compute_indicators

    candles = _fetch_candles(symbol, interval="1d")
    if len(candles) < 26:
        print("Not enough data")
        return

    ind = compute_indicators(candles)
    price = candles[-1].close

    print(f"  Price: ${price:.2f}")
    print(f"  RSI(14): {ind.rsi_14:.1f}")
    print(f"  BB: ${ind.bb_lower:.2f} / ${ind.bb_middle:.2f} / ${ind.bb_upper:.2f}")
    if ind.sma_50 > 0:
        print(f"  50 SMA: ${ind.sma_50:.2f}")

    # Options signals from the skill
    print(f"\n  Options Signals:")
    at_lower_bb = price <= ind.bb_lower * 1.01 if ind.bb_lower > 0 else False
    at_upper_bb = price >= ind.bb_upper * 0.99 if ind.bb_upper > 0 else False
    above_50 = price > ind.sma_50 if ind.sma_50 > 0 else False

    if ind.rsi_14 < 30:
        if at_lower_bb and above_50:
            print(f"    >>> VERY STRONG BUY SIGNAL <<<")
            print(f"    RSI oversold + lower BB + above 50 SMA")
        print(f"    -> Sell cash-secured puts (20-30 delta, 30-45 DTE)")
        print(f"    -> Buy calls (ATM or slightly OTM)")
        if ind.rsi_14 < 20:
            print(f"    -> RSI at {ind.rsi_14:.1f} — extreme oversold, high conviction")
    elif ind.rsi_14 > 70:
        if at_upper_bb:
            print(f"    >>> STRONG SELL SIGNAL <<<")
            print(f"    RSI overbought + upper BB")
        print(f"    -> Sell covered calls (20-30 delta, 30-45 DTE)")
        print(f"    -> Buy puts if expecting pullback")
    elif 40 < ind.rsi_14 < 60:
        print(f"    -> Neutral RSI — range-bound strategies work here")
        print(f"    -> Iron condors at Bollinger Band strikes")
        print(f"    -> Short leg at BB, buy $5 outside")
    else:
        print(f"    -> No strong RSI signal at {ind.rsi_14:.1f}")


def _check_candles(args):
    """Detect candle patterns."""
    if not args:
        print("Usage: candles AAPL")
        return

    symbol = args[0].upper()
    interval = args[1] if len(args) > 1 else "1d"

    from bot.engine.analyzer import _fetch_candles
    from bot.data.candle_patterns import detect_patterns

    candles = _fetch_candles(symbol, interval=interval)
    if len(candles) < 5:
        print("Not enough data")
        return

    latest = candles[-1]
    print(f"\n{symbol} ({interval}) — O:{latest.open:.2f} H:{latest.high:.2f} L:{latest.low:.2f} C:{latest.close:.2f}")

    patterns = detect_patterns(candles[-5:])
    if patterns:
        for p in patterns:
            icon = "^" if p.direction == "bullish" else "v" if p.direction == "bearish" else "-"
            print(f"  {icon} {p.name} ({p.direction}, strength: {p.strength:.0%})")
            print(f"    {p.description}")
    else:
        print("  No significant patterns detected")


def _check_pillars_interactive(args):
    """Interactive 5 Pillars check."""
    if not args:
        print("Usage: pillars AAPL")
        return

    symbol = args[0].upper()
    print(f"\n5 Pillars Day Trade Check: {symbol}")

    # Try to auto-fetch data
    from bot.engine.analyzer import _fetch_candles
    from bot.data.indicators import compute_indicators

    try:
        candles = _fetch_candles(symbol, interval="1d", days=60)
        if len(candles) >= 26:
            ind = compute_indicators(candles)
            price = candles[-1].close
            change = ind.day_change_pct
            rvol = ind.relative_volume
            print(f"  Auto-detected: Price ${price:.2f}, Change {change:+.1f}%, RVOL {rvol:.1f}x")
        else:
            price = float(input("  Price: $").strip())
            change = float(input("  Day change %: ").strip())
            rvol = float(input("  Relative volume (x): ").strip())
    except Exception:
        price = float(input("  Price: $").strip())
        change = float(input("  Day change %: ").strip())
        rvol = float(input("  Relative volume (x): ").strip())

    catalyst = input("  Catalyst (news): ").strip()
    float_m = input("  Float (M shares, Enter if unknown): ").strip()
    float_m = float(float_m) if float_m else 0

    from bot.engine.day_scanner import check_five_pillars

    c = check_five_pillars(symbol, price, change, rvol, catalyst, float_m)

    print(f"\n  Result: {c.pillars_met}/5 Pillars {'PASS' if c.passed else 'FAIL'}")
    print(f"  Catalyst Tier: {c.catalyst_tier}")
    for key, info in c.pillar_details.items():
        icon = "+" if info["met"] else "x"
        print(f"    [{icon}] {key}: {info['value']}", end="")
        if not info["met"] and "need" in info:
            print(f" (need: {info['need']})", end="")
        print()


def _calculate_risk(args):
    """Position size calculator."""
    if len(args) < 2:
        print("Usage: risk AAPL 175.50")
        return

    symbol = args[0].upper()
    price = float(args[1])
    confidence = float(args[2]) if len(args) > 2 else 0.65

    from bot.engine.risk_manager import RiskManager
    rm = RiskManager()
    result = rm.calculate_position_size(symbol, price, confidence=confidence)

    print(f"\n  Position Size: {symbol} @ ${price:.2f}")
    if result["can_trade"]:
        print(f"    Shares: {result['shares']}")
        print(f"    Position Value: ${result['position_value']:.2f}")
        print(f"    Risk Amount: ${result['risk_amount']:.2f} ({result.get('risk_pct_of_capital', 0):.1f}% of capital)")
        print(f"    Stop Loss: ${result['stop_loss_price']:.2f} ({result.get('stop_loss_pct', 0):.1f}%)")
        print(f"    Take Profit: ${result['take_profit_price']:.2f}")
        print(f"    R:R: {result['reward_risk_ratio']:.1f}:1")
    else:
        print(f"    BLOCKED: {result['reason']}")


def _run_sectors():
    """Sector rotation (delegates to main)."""
    from bot.main import run_sectors
    run_sectors()


def _run_journal():
    """Journal review (delegates to main)."""
    from bot.main import run_journal
    run_journal()


def _run_intel():
    """Intelligence scan."""
    from bot.main import run_intel
    run_intel()


def _log_trade_interactive():
    """Log a trade interactively."""
    from bot.engine.trade_journal import log_trade, JournalEntry

    print("\n--- Log Trade ---")
    symbol = input("  Symbol: ").strip().upper()
    if not symbol:
        return

    style = input("  Style (day/swing/options): ").strip() or "day"
    direction = input("  Direction (long/short): ").strip() or "long"
    setup = input("  Setup (e.g. Pullback, VWAP Reclaim): ").strip()
    entry_price = float(input("  Entry price: $").strip())
    shares = input("  Shares: ").strip()
    shares = float(shares) if shares else 0
    stop_loss = input("  Stop loss: $").strip()
    stop_loss = float(stop_loss) if stop_loss else 0
    target = input("  Target: $").strip()
    target = float(target) if target else 0
    catalyst = input("  Catalyst: ").strip()
    why = input("  Why entering: ").strip()

    entry = JournalEntry(
        symbol=symbol, style=style, direction=direction,
        setup=setup, entry_price=entry_price, shares=shares,
        stop_loss=stop_loss, target=target, catalyst=catalyst,
        why_entered=why,
    )
    if stop_loss > 0 and target > 0:
        risk = abs(entry_price - stop_loss)
        reward = abs(target - entry_price)
        entry.risk_reward_planned = round(reward / risk, 1) if risk > 0 else 0

    entry_id = log_trade(entry)
    print(f"\n  Trade logged! ID: {entry_id}")
    if entry.risk_reward_planned:
        print(f"  R:R: {entry.risk_reward_planned}:1")
    if entry.risk_reward_planned > 0 and entry.risk_reward_planned < 2.0:
        print(f"  WARNING: R:R below 2:1 minimum — consider skipping this trade")


def _show_profile():
    """Show risk profile."""
    from bot.engine.risk_manager import RiskManager
    rm = RiskManager()
    p = rm.profile
    status = rm.get_status()

    print(f"\n  === Trading Profile ===")
    print(f"    Capital:          ${p.current_capital:,.2f}")
    print(f"    Risk Level:       {p.risk_level.capitalize()}")
    print(f"    Risk Per Trade:   {p.risk_per_trade_pct}% (${p.risk_per_trade_dollars():.2f})")
    print(f"    Risk Multiplier:  {p.risk_multiplier}x")
    print(f"    Max Day Trades:   {p.max_day_trades}")
    print(f"    Max Swing Trades: {p.max_swing_trades}")
    print(f"    Daily Loss Limit: {p.daily_loss_limit_pct}%")
    print(f"    Min R:R:          {p.min_risk_reward}:1")
    print(f"    Options Max:      {p.options_max_pct}%")

    if p.total_trades > 0:
        print(f"\n    --- Performance ---")
        print(f"    Trades: {p.total_trades} ({p.winning_trades}W/{p.losing_trades}L)")
        print(f"    Win Rate: {p.win_rate:.1%}")
        print(f"    Total P&L: ${p.total_pnl:+,.2f}")
        print(f"    Growth: {p.growth_pct:+.1f}%")
        print(f"    Streak: {'+' if p.current_streak > 0 else ''}{p.current_streak}")
        print(f"    Drawdown: {p.drawdown_pct:.1f}%")

    print(f"\n    Can trade today: {'Yes' if status['can_trade_today'] else 'NO (daily limit hit)'}")
    print(f"    Can trade week:  {'Yes' if status['can_trade_week'] else 'NO (weekly limit hit)'}")


def _show_status():
    """Show account status and positions."""
    _show_profile()

    # Try to show Alpaca positions
    try:
        from bot.engine.trader import get_account_info, get_positions
        account = get_account_info()
        if "error" not in account:
            print(f"\n    --- Alpaca Account ---")
            print(f"    Equity: ${float(account.get('equity', 0)):,.2f}")
            print(f"    Buying Power: ${float(account.get('buying_power', 0)):,.2f}")
            print(f"    Day Trades Left: {account.get('day_trades_remaining', 'N/A')}")

        positions = get_positions()
        if positions:
            print(f"\n    --- Open Positions ({len(positions)}) ---")
            for pos in positions:
                pnl = float(pos.get("unrealized_pnl", 0))
                pnl_icon = "+" if pnl >= 0 else ""
                print(f"    {pos['symbol']:6s} {pos.get('qty', 0):>6} shares @ ${float(pos.get('avg_entry', 0)):>8.2f}  P&L: {pnl_icon}${pnl:.2f}")
        else:
            print(f"\n    No open positions")
    except Exception:
        print(f"\n    (Connect Alpaca for live positions — run 'setup')")
