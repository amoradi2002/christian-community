"""
RSI + Bollinger Band Combined Strategy

From the trading skill:
- RSI < 30 = oversold -> sell puts / buy calls
- RSI > 70 = overbought -> sell covered calls / buy puts
- RSI near 20 on quality stock = high-conviction entry
- Combined signal: Stock at lower BB + RSI < 30 + above 50-day MA = very strong entry

Also includes options-specific RSI signals:
- RSI under 30: Sell cash-secured puts or buy calls
- RSI over 70: Sell covered calls or buy puts
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal
from bot.data.candle_patterns import detect_patterns


class RSIReversalStrategy(Strategy):
    name = "RSI Reversal"
    description = "Buy when RSI < 30 (oversold), Sell when RSI > 70 (overbought) with options guidance"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        rsi = ind.rsi_14
        price = snapshot.latest.close

        if rsi <= 30:
            reasons = [f"RSI oversold at {rsi:.1f}"]
            confidence = min(0.5 + (30 - rsi) / 60, 0.95)
            style = "swing"

            # Combined signal: RSI < 30 + lower BB + above 50 SMA = very strong
            at_lower_bb = price <= ind.bb_lower * 1.01 if ind.bb_lower > 0 else False
            above_50_sma = price > ind.sma_50 if ind.sma_50 > 0 else False

            if at_lower_bb and above_50_sma:
                confidence = min(confidence + 0.15, 0.95)
                reasons.append(f"At lower Bollinger Band (${ind.bb_lower:.2f}) + above 50 SMA — VERY STRONG entry")
                reasons.append("Options: Sell cash-secured puts at current strike or buy calls")
            elif at_lower_bb:
                confidence = min(confidence + 0.1, 0.95)
                reasons.append(f"At lower Bollinger Band (${ind.bb_lower:.2f})")
                reasons.append("Options: Consider selling puts for income")
            elif above_50_sma:
                reasons.append(f"Above 50 SMA (${ind.sma_50:.2f}) — institutional support")
                reasons.append("Options: Buy calls or sell cash-secured puts")

            # RSI near 20 = high conviction
            if rsi <= 20:
                confidence = min(confidence + 0.1, 0.95)
                reasons.append(f"RSI at {rsi:.1f} — extreme oversold, high-conviction entry")

            # Check for bullish candle pattern confirmation
            patterns = detect_patterns(snapshot.candles[-5:])
            bullish = [p for p in patterns if p.direction == "bullish"]
            if bullish:
                confidence = min(confidence + 0.05, 0.95)
                reasons.append(f"Candle confirms: {bullish[0].name}")

            # Calculate trade levels
            stop_loss = ind.bb_lower * 0.97 if ind.bb_lower > 0 else price * 0.95
            target = ind.bb_middle if ind.bb_middle > 0 else price * 1.05
            risk = price - stop_loss
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            return Signal(
                action="BUY",
                confidence=confidence,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=reasons,
                style=style,
                setup="RSI Oversold" + (" + BB + 50 SMA" if at_lower_bb and above_50_sma else ""),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                risk_reward=round(rr, 1) if rr > 0 else 0,
            )

        elif rsi >= 70:
            reasons = [f"RSI overbought at {rsi:.1f}"]
            confidence = min(0.5 + (rsi - 70) / 60, 0.95)

            # At upper BB = stronger signal
            at_upper_bb = price >= ind.bb_upper * 0.99 if ind.bb_upper > 0 else False
            if at_upper_bb:
                confidence = min(confidence + 0.1, 0.95)
                reasons.append(f"At upper Bollinger Band (${ind.bb_upper:.2f})")
                reasons.append("Options: Sell covered calls at current level")
            else:
                reasons.append("Options: Consider selling covered calls or buying puts")

            # Check bearish candle patterns
            patterns = detect_patterns(snapshot.candles[-5:])
            bearish = [p for p in patterns if p.direction == "bearish"]
            if bearish:
                confidence = min(confidence + 0.05, 0.95)
                reasons.append(f"Candle confirms: {bearish[0].name}")

            stop_loss = ind.bb_upper * 1.03 if ind.bb_upper > 0 else price * 1.05
            target = ind.bb_middle if ind.bb_middle > 0 else price * 0.95
            risk = stop_loss - price
            reward = price - target
            rr = reward / risk if risk > 0 else 0

            return Signal(
                action="SELL",
                confidence=confidence,
                strategy_name=self.name,
                symbol=snapshot.symbol,
                price=price,
                reasons=reasons,
                style="swing",
                setup="RSI Overbought" + (" + Upper BB" if at_upper_bb else ""),
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                risk_reward=round(rr, 1) if rr > 0 else 0,
            )

        return None

    def to_dict(self):
        return {"name": self.name, "type": "builtin", "params": {"oversold": 30, "overbought": 70}}

    @classmethod
    def from_dict(cls, data):
        return cls()
