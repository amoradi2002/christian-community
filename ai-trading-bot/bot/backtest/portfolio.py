"""
Portfolio Simulator - Full-featured portfolio tracking for backtesting.

Supports long and short positions, stop-loss/take-profit auto-execution,
trailing stops, slippage/commission modeling, margin tracking, and
detailed equity curve recording.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """A single open position in the portfolio."""
    symbol: str
    shares: float
    entry_price: float
    entry_date: str
    strategy_name: str
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop_pct: float = 0.0
    highest_price: float = 0.0  # for trailing stop (long)
    lowest_price: float = 0.0   # for trailing stop (short)
    side: str = "long"          # "long" or "short"

    @property
    def cost_basis(self) -> float:
        """Total cost to enter this position (absolute value)."""
        return self.shares * self.entry_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L at a given price."""
        if self.side == "long":
            return self.shares * (current_price - self.entry_price)
        else:
            return self.shares * (self.entry_price - current_price)

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Unrealized P&L as a percentage of entry cost."""
        if self.entry_price == 0:
            return 0.0
        if self.side == "long":
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - current_price) / self.entry_price) * 100

    def market_value(self, current_price: float) -> float:
        """Current market value of the position."""
        return self.shares * current_price

    def update_trailing_stop(self, current_price: float) -> None:
        """Update trailing stop levels based on current price movement."""
        if self.trailing_stop_pct <= 0:
            return

        if self.side == "long":
            if current_price > self.highest_price:
                self.highest_price = current_price
            new_stop = self.highest_price * (1 - self.trailing_stop_pct / 100)
            if new_stop > self.stop_loss:
                self.stop_loss = new_stop
        else:
            if self.lowest_price == 0 or current_price < self.lowest_price:
                self.lowest_price = current_price
            new_stop = self.lowest_price * (1 + self.trailing_stop_pct / 100)
            if self.stop_loss == 0 or new_stop < self.stop_loss:
                self.stop_loss = new_stop

    def check_stop_triggered(self, candle_low: float, candle_high: float) -> Optional[str]:
        """
        Check if stop-loss or take-profit was triggered during a candle.

        Returns:
            "stop_loss", "take_profit", or None
        """
        if self.side == "long":
            if self.stop_loss > 0 and candle_low <= self.stop_loss:
                return "stop_loss"
            if self.take_profit > 0 and candle_high >= self.take_profit:
                return "take_profit"
        else:
            if self.stop_loss > 0 and candle_high >= self.stop_loss:
                return "stop_loss"
            if self.take_profit > 0 and candle_low <= self.take_profit:
                return "take_profit"
        return None


@dataclass
class Trade:
    """A completed (closed) trade."""
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    entry_date: str
    exit_price: float = 0.0
    exit_date: str = ""
    shares: float = 0.0
    pnl: float = 0.0        # absolute P&L
    pnl_pct: float = 0.0    # percentage P&L
    strategy_name: str = ""
    exit_reason: str = ""    # "signal", "stop_loss", "take_profit", "trailing_stop", "forced_close"
    commission: float = 0.0
    slippage_cost: float = 0.0


@dataclass
class EquityPoint:
    """A single data point in the equity curve."""
    date: str
    equity: float
    cash: float
    positions_value: float
    drawdown: float  # current drawdown percentage from peak
    num_positions: int


@dataclass
class Portfolio:
    """
    Full-featured portfolio simulator for backtesting.

    Supports long/short positions, automatic stop/target execution,
    slippage and commission modeling, position limits, and margin tracking.
    """
    cash: float = 10000.0
    initial_cash: float = 0.0
    positions: dict = field(default_factory=dict)  # symbol -> Position
    trades: list = field(default_factory=list)       # list[Trade]
    equity_curve: list = field(default_factory=list)  # list[EquityPoint]

    # Configuration
    slippage_pct: float = 0.05         # 0.05% slippage per trade
    commission_per_trade: float = 0.0   # flat commission per trade
    max_positions: int = 10
    position_size_pct: float = 10.0     # default % of equity per position
    margin_requirement: float = 150.0   # 150% margin for shorts (Reg T)

    # Internal tracking
    peak_equity: float = 0.0
    margin_used: float = 0.0  # total margin reserved for short positions

    def __post_init__(self):
        if self.initial_cash == 0:
            self.initial_cash = self.cash
        if self.peak_equity == 0:
            self.peak_equity = self.cash

    # ─── Order Execution ─────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        price: float,
        date: str,
        strategy_name: str = "",
        allocation_pct: float = 0.0,
        shares: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        trailing_stop_pct: float = 0.0,
    ) -> bool:
        """
        Open a long position or close a short position.

        Args:
            symbol: Ticker symbol.
            price: Execution price before slippage.
            date: Trade date string.
            strategy_name: Name of the strategy generating this signal.
            allocation_pct: % of current equity to allocate (0 = use default).
            shares: Explicit share count (overrides allocation_pct if > 0).
            stop_loss: Stop-loss price level.
            take_profit: Take-profit price level.
            trailing_stop_pct: Trailing stop distance as percentage.

        Returns:
            True if order executed, False if rejected.
        """
        # If we have a short position, close it
        if symbol in self.positions and self.positions[symbol].side == "short":
            return self._close_position(symbol, price, date, exit_reason="signal")

        # Don't open duplicate long
        if symbol in self.positions:
            logger.debug("Already have a long position in %s", symbol)
            return False

        # Check position limits
        if len(self.positions) >= self.max_positions:
            logger.debug("Max positions (%d) reached, rejecting buy for %s",
                         self.max_positions, symbol)
            return False

        # Calculate execution price with slippage (buy = pay more)
        exec_price = price * (1 + self.slippage_pct / 100)
        slippage_per_share = exec_price - price

        # Determine share count
        if shares <= 0:
            alloc = allocation_pct if allocation_pct > 0 else self.position_size_pct
            current_equity = self._current_equity_estimate(price)
            amount = current_equity * (alloc / 100)
            amount = min(amount, self.cash - self.commission_per_trade)
            if amount <= 0:
                logger.debug("Insufficient cash for buy on %s", symbol)
                return False
            shares = amount / exec_price

        if shares <= 0:
            return False

        total_cost = shares * exec_price + self.commission_per_trade

        # Cash check
        if total_cost > self.cash:
            # Try to buy what we can afford
            affordable = (self.cash - self.commission_per_trade) / exec_price
            if affordable <= 0:
                logger.debug("Cannot afford any shares of %s", symbol)
                return False
            shares = affordable
            total_cost = shares * exec_price + self.commission_per_trade

        self.cash -= total_cost

        pos = Position(
            symbol=symbol,
            shares=shares,
            entry_price=exec_price,
            entry_date=date,
            strategy_name=strategy_name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct,
            highest_price=exec_price,
            lowest_price=exec_price,
            side="long",
        )
        self.positions[symbol] = pos

        logger.debug("BUY %s: %.2f shares @ $%.2f (slippage: $%.4f/sh, comm: $%.2f)",
                      symbol, shares, exec_price, slippage_per_share,
                      self.commission_per_trade)
        return True

    def sell(
        self,
        symbol: str,
        price: float,
        date: str,
        exit_reason: str = "signal",
    ) -> bool:
        """
        Close a long position or open a short position.

        If a long position exists for the symbol, it is closed.
        Otherwise the sell is ignored (use sell_short to open shorts).
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        if pos.side == "long":
            return self._close_position(symbol, price, date, exit_reason=exit_reason)
        else:
            # Already short; ignore duplicate sell
            return False

    def sell_short(
        self,
        symbol: str,
        price: float,
        date: str,
        strategy_name: str = "",
        allocation_pct: float = 0.0,
        shares: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        trailing_stop_pct: float = 0.0,
    ) -> bool:
        """
        Open a short position.

        Requires margin; the portfolio reserves margin_requirement% of
        the position value from cash.
        """
        # If we have a long position, close it first
        if symbol in self.positions and self.positions[symbol].side == "long":
            self._close_position(symbol, price, date, exit_reason="signal")

        if symbol in self.positions:
            logger.debug("Already have a short position in %s", symbol)
            return False

        if len(self.positions) >= self.max_positions:
            logger.debug("Max positions (%d) reached, rejecting short for %s",
                         self.max_positions, symbol)
            return False

        # Slippage on short: execute at lower price (worse fill for seller)
        exec_price = price * (1 - self.slippage_pct / 100)
        slippage_per_share = price - exec_price

        # Determine share count
        if shares <= 0:
            alloc = allocation_pct if allocation_pct > 0 else self.position_size_pct
            current_equity = self._current_equity_estimate(price)
            amount = current_equity * (alloc / 100)
            shares = amount / exec_price

        if shares <= 0:
            return False

        # Margin requirement: reserve cash for the short
        margin_needed = shares * exec_price * (self.margin_requirement / 100)
        margin_needed += self.commission_per_trade

        if margin_needed > self.cash:
            # Reduce to what we can afford
            affordable_margin = self.cash - self.commission_per_trade
            if affordable_margin <= 0:
                return False
            shares = affordable_margin / (exec_price * (self.margin_requirement / 100))
            margin_needed = shares * exec_price * (self.margin_requirement / 100)
            margin_needed += self.commission_per_trade

        # We receive proceeds from the short sale, but must reserve margin
        short_proceeds = shares * exec_price
        self.cash += short_proceeds        # proceeds credited
        self.cash -= margin_needed         # margin reserved
        self.margin_used += margin_needed - self.commission_per_trade

        pos = Position(
            symbol=symbol,
            shares=shares,
            entry_price=exec_price,
            entry_date=date,
            strategy_name=strategy_name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct,
            highest_price=exec_price,
            lowest_price=exec_price,
            side="short",
        )
        self.positions[symbol] = pos

        logger.debug("SHORT %s: %.2f shares @ $%.2f (slippage: $%.4f/sh, comm: $%.2f)",
                      symbol, shares, exec_price, slippage_per_share,
                      self.commission_per_trade)
        return True

    def cover_short(
        self,
        symbol: str,
        price: float,
        date: str,
        exit_reason: str = "signal",
    ) -> bool:
        """Close (cover) a short position."""
        if symbol not in self.positions:
            return False
        if self.positions[symbol].side != "short":
            return False
        return self._close_position(symbol, price, date, exit_reason=exit_reason)

    def _close_position(
        self,
        symbol: str,
        price: float,
        date: str,
        exit_reason: str = "signal",
    ) -> bool:
        """Internal: close any position (long or short)."""
        if symbol not in self.positions:
            return False

        pos = self.positions.pop(symbol)

        if pos.side == "long":
            # Slippage on sell: execute at lower price
            exec_price = price * (1 - self.slippage_pct / 100)
            slippage_cost = pos.shares * (price - exec_price)
            proceeds = pos.shares * exec_price - self.commission_per_trade
            self.cash += proceeds
            pnl = pos.shares * (exec_price - pos.entry_price) - self.commission_per_trade
        else:
            # Covering short: buy at higher price (slippage hurts)
            exec_price = price * (1 + self.slippage_pct / 100)
            slippage_cost = pos.shares * (exec_price - price)
            cover_cost = pos.shares * exec_price + self.commission_per_trade

            # Release margin and compute P&L
            margin_for_pos = pos.shares * pos.entry_price * (self.margin_requirement / 100)
            self.margin_used = max(0, self.margin_used - margin_for_pos)
            self.cash += margin_for_pos  # release margin back
            self.cash -= cover_cost      # pay to cover
            pnl = pos.shares * (pos.entry_price - exec_price) - self.commission_per_trade

        pnl_pct = 0.0
        if pos.entry_price > 0:
            if pos.side == "long":
                pnl_pct = ((exec_price - pos.entry_price) / pos.entry_price) * 100
            else:
                pnl_pct = ((pos.entry_price - exec_price) / pos.entry_price) * 100

        trade = Trade(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            entry_date=pos.entry_date,
            exit_price=exec_price,
            exit_date=date,
            shares=pos.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            strategy_name=pos.strategy_name,
            exit_reason=exit_reason,
            commission=self.commission_per_trade * 2,  # entry + exit
            slippage_cost=slippage_cost,
        )
        self.trades.append(trade)

        logger.debug("CLOSE %s %s: %.2f shares @ $%.2f | PnL: $%.2f (%.2f%%) [%s]",
                      pos.side.upper(), symbol, pos.shares, exec_price,
                      pnl, pnl_pct, exit_reason)
        return True

    # ─── Stop / Target Checking ──────────────────────────────────────

    def check_stops(self, current_prices: dict, current_date: str,
                    candle_data: Optional[dict] = None) -> list:
        """
        Check all open positions for stop-loss and take-profit triggers.

        Args:
            current_prices: dict of symbol -> current price
            current_date: date string for the current bar
            candle_data: optional dict of symbol -> {high, low} for
                         intra-bar stop checking

        Returns:
            List of Trade objects for positions that were closed.
        """
        closed_trades = []
        symbols_to_close = []

        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol)
            if price is None:
                continue

            # Update trailing stop first
            pos.update_trailing_stop(price)

            # Get candle high/low for accurate stop checking
            if candle_data and symbol in candle_data:
                candle_low = candle_data[symbol].get("low", price)
                candle_high = candle_data[symbol].get("high", price)
            else:
                candle_low = price
                candle_high = price

            trigger = pos.check_stop_triggered(candle_low, candle_high)

            if trigger is not None:
                if trigger == "stop_loss":
                    exit_price = pos.stop_loss
                    exit_reason = "trailing_stop" if pos.trailing_stop_pct > 0 else "stop_loss"
                else:
                    exit_price = pos.take_profit
                    exit_reason = "take_profit"

                symbols_to_close.append((symbol, exit_price, exit_reason))

        for symbol, exit_price, exit_reason in symbols_to_close:
            self._close_position(symbol, exit_price, current_date,
                                 exit_reason=exit_reason)
            closed_trades.append(self.trades[-1])

        return closed_trades

    # ─── Exposure & Risk Tracking ────────────────────────────────────

    def get_exposure(self, current_prices: Optional[dict] = None) -> dict:
        """
        Get total long and short exposure as percentage of equity.

        Returns:
            Dict with long_pct, short_pct, net_pct, gross_pct
        """
        equity = self.total_value(current_prices or {})
        if equity <= 0:
            return {"long_pct": 0.0, "short_pct": 0.0,
                    "net_pct": 0.0, "gross_pct": 0.0}

        long_value = 0.0
        short_value = 0.0

        for symbol, pos in self.positions.items():
            price = (current_prices or {}).get(symbol, pos.entry_price)
            mv = pos.shares * price
            if pos.side == "long":
                long_value += mv
            else:
                short_value += mv

        long_pct = (long_value / equity) * 100
        short_pct = (short_value / equity) * 100

        return {
            "long_pct": round(long_pct, 2),
            "short_pct": round(short_pct, 2),
            "net_pct": round(long_pct - short_pct, 2),
            "gross_pct": round(long_pct + short_pct, 2),
        }

    def get_sector_exposure(self, current_prices: Optional[dict] = None,
                            sector_map: Optional[dict] = None) -> dict:
        """
        Get exposure broken down by sector.

        Args:
            current_prices: symbol -> price
            sector_map: symbol -> sector name

        Returns:
            Dict of sector -> exposure percentage of equity
        """
        if not sector_map:
            return {}

        equity = self.total_value(current_prices or {})
        if equity <= 0:
            return {}

        sector_exposure = {}
        for symbol, pos in self.positions.items():
            price = (current_prices or {}).get(symbol, pos.entry_price)
            sector = sector_map.get(symbol, "Unknown")
            mv = pos.shares * price
            if pos.side == "short":
                mv = -mv
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + mv

        return {
            sector: round((value / equity) * 100, 2)
            for sector, value in sector_exposure.items()
        }

    def get_portfolio_heat(self, current_prices: Optional[dict] = None) -> dict:
        """
        Calculate total portfolio heat: the sum of risk across all positions.

        Heat = sum of (distance from current price to stop-loss) for each position,
        expressed as a percentage of total equity.
        """
        equity = self.total_value(current_prices or {})
        if equity <= 0:
            return {"total_heat_pct": 0.0, "positions_at_risk": 0, "details": []}

        total_risk = 0.0
        details = []

        for symbol, pos in self.positions.items():
            price = (current_prices or {}).get(symbol, pos.entry_price)

            if pos.stop_loss > 0:
                if pos.side == "long":
                    risk_per_share = max(0, price - pos.stop_loss)
                else:
                    risk_per_share = max(0, pos.stop_loss - price)
                position_risk = risk_per_share * pos.shares
            else:
                # No stop loss: risk is entire position value
                position_risk = pos.shares * price

            risk_pct = (position_risk / equity) * 100
            total_risk += position_risk

            details.append({
                "symbol": symbol,
                "side": pos.side,
                "risk_dollars": round(position_risk, 2),
                "risk_pct": round(risk_pct, 2),
                "has_stop": pos.stop_loss > 0,
            })

        return {
            "total_heat_pct": round((total_risk / equity) * 100, 2),
            "positions_at_risk": len(details),
            "details": details,
        }

    # ─── Valuation ───────────────────────────────────────────────────

    def total_value(self, current_prices: dict) -> float:
        """Calculate total portfolio value (cash + positions)."""
        value = self.cash + self.margin_used  # margin is still ours
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos.entry_price)
            if pos.side == "long":
                value += pos.shares * price
            else:
                # Short: value = entry proceeds - current cover cost
                # Already accounted in cash/margin, just add unrealized P&L
                value += pos.shares * (pos.entry_price - price)
        return value

    def _current_equity_estimate(self, ref_price: float = 0.0) -> float:
        """Quick equity estimate using entry prices (no current prices needed)."""
        value = self.cash + self.margin_used
        for symbol, pos in self.positions.items():
            if pos.side == "long":
                value += pos.shares * pos.entry_price
        return value

    # ─── Equity Curve ────────────────────────────────────────────────

    def snapshot_equity(self, date: str, current_prices: dict) -> None:
        """Record a point on the equity curve with full detail."""
        equity = self.total_value(current_prices)

        if equity > self.peak_equity:
            self.peak_equity = equity

        drawdown = 0.0
        if self.peak_equity > 0:
            drawdown = ((self.peak_equity - equity) / self.peak_equity) * 100

        positions_value = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos.entry_price)
            positions_value += pos.shares * price

        point = EquityPoint(
            date=date,
            equity=equity,
            cash=self.cash,
            positions_value=positions_value,
            drawdown=drawdown,
            num_positions=len(self.positions),
        )
        self.equity_curve.append(point)

    def get_equity_series(self) -> list:
        """Return equity values as a simple list for analysis."""
        return [p.equity for p in self.equity_curve]

    def get_dates_series(self) -> list:
        """Return dates as a simple list."""
        return [p.date for p in self.equity_curve]

    # ─── Convenience ─────────────────────────────────────────────────

    def close_all_positions(self, current_prices: dict, date: str,
                            exit_reason: str = "forced_close") -> None:
        """Close every open position at current prices."""
        symbols = list(self.positions.keys())
        for symbol in symbols:
            price = current_prices.get(symbol)
            if price is not None:
                self._close_position(symbol, price, date, exit_reason=exit_reason)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def num_positions(self) -> int:
        return len(self.positions)

    def summary(self, current_prices: Optional[dict] = None) -> dict:
        """Quick summary of portfolio state."""
        prices = current_prices or {}
        equity = self.total_value(prices)
        return {
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "margin_used": round(self.margin_used, 2),
            "num_positions": len(self.positions),
            "total_trades": len(self.trades),
            "peak_equity": round(self.peak_equity, 2),
            "return_pct": round(((equity - self.initial_cash) / self.initial_cash) * 100, 2)
            if self.initial_cash > 0 else 0.0,
        }
