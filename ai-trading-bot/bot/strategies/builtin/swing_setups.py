"""
Swing Trading Setups from the Trading Skill

3 Core Swing Setups:
1. Daily Gap Up Through Multi-Month Resistance
   - Entry: pullback to 8 EMA (don't chase the open)
   - Stop: below 8 EMA support
   - Target: next resistance levels

2. Long-Term Downtrend Break
   - Stock breaks above multi-month downtrend + reclaims 200 SMA on high volume
   - Entry: on or above 200 SMA after trendline break
   - Stop: below the breakout / recent support

3. Oversold Bounce
   - Quality stock drops 20%+ below 200 SMA on recoverable catalyst
   - Entry: first daily close above 8 EMA
   - Stop: low of entry candle
   - R:R must be 3:1+

Key indicators: 8 EMA (trend), 200 SMA (institutional support), Volume confirmation
"""

from bot.strategies.base import Strategy
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal


class SwingEMAPullbackStrategy(Strategy):
    """
    Setup 1: Gap up through resistance, then pullback to 8 EMA.
    Stock riding close to 8 EMA = healthy uptrend.
    """
    name = "Swing: 8 EMA Pullback"
    description = "Buy on pullback to 8 EMA in uptrend above 200 SMA"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        candles = snapshot.candles
        if len(candles) < 20 or ind.ema_8 == 0 or ind.sma_200 == 0:
            return None

        price = snapshot.latest.close

        # Must be above 200 SMA (bullish, institutionally supported)
        if price < ind.sma_200:
            return None

        # Price should be near 8 EMA (pullback)
        distance_from_ema = abs(price - ind.ema_8) / ind.ema_8 * 100
        if distance_from_ema > 3:
            return None  # Too far from 8 EMA

        # Confirm uptrend: 8 EMA above 200 SMA
        if ind.ema_8 < ind.sma_200:
            return None

        # Recent pullback: price was above, dipped to 8 EMA
        above_ema_recently = any(c.close > ind.ema_8 * 1.02 for c in candles[-10:-2])
        if not above_ema_recently:
            return None

        # Current candle should be recovering (green, at or above 8 EMA)
        latest = snapshot.latest
        if latest.close < latest.open:
            return None
        if latest.close < ind.ema_8 * 0.99:
            return None

        # Volume confirmation
        if latest.volume < ind.volume_sma_20 * 0.8:
            return None

        # Calculate trade levels
        stop_loss = ind.ema_8 * 0.97  # Below 8 EMA
        target_1 = max(c.high for c in candles[-20:])  # Recent high
        risk = price - stop_loss
        reward = target_1 - price
        rr = reward / risk if risk > 0 else 0

        if rr < 2.0:
            return None

        confidence = 0.6
        if ind.macd_line > ind.macd_signal:
            confidence += 0.1
        if ind.rsi_14 > 40 and ind.rsi_14 < 60:
            confidence += 0.05  # Not overbought
        if ind.relative_volume >= 1.5:
            confidence += 0.05

        return Signal(
            action="BUY",
            confidence=min(confidence, 0.9),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"Swing pullback to 8 EMA (${ind.ema_8:.2f}) in uptrend",
                f"Above 200 SMA (${ind.sma_200:.2f}) — institutionally supported",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target_1:.2f}",
                "Sell in quarters: 25% at each resistance level",
            ],
            style="swing",
            setup="8 EMA Pullback",
            stop_loss=round(stop_loss, 2),
            target=round(target_1, 2),
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()


class SwingDowntrendBreakStrategy(Strategy):
    """
    Setup 2: Long-term downtrend break.
    Stock reclaims 200 SMA on high volume after being below it.
    """
    name = "Swing: Downtrend Break"
    description = "Buy when stock reclaims 200 SMA on high volume after prolonged downtrend"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        candles = snapshot.candles
        if len(candles) < 50 or ind.sma_200 == 0:
            return None

        price = snapshot.latest.close
        latest = snapshot.latest

        # Price just crossed above 200 SMA
        if price < ind.sma_200:
            return None

        # Was below 200 SMA recently (within last 5 candles)
        recently_below = any(c.close < ind.sma_200 for c in candles[-5:-1])
        if not recently_below:
            return None

        # Must have been in downtrend (below 200 SMA for extended period)
        lookback = candles[-50:-5]
        pct_below = sum(1 for c in lookback if c.close < ind.sma_200) / len(lookback)
        if pct_below < 0.6:
            return None  # Wasn't really in a downtrend

        # Volume spike on the break
        if latest.volume < ind.volume_sma_20 * 1.5:
            return None

        # Green candle
        if latest.close < latest.open:
            return None

        # Calculate levels
        stop_loss = min(c.low for c in candles[-5:])
        recent_high = max(c.high for c in candles[-30:])
        risk = price - stop_loss
        reward = recent_high - price
        rr = reward / risk if risk > 0 else 0

        if rr < 2.0:
            return None

        confidence = 0.6
        if ind.relative_volume >= 2.0:
            confidence += 0.1
        if ind.macd_histogram > 0:
            confidence += 0.05
        if ind.rsi_14 > 50:
            confidence += 0.05

        return Signal(
            action="BUY",
            confidence=min(confidence, 0.9),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"Downtrend break: price reclaimed 200 SMA (${ind.sma_200:.2f})",
                f"Was below 200 SMA {pct_below:.0%} of last 50 candles",
                f"Volume spike: {ind.relative_volume:.1f}x average",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${recent_high:.2f}",
            ],
            style="swing",
            setup="Downtrend Break",
            stop_loss=round(stop_loss, 2),
            target=round(recent_high, 2),
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()


