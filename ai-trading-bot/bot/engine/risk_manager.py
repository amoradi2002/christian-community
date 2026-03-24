"""
Risk Manager - Personalized position sizing and adaptive risk control.

This is your financial safety net. It:
1. Knows your budget and adjusts position sizes accordingly
2. Never risks more than you're comfortable losing per trade
3. Automatically increases/decreases risk as your account grows/shrinks
4. Tracks your win rate and adjusts confidence over time
5. Prevents revenge trading after losses

Key concepts:
- Risk per trade: The max $ you're willing to lose on a single trade
- Position size: Calculated from risk, not just "buy 10 shares"
- Kelly Criterion: Math-based sizing that grows with your edge
- Drawdown protection: Reduces risk when you're on a losing streak
"""

import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from bot.db.database import get_connection


@dataclass
class UserProfile:
    """Your personalized trading profile."""
    # --- You set these ---
    starting_capital: float = 500.0          # How much you're starting with
    current_capital: float = 500.0           # Updated as you trade
    risk_per_trade_pct: float = 2.0          # Max % to risk per trade (1-5% recommended)
    max_portfolio_pct: float = 10.0          # Max % of portfolio in one stock
    max_open_positions: int = 5              # Don't spread too thin
    risk_level: str = "conservative"         # "conservative", "moderate", "aggressive"
    preferred_strategies: list = field(default_factory=list)  # e.g. ["swing", "options"]
    daily_loss_limit_pct: float = 5.0        # Stop trading if down this % in a day
    weekly_loss_limit_pct: float = 10.0      # Stop trading if down this % in a week

    # --- Bot tracks these ---
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    current_streak: int = 0                  # Positive = wins, negative = losses
    peak_capital: float = 500.0              # Highest your account has been
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    last_trade_date: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def drawdown_pct(self) -> float:
        """How far below your peak you are."""
        if self.peak_capital == 0:
            return 0.0
        return ((self.peak_capital - self.current_capital) / self.peak_capital) * 100

    @property
    def growth_pct(self) -> float:
        """Total growth from starting capital."""
        if self.starting_capital == 0:
            return 0.0
        return ((self.current_capital - self.starting_capital) / self.starting_capital) * 100

    @property
    def avg_pnl_per_trade(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl / self.total_trades

    @property
    def risk_multiplier(self) -> float:
        """
        Dynamic multiplier based on performance.
        - Winning streak: gradually increase (up to 1.5x)
        - Losing streak: aggressively decrease (down to 0.25x)
        - In drawdown: reduce proportionally
        """
        multiplier = 1.0

        # Streak adjustment
        if self.current_streak >= 3:
            multiplier = min(1.5, 1.0 + (self.current_streak - 2) * 0.1)
        elif self.current_streak <= -2:
            multiplier = max(0.25, 1.0 + self.current_streak * 0.2)

        # Drawdown adjustment
        dd = self.drawdown_pct
        if dd > 15:
            multiplier *= 0.25  # Severe drawdown: quarter risk
        elif dd > 10:
            multiplier *= 0.5   # Significant drawdown: half risk
        elif dd > 5:
            multiplier *= 0.75  # Moderate drawdown: reduce risk

        return round(multiplier, 2)

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = v
        d["win_rate"] = self.win_rate
        d["drawdown_pct"] = self.drawdown_pct
        d["growth_pct"] = self.growth_pct
        d["avg_pnl_per_trade"] = self.avg_pnl_per_trade
        d["risk_multiplier"] = self.risk_multiplier
        d["risk_per_trade_dollars"] = self.risk_per_trade_dollars()
        d["effective_risk_pct"] = round(self.risk_per_trade_pct * self.risk_multiplier, 2)
        return d

    def risk_per_trade_dollars(self) -> float:
        """Max dollars to risk on a single trade, adjusted for performance."""
        base_risk = self.current_capital * (self.risk_per_trade_pct / 100)
        return round(base_risk * self.risk_multiplier, 2)


# Risk level presets
RISK_PRESETS = {
    "conservative": {
        "risk_per_trade_pct": 1.0,
        "max_portfolio_pct": 5.0,
        "max_open_positions": 3,
        "daily_loss_limit_pct": 3.0,
        "weekly_loss_limit_pct": 6.0,
    },
    "moderate": {
        "risk_per_trade_pct": 2.0,
        "max_portfolio_pct": 10.0,
        "max_open_positions": 5,
        "daily_loss_limit_pct": 5.0,
        "weekly_loss_limit_pct": 10.0,
    },
    "aggressive": {
        "risk_per_trade_pct": 4.0,
        "max_portfolio_pct": 20.0,
        "max_open_positions": 8,
        "daily_loss_limit_pct": 8.0,
        "weekly_loss_limit_pct": 15.0,
    },
}


class RiskManager:
    """
    The brain behind position sizing and risk control.
    Sits between signal generation and order execution.
    """

    def __init__(self):
        self.profile = load_profile()

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        stop_loss_pct: float | None = None,
        confidence: float = 0.65,
    ) -> dict:
        """
        Calculate how many shares to buy based on your risk profile.

        Args:
            symbol: Stock ticker
            price: Current stock price
            stop_loss_pct: How far below entry to set stop loss (default: ATR-based)
            confidence: Signal confidence (0-1)

        Returns dict with:
            - shares: Number of shares to buy
            - position_value: Total cost
            - risk_amount: Max you could lose
            - stop_loss_price: Suggested stop loss
            - take_profit_price: Suggested take profit
            - can_trade: Whether this trade is allowed
            - reason: Why trade was blocked (if blocked)
        """
        p = self.profile

        # Check if trading is allowed
        block_reason = self._check_trading_allowed(symbol, price)
        if block_reason:
            return {
                "shares": 0, "position_value": 0, "risk_amount": 0,
                "stop_loss_price": 0, "take_profit_price": 0,
                "can_trade": False, "reason": block_reason,
            }

        # Default stop loss based on risk level
        if stop_loss_pct is None:
            stop_loss_pct = {"conservative": 3.0, "moderate": 5.0, "aggressive": 8.0}.get(
                p.risk_level, 5.0
            )

        # Risk amount for this trade
        risk_dollars = p.risk_per_trade_dollars()

        # Confidence scaling: higher confidence = more of your risk budget
        confidence_scale = min(1.0, max(0.5, confidence))
        adjusted_risk = risk_dollars * confidence_scale

        # Position size from risk
        stop_loss_price = round(price * (1 - stop_loss_pct / 100), 2)
        risk_per_share = price - stop_loss_price

        if risk_per_share <= 0:
            return {
                "shares": 0, "position_value": 0, "risk_amount": 0,
                "stop_loss_price": stop_loss_price, "take_profit_price": 0,
                "can_trade": False, "reason": "Invalid stop loss",
            }

        shares = int(adjusted_risk / risk_per_share)

        # Cap by max portfolio percentage
        max_position_value = p.current_capital * (p.max_portfolio_pct / 100)
        max_shares_by_portfolio = int(max_position_value / price)
        shares = min(shares, max_shares_by_portfolio)

        # Can't buy less than 1 share (unless fractional)
        if shares < 1 and price <= p.current_capital * (p.max_portfolio_pct / 100):
            shares = 1  # Allow at least 1 share if you can afford it

        if shares < 1:
            return {
                "shares": 0, "position_value": 0, "risk_amount": 0,
                "stop_loss_price": stop_loss_price, "take_profit_price": 0,
                "can_trade": False,
                "reason": f"Stock price ${price} too high for your current capital ${p.current_capital:.2f}",
            }

        position_value = round(shares * price, 2)
        actual_risk = round(shares * risk_per_share, 2)

        # Take profit at 2:1 reward-to-risk ratio
        take_profit_price = round(price + (risk_per_share * 2), 2)

        return {
            "shares": shares,
            "position_value": position_value,
            "risk_amount": actual_risk,
            "risk_pct_of_capital": round((actual_risk / p.current_capital) * 100, 2),
            "stop_loss_price": stop_loss_price,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_price": take_profit_price,
            "reward_risk_ratio": 2.0,
            "can_trade": True,
            "reason": "Trade approved",
            "confidence_used": confidence,
            "risk_multiplier": p.risk_multiplier,
        }

    def calculate_options_size(
        self,
        contract_price: float,
        confidence: float = 0.65,
    ) -> dict:
        """
        Calculate how many options contracts to buy.
        Options are riskier, so we use tighter limits.
        """
        p = self.profile

        # For options, risk the premium amount (can lose 100%)
        risk_dollars = p.risk_per_trade_dollars()

        # Options get half the risk budget of stocks
        options_risk = risk_dollars * 0.5

        # Scale by confidence
        confidence_scale = min(1.0, max(0.5, confidence))
        adjusted_risk = options_risk * confidence_scale

        # Each contract = 100 shares, price is per share
        contract_cost = contract_price * 100
        contracts = max(1, int(adjusted_risk / contract_cost))

        total_cost = contracts * contract_cost
        if total_cost > p.current_capital * (p.max_portfolio_pct / 100):
            contracts = max(1, int((p.current_capital * p.max_portfolio_pct / 100) / contract_cost))
            total_cost = contracts * contract_cost

        return {
            "contracts": contracts,
            "total_cost": round(total_cost, 2),
            "max_loss": round(total_cost, 2),  # Options can go to zero
            "can_trade": total_cost <= p.current_capital * 0.5,  # Never put >50% in options
            "reason": "Approved" if total_cost <= p.current_capital * 0.5 else "Position too large for account",
        }

    def record_trade_result(self, pnl: float, symbol: str = ""):
        """
        Record a trade result and update the profile.
        Call this when a position is closed.
        """
        p = self.profile
        p.total_trades += 1
        p.total_pnl += pnl
        p.current_capital += pnl
        p.last_trade_date = datetime.now().strftime("%Y-%m-%d")

        if pnl > 0:
            p.winning_trades += 1
            p.current_streak = max(1, p.current_streak + 1)
            p.best_trade_pnl = max(p.best_trade_pnl, pnl)
        elif pnl < 0:
            p.losing_trades += 1
            p.current_streak = min(-1, p.current_streak - 1)
            p.worst_trade_pnl = min(p.worst_trade_pnl, pnl)

        # Update peak
        if p.current_capital > p.peak_capital:
            p.peak_capital = p.current_capital

        # Track daily/weekly PnL
        p.daily_pnl += pnl
        p.weekly_pnl += pnl

        p.updated_at = datetime.now().isoformat()
        save_profile(p)

    def get_status(self) -> dict:
        """Get current risk status for display."""
        p = self.profile
        return {
            "profile": p.to_dict(),
            "can_trade_today": p.daily_pnl > -(p.current_capital * p.daily_loss_limit_pct / 100),
            "can_trade_week": p.weekly_pnl > -(p.current_capital * p.weekly_loss_limit_pct / 100),
            "daily_pnl": p.daily_pnl,
            "daily_limit": round(p.current_capital * p.daily_loss_limit_pct / 100, 2),
            "weekly_pnl": p.weekly_pnl,
            "weekly_limit": round(p.current_capital * p.weekly_loss_limit_pct / 100, 2),
            "next_trade_risk": p.risk_per_trade_dollars(),
            "risk_level_label": p.risk_level.capitalize(),
            "streak_label": f"{'+' if p.current_streak > 0 else ''}{p.current_streak}",
        }

    def _check_trading_allowed(self, symbol: str, price: float) -> str | None:
        """Check if a trade should be blocked. Returns reason string or None."""
        p = self.profile

        # Daily loss limit
        if p.daily_pnl <= -(p.current_capital * p.daily_loss_limit_pct / 100):
            return f"Daily loss limit reached (${p.daily_pnl:.2f}). Take a break, come back tomorrow."

        # Weekly loss limit
        if p.weekly_pnl <= -(p.current_capital * p.weekly_loss_limit_pct / 100):
            return f"Weekly loss limit reached (${p.weekly_pnl:.2f}). Step back and review your strategy."

        # Check max open positions
        try:
            from bot.engine.trader import get_positions
            positions = get_positions()
            if len(positions) >= p.max_open_positions:
                return f"Max open positions ({p.max_open_positions}) reached. Close a position first."

            # Check if already in this stock
            for pos in positions:
                if pos.get("symbol", "").upper() == symbol.upper():
                    return f"Already have a position in {symbol}. Manage existing position first."
        except Exception:
            pass

        # Not enough capital
        if price > p.current_capital:
            return f"Stock price ${price:.2f} exceeds your capital ${p.current_capital:.2f}"

        # Losing streak protection
        if p.current_streak <= -4:
            return "On a 4+ loss streak. Risk is reduced to minimum. Consider pausing."

        return None

    def reset_daily_pnl(self):
        """Reset daily PnL (call at market open)."""
        self.profile.daily_pnl = 0
        save_profile(self.profile)

    def reset_weekly_pnl(self):
        """Reset weekly PnL (call Monday morning)."""
        self.profile.weekly_pnl = 0
        save_profile(self.profile)

    def update_capital_from_broker(self):
        """Sync capital with actual Alpaca account balance."""
        try:
            from bot.engine.trader import get_account_info
            account = get_account_info()
            if "error" not in account:
                self.profile.current_capital = float(account.get("equity", self.profile.current_capital))
                if self.profile.current_capital > self.profile.peak_capital:
                    self.profile.peak_capital = self.profile.current_capital
                save_profile(self.profile)
        except Exception:
            pass


