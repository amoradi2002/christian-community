"""
Core Analyzer - Orchestrates data fetching, strategy evaluation, AI prediction, and alerts.
Supports both Yahoo Finance (free/delayed) and Alpaca (real-time) data providers.
"""

from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot
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

        signals = []

        # 4. Run all strategies
        for strategy in self.registry.get_all():
            try:
                signal = strategy.analyze(snapshot)
                if signal and signal.confidence >= self.threshold:
                    signals.append(signal)
            except Exception as e:
                print(f"[{symbol}] Strategy {strategy.name} error: {e}")

        # 5. Run AI prediction
        try:
            ai_signal = predict_signal(snapshot)
            if ai_signal and ai_signal.confidence >= self.threshold:
                signals.append(ai_signal)
        except Exception:
            pass  # AI model might not be trained yet

        # 6. Dispatch alerts and record performance
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
                    print(f"  [{symbol}] {len(signals)} signal(s)")
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
