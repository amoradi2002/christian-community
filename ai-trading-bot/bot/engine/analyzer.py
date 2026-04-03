"""
Core Analyzer - Orchestrates data fetching, strategy evaluation, AI prediction, and alerts.
Supports both Yahoo Finance (free/delayed) and Alpaca (real-time) data providers.

Enhanced with trading skill framework:
- Candlestick pattern detection on every scan
- Day trade and swing trade specific scans
- Sector rotation awareness
- Trade analysis template in alerts
"""

from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot
from bot.data.candle_patterns import detect_patterns, get_pattern_summary
from bot.strategies.registry import StrategyRegistry
from bot.ai.predictor import predict_signal
from bot.alerts.manager import AlertManager
from bot.engine.signal import Signal
from bot.engine.performance import record_signal
from bot.strategies.store import get_strategy_by_name
from bot.config.settings import CONFIG


def _fetch_candles(symbol: str, interval: str = "1d", days: int = 365) -> list:
    """Fetch candles using the configured data provider."""
    provider = CONFIG.get("data", {}).get("provider", "yfinance")

    if provider == "alpaca":
        try:
            from bot.data.alpaca_provider import fetch_alpaca_bars
            return fetch_alpaca_bars(symbol, interval=interval, days=days)
        except (ImportError, ValueError) as e:
            print(f"Alpaca unavailable ({e}), falling back to yfinance")

    # Fallback to yfinance
    from bot.data.fetcher import fetch_market_data
    period_map = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "1y"}
    period = period_map.get(interval, "1y")
    return fetch_market_data(symbol, period=period, interval=interval)