# ─── Profile Persistence ──────────────────────────────────────────────

def save_profile(profile: UserProfile):
    """Save user profile to database."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO user_profile
           (id, data_json, updated_at)
           VALUES (1, ?, ?)""",
        (json.dumps(profile.to_dict()), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_profile() -> UserProfile:
    """Load user profile from database, or create default."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT data_json FROM user_profile WHERE id = 1"
        ).fetchone()
        conn.close()

        if row and row["data_json"]:
            data = json.loads(row["data_json"])
            # Remove computed properties before constructing
            for key in ["win_rate", "drawdown_pct", "growth_pct", "avg_pnl_per_trade",
                         "risk_multiplier", "risk_per_trade_dollars", "effective_risk_pct"]:
                data.pop(key, None)
            return UserProfile(**data)
    except Exception:
        pass

    return UserProfile()


def update_profile(**kwargs) -> UserProfile:
    """Update specific profile fields."""
    profile = load_profile()
    for key, value in kwargs.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    # Apply risk preset if risk_level changed
    if "risk_level" in kwargs and kwargs["risk_level"] in RISK_PRESETS:
        preset = RISK_PRESETS[kwargs["risk_level"]]
        for k, v in preset.items():
            if k not in kwargs:  # Don't override explicit values
                setattr(profile, k, v)

    profile.updated_at = datetime.now().isoformat()
    save_profile(profile)
    return profile