class SwingOversoldBounceStrategy(Strategy):
    """
    Setup 3: Oversold bounce on quality stock.
    Stock drops significantly below 200 SMA, first close above 8 EMA = entry.
    """
    name = "Swing: Oversold Bounce"
    description = "Buy first close above 8 EMA after deep sell-off below 200 SMA"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        ind = snapshot.indicators
        candles = snapshot.candles
        if len(candles) < 20 or ind.ema_8 == 0 or ind.sma_200 == 0:
            return None

        price = snapshot.latest.close
        latest = snapshot.latest

        # Stock must be well below 200 SMA (oversold)
        below_200_pct = ((ind.sma_200 - price) / ind.sma_200) * 100
        if below_200_pct < 10:
            return None  # Not oversold enough

        # RSI should be low (confirming oversold)
        if ind.rsi_14 > 40:
            return None

        # First close above 8 EMA (the entry trigger)
        if price < ind.ema_8:
            return None

        # Previous candle was below 8 EMA
        if len(candles) >= 2 and candles[-2].close >= ind.ema_8:
            return None  # Not the FIRST close above

        # Green candle
        if latest.close < latest.open:
            return None

        # Calculate levels — R:R must be 3:1+ given uncertainty
        stop_loss = latest.low
        target = ind.sma_200  # Target the 200 SMA reclaim
        risk = price - stop_loss
        reward = target - price
        rr = reward / risk if risk > 0 else 0

        if rr < 3.0:
            return None  # Need higher R:R for oversold bounces

        confidence = 0.55  # Lower base confidence (risky setup)
        if ind.rsi_14 < 25:
            confidence += 0.1  # Very oversold
        if latest.volume > ind.volume_sma_20 * 1.5:
            confidence += 0.05

        return Signal(
            action="BUY",
            confidence=min(confidence, 0.85),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"Oversold bounce: first close above 8 EMA (${ind.ema_8:.2f})",
                f"RSI at {ind.rsi_14:.1f} (oversold), {below_200_pct:.0f}% below 200 SMA",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f} (200 SMA)",
                "Higher risk setup — sell in quarters at each resistance level",
            ],
            style="swing",
            setup="Oversold Bounce",
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()


class BearFlagStrategy(Strategy):
    """
    Bear Flag / Breakdown setup for short selling.
    Strong red candle -> 2-3 bounce candles -> breaks low.
    """
    name = "Bear Flag Breakdown"
    description = "Sell/short on bear flag breakdown below consolidation low"

    def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles
        ind = snapshot.indicators
        if len(candles) < 10:
            return None

        price = snapshot.latest.close
        latest = snapshot.latest

        # Need bearish context: below 200 SMA or strong downtrend
        if ind.sma_200 > 0 and price > ind.sma_200:
            return None

        # Look for the pattern in last 6 candles
        recent = candles[-6:]
        first = recent[0]

        # First candle: strong red
        first_move = (first.open - first.close) / first.open * 100 if first.open > 0 else 0
        if first_move < 2:
            return None  # Not a strong enough red candle

        # Middle candles: small bounces
        middle = recent[1:-1]
        green_count = sum(1 for c in middle if c.close > c.open)
        if green_count < 2:
            return None

        bodies_small = all(
            abs(c.close - c.open) < abs(first.close - first.open) * 0.5
            for c in middle
        )
        if not bodies_small:
            return None

        # Latest: breaks below the consolidation low
        consol_low = min(c.low for c in middle)
        if latest.close > consol_low:
            return None
        if latest.close > latest.open:
            return None  # Should be red

        # Volume confirms
        if ind.macd_line > ind.macd_signal:
            return None  # MACD should be bearish

        stop_loss = max(c.high for c in middle)
        target = consol_low - (stop_loss - consol_low)  # Measured move down
        risk = stop_loss - price
        reward = price - target
        rr = reward / risk if risk > 0 else 0

        if rr < 2.0:
            return None

        confidence = 0.6
        if latest.volume > ind.volume_sma_20 * 1.5:
            confidence += 0.1
        if ind.rsi_14 < 40:
            confidence += 0.05

        return Signal(
            action="SELL",
            confidence=min(confidence, 0.9),
            strategy_name=self.name,
            symbol=snapshot.symbol,
            price=price,
            reasons=[
                f"Bear flag breakdown below ${consol_low:.2f}",
                f"Below 200 SMA (${ind.sma_200:.2f}) — bearish trend confirmed",
                f"R:R = {rr:.1f}:1 | Stop: ${stop_loss:.2f} | Target: ${target:.2f}",
                "MACD bearish, volume confirming the breakdown",
            ],
            style="swing",
            setup="Bear Flag Breakdown",
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            risk_reward=round(rr, 1),
        )

    def to_dict(self):
        return {"name": self.name, "type": "builtin"}

    @classmethod
    def from_dict(cls, data):
        return cls()