class Analyzer:
    def __init__(self):
        self.registry = StrategyRegistry()
        self.registry.load_all()
        self.alert_manager = AlertManager()
        self.threshold = CONFIG.get("bot", {}).get("confidence_threshold", 0.65)
        self.provider = CONFIG.get("data", {}).get("provider", "yfinance")

    def analyze_symbol(self, symbol: str, interval: str = "1d") -> list[Signal]:
        """Run full analysis pipeline on a single symbol."""
        # 1. Fetch data (auto-selects Alpaca or Yahoo based on config)
        candles = _fetch_candles(symbol, interval=interval)
        if len(candles) < 30:
            print(f"[{symbol}] Not enough data ({len(candles)} candles)")
            return []

        # 2. Compute indicators
        indicators = compute_indicators(candles)

        # 3. Build snapshot
        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=interval,
            candles=candles,
            indicators=indicators,
        )

        # 4. Detect candlestick patterns
        patterns = detect_patterns(candles[-5:])

        signals = []

        # 5. Run all strategies
        for strategy in self.registry.get_all():
            try:
                signal = strategy.analyze(snapshot)
                if signal and signal.confidence >= self.threshold:
                    # Enrich signal with candle pattern info if not already set
                    if not signal.candle_pattern and patterns:
                        best_pattern = max(patterns, key=lambda p: p.strength)
                        signal.candle_pattern = best_pattern.name
                    signals.append(signal)
            except Exception as e:
                print(f"[{symbol}] Strategy {strategy.name} error: {e}")

        # 6. Run AI prediction
        try:
            ai_signal = predict_signal(snapshot)
            if ai_signal and ai_signal.confidence >= self.threshold:
                signals.append(ai_signal)
        except Exception:
            pass  # AI model might not be trained yet

        # 7. Dispatch alerts and record performance
        for signal in signals:
            strategy_row = get_strategy_by_name(signal.strategy_name)
            strategy_id = strategy_row["id"] if strategy_row else None

            self.alert_manager.dispatch(signal, strategy_id=strategy_id)

            if signal.action in ("BUY", "SELL") and strategy_id:
                record_signal(strategy_id, symbol, signal.action, signal.price)

        return signals

    def run_scan(self) -> dict[str, list[Signal]]:
        """Scan all watchlist symbols."""
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        results = {}

        print(f"\nScanning {len(watchlist)} symbols...")
        for symbol in watchlist:
            try:
                signals = self.analyze_symbol(symbol)
                if signals:
                    results[symbol] = signals
                    for s in signals:
                        style_tag = f" [{s.style}]" if s.style else ""
                        setup_tag = f" ({s.setup})" if s.setup else ""
                        rr_tag = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                        print(f"  [{symbol}] {s.action}{style_tag}{setup_tag}{rr_tag} — {s.strategy_name} ({s.confidence:.0%})")
                else:
                    print(f"  [{symbol}] No signals")
            except Exception as e:
                print(f"  [{symbol}] Error: {e}")

        # Send alerts to all channels (Discord + Telegram)
        all_signals = [s for sigs in results.values() for s in sigs]
        self._dispatch_alerts(all_signals, scan_type="Full")

        print(f"Scan complete. {sum(len(s) for s in results.values())} total signals.\n")
        return results

    def run_day_scan(self, interval: str = "5m") -> dict[str, list[Signal]]:
        """Run day-trade-specific scan using intraday data."""
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        results = {}

        print(f"\nDay Trade Scan ({interval}) on {len(watchlist)} symbols...")
        day_strategies = self.registry.get_by_style("day")

        for symbol in watchlist:
            try:
                candles = _fetch_candles(symbol, interval=interval, days=7)
                if len(candles) < 10:
                    continue

                indicators = compute_indicators(candles)
                snapshot = MarketSnapshot(
                    symbol=symbol, timeframe=interval,
                    candles=candles, indicators=indicators,
                )

                signals = []
                for strategy in day_strategies:
                    try:
                        signal = strategy.analyze(snapshot)
                        if signal and signal.confidence >= self.threshold:
                            signals.append(signal)
                    except Exception as e:
                        print(f"  [{symbol}] {strategy.name} error: {e}")

                if signals:
                    results[symbol] = signals
                    for s in signals:
                        print(f"  [{symbol}] {s.action} [{s.setup}] R:R {s.risk_reward:.1f}:1 ({s.confidence:.0%})")
            except Exception as e:
                print(f"  [{symbol}] Error: {e}")

        all_signals = [s for sigs in results.values() for s in sigs]
        for s in all_signals:
            s.broker = "interactive_brokers"
        self._dispatch_alerts(all_signals, scan_type="Day Trade")

        print(f"Day scan complete. {sum(len(s) for s in results.values())} signals.\n")
        return results

    def run_swing_scan(self) -> dict[str, list[Signal]]:
        """Run swing-trade-specific scan using daily data."""
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        results = {}

        print(f"\nSwing Trade Scan on {len(watchlist)} symbols...")
        swing_strategies = self.registry.get_by_style("swing")

        for symbol in watchlist:
            try:
                candles = _fetch_candles(symbol, interval="1d", days=365)
                if len(candles) < 50:
                    continue

                indicators = compute_indicators(candles)
                snapshot = MarketSnapshot(
                    symbol=symbol, timeframe="1d",
                    candles=candles, indicators=indicators,
                )

                signals = []
                for strategy in swing_strategies:
                    try:
                        signal = strategy.analyze(snapshot)
                        if signal and signal.confidence >= self.threshold:
                            signals.append(signal)
                    except Exception as e:
                        print(f"  [{symbol}] {strategy.name} error: {e}")

                if signals:
                    results[symbol] = signals
                    for s in signals:
                        print(f"  [{symbol}] {s.action} [{s.setup}] R:R {s.risk_reward:.1f}:1 ({s.confidence:.0%})")
            except Exception as e:
                print(f"  [{symbol}] Error: {e}")

        all_signals = [s for sigs in results.values() for s in sigs]
        for s in all_signals:
            s.broker = "fidelity"
        self._dispatch_alerts(all_signals, scan_type="Swing Trade")

        print(f"Swing scan complete. {sum(len(s) for s in results.values())} signals.\n")
        return results

    def run_options_scan(self) -> dict[str, list[Signal]]:
        """Run options-specific scan — finds high-probability options plays.

        Combines technical signals with options flow data to generate
        call/put recommendations with strike, expiry, and premium.
        """
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        results = {}

        print(f"\nOptions Scan on {len(watchlist)} symbols...")

        for symbol in watchlist:
            try:
                candles = _fetch_candles(symbol, interval="1d", days=60)
                if len(candles) < 20:
                    continue

                indicators = compute_indicators(candles)
                snapshot = MarketSnapshot(
                    symbol=symbol, timeframe="1d",
                    candles=candles, indicators=indicators,
                )

                signals = []
                # Run all strategies, then convert strong signals to options calls
                all_strategies = self.registry.get_all()
                for strategy in all_strategies:
                    try:
                        signal = strategy.analyze(snapshot)
                        if signal and signal.confidence >= 0.70:  # Higher bar for options
                            opt_signal = self._convert_to_options_signal(signal, candles, indicators)
                            if opt_signal:
                                signals.append(opt_signal)
                    except Exception as e:
                        print(f"  [{symbol}] {strategy.name} error: {e}")

                if signals:
                    results[symbol] = signals
                    for s in signals:
                        opt = (s.option_type or "call").upper()
                        strike_str = f"${s.strike:.0f}" if s.strike else "ATM"
                        print(f"  [{symbol}] {opt} {strike_str} {s.expiry} @ ${s.premium:.2f} ({s.confidence:.0%})")
            except Exception as e:
                print(f"  [{symbol}] Error: {e}")

        all_signals = [s for sigs in results.values() for s in sigs]
        for s in all_signals:
            s.broker = "robinhood"
        self._dispatch_alerts(all_signals, scan_type="Options")

        print(f"Options scan complete. {sum(len(s) for s in results.values())} signals.\n")
        return results

    def _convert_to_options_signal(self, signal: Signal, candles, indicators) -> Signal | None:
        """Convert a stock signal into an options recommendation."""
        if not candles:
            return None

        price = candles[-1].close
        atr = indicators.atr_14 if indicators.atr_14 else price * 0.02

        # Determine option type from signal
        if signal.action == "BUY":
            option_type = "call"
            # Strike: slightly OTM for leverage, or ATM for higher probability
            if signal.confidence >= 0.80:
                strike = round(price, 0)  # ATM for high confidence
            else:
                strike = round(price * 1.02, 0)  # Slightly OTM
        elif signal.action == "SELL":
            option_type = "put"
            if signal.confidence >= 0.80:
                strike = round(price, 0)
            else:
                strike = round(price * 0.98, 0)
        else:
            return None

        # Expiry: 2-4 weeks out for swing, 1 week for day
        from datetime import datetime, timedelta
        today = datetime.now()
        if signal.style == "day":
            # Weekly expiry (next Friday)
            days_to_friday = (4 - today.weekday()) % 7
            if days_to_friday == 0:
                days_to_friday = 7
            expiry_date = today + timedelta(days=days_to_friday)
        else:
            # 3 weeks out for swing
            expiry_date = today + timedelta(days=21)
            # Round to next Friday
            days_to_friday = (4 - expiry_date.weekday()) % 7
            expiry_date += timedelta(days=days_to_friday)

        expiry = expiry_date.strftime("%Y-%m-%d")

        # Estimate premium using ATR as a rough proxy
        # Real premium would come from options chain API
        estimated_premium = round(atr * 0.5, 2)

        # Calculate suggested contracts based on risk
        try:
            from bot.engine.risk_manager import RiskManager
            rm = RiskManager()
            max_risk = rm.profile.risk_per_trade_dollars()
            if estimated_premium > 0:
                contracts = max(1, int(max_risk / (estimated_premium * 100)))
            else:
                contracts = 1
        except Exception:
            contracts = 1

        reasons = list(signal.reasons)
        reasons.append(f"Options play: {option_type.upper()} ${strike:.0f} exp {expiry}")
        if signal.stop_loss:
            reasons.append(f"Exit if stock breaks ${signal.stop_loss:.2f}")

        return Signal(
            action=signal.action,
            confidence=signal.confidence,
            strategy_name=signal.strategy_name,
            symbol=signal.symbol,
            price=price,
            reasons=reasons,
            style="options",
            setup=signal.setup,
            stop_loss=signal.stop_loss,
            target=signal.target,
            target_price=signal.target_price,
            risk_reward=signal.risk_reward,
            catalyst=signal.catalyst,
            catalyst_tier=signal.catalyst_tier,
            candle_pattern=signal.candle_pattern,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            premium=estimated_premium,
            contracts=contracts,
            broker="robinhood",
        )

    def _dispatch_alerts(self, signals: list[Signal], scan_type: str = "Full"):
        """Send trade calls to Discord (labeled by type: options/day/swing).

        Discord = automatic trade calls (the bread-making alerts)
        Telegram = interactive agent chat (user types/asks questions)
        """
        if not signals:
            return

        # Discord gets ALL the calls — options, day, swing — properly labeled
        try:
            from bot.alerts.discord import DiscordChannel
            discord = DiscordChannel()
            # Send individual embeds for each signal (labeled by type)
            for s in signals:
                discord.send(s)
            # Also send the summary
            discord.send_summary(signals)
        except Exception:
            pass
