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

        # Send Discord summary of all signals from this scan
        all_signals = [s for sigs in results.values() for s in sigs]
        if all_signals:
            try:
                from bot.alerts.discord import DiscordChannel
                discord = DiscordChannel()
                discord.send_summary(all_signals)
            except Exception:
                pass

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

        print(f"Swing scan complete. {sum(len(s) for s in results.values())} signals.\n")
        return results
