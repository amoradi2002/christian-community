"""
Paper Trading Execution Module - simulate trades without real money.

Provides a full paper trading environment backed by SQLite. Integrates with the
RiskManager for position sizing and the Signal dataclass for trade entry.
Supports automatic execution of high-confidence signals when configured.

Usage:
    from bot.engine.paper_trader import PaperTrader

    trader = PaperTrader()
    trade = trader.execute_signal(signal, current_price=150.25)
    closed = trader.check_stops_and_targets({"AAPL": 148.00})
    summary = trader.get_performance_summary()
"""

import sqlite3
from datetime import datetime, date

from bot.config.settings import CONFIG
from bot.db.database import get_connection
from bot.engine.risk_manager import RiskManager
from bot.engine.signal import Signal


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL,
    target_price REAL,
    exit_price REAL,
    pnl_dollars REAL,
    status TEXT NOT NULL DEFAULT 'open',
    strategy_name TEXT NOT NULL DEFAULT '',
    signal_confidence REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    notes TEXT
);
"""


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


class PaperTrader:
    """
    Simulated trade execution engine.

    Records trades in a local SQLite table, checks stops and targets against
    live prices, and calculates portfolio-level performance metrics.  All
    position sizing is delegated to RiskManager so that risk rules are
    enforced identically to live trading.
    """

    def __init__(self):
        self.paper_cfg = CONFIG.get("paper_trading", {})
        self.auto_execute = self.paper_cfg.get("auto_execute", False)
        self.confidence_threshold = self.paper_cfg.get("confidence_threshold", 0.70)
        self.starting_capital = self.paper_cfg.get("starting_capital", 10_000.0)
        self.risk_manager = RiskManager()
        self._init_db()

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _init_db(self):
        """Ensure the paper_trades table exists."""
        conn = get_connection()
        conn.executescript(_CREATE_TABLE_SQL)
        conn.close()

    def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

    def _fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        conn = get_connection()
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return _row_to_dict(row) if row else None

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a write query and return lastrowid."""
        conn = get_connection()
        cur = conn.execute(sql, params)
        conn.commit()
        last_id = cur.lastrowid
        conn.close()
        return last_id

    # ------------------------------------------------------------------
    # Core trading operations
    # ------------------------------------------------------------------

    def execute_signal(self, signal: Signal, current_price: float) -> dict | None:
        """
        Execute a paper trade from a Signal object.

        Uses RiskManager.calculate_position_size to determine quantity.
        Returns the new trade dict, or None if the risk check fails.
        """
        if signal.action not in ("BUY", "SELL"):
            return None

        # Auto-execute gate: skip low-confidence signals when in auto mode
        if self.auto_execute and signal.confidence < self.confidence_threshold:
            return None

        side = signal.action.lower()

        # Determine stop-loss percentage for the risk manager
        stop_loss_pct = None
        if signal.stop_loss and signal.stop_loss > 0 and current_price > 0:
            if side == "buy":
                stop_loss_pct = ((current_price - signal.stop_loss) / current_price) * 100
            else:
                stop_loss_pct = ((signal.stop_loss - current_price) / current_price) * 100
            # Clamp to something reasonable
            if stop_loss_pct <= 0:
                stop_loss_pct = None

        sizing = self.risk_manager.calculate_position_size(
            symbol=signal.symbol,
            price=current_price,
            stop_loss_pct=stop_loss_pct,
            confidence=signal.confidence,
        )

        if not sizing.get("can_trade"):
            return None

        quantity = sizing["shares"]
        if quantity < 1:
            return None

        stop_loss = signal.stop_loss if signal.stop_loss else sizing.get("stop_loss_price")
        target_price = signal.target if signal.target else sizing.get("take_profit_price")

        now_iso = datetime.now().isoformat()

        trade_id = self._execute(
            """INSERT INTO paper_trades
               (symbol, side, quantity, entry_price, stop_loss, target_price,
                status, strategy_name, signal_confidence, created_at, notes)
               VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
            (
                signal.symbol,
                side,
                quantity,
                round(current_price, 4),
                round(stop_loss, 4) if stop_loss else None,
                round(target_price, 4) if target_price else None,
                signal.strategy_name,
                round(signal.confidence, 4),
                now_iso,
                "; ".join(signal.reasons) if signal.reasons else None,
            ),
        )

        trade = self._fetch_one("SELECT * FROM paper_trades WHERE id = ?", (trade_id,))
        return trade

    def close_trade(self, trade_id: int, exit_price: float, reason: str = "manual") -> dict | None:
        """
        Close an open paper trade at *exit_price*.

        Calculates realised PnL and updates the RiskManager profile.
        Returns the updated trade dict, or None if the trade was not found
        or was already closed.
        """
        trade = self._fetch_one(
            "SELECT * FROM paper_trades WHERE id = ? AND status = 'open'",
            (trade_id,),
        )
        if not trade:
            return None

        if trade["side"] == "buy":
            pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
        else:
            pnl = (trade["entry_price"] - exit_price) * trade["quantity"]

        pnl = round(pnl, 2)
        now_iso = datetime.now().isoformat()

        status = reason if reason in ("stopped_out", "target_hit") else "closed"

        existing_notes = trade["notes"] or ""
        note_suffix = f"closed: {reason}"
        new_notes = f"{existing_notes}; {note_suffix}" if existing_notes else note_suffix

        self._execute(
            """UPDATE paper_trades
               SET exit_price = ?, pnl_dollars = ?, status = ?,
                   closed_at = ?, notes = ?
               WHERE id = ?""",
            (round(exit_price, 4), pnl, status, now_iso, new_notes, trade_id),
        )

        # Update the risk manager profile with this result
        self.risk_manager.record_trade_result(pnl, symbol=trade["symbol"])

        return self._fetch_one("SELECT * FROM paper_trades WHERE id = ?", (trade_id,))

    def check_stops_and_targets(self, current_prices: dict) -> list[dict]:
        """
        Scan all open trades and auto-close any whose stop-loss or target
        has been hit.

        Args:
            current_prices: mapping of symbol -> current market price

        Returns:
            List of trade dicts that were closed during this check.
        """
        open_trades = self._fetch_all("SELECT * FROM paper_trades WHERE status = 'open'")
        closed: list[dict] = []

        for trade in open_trades:
            symbol = trade["symbol"]
            price = current_prices.get(symbol)
            if price is None:
                continue

            stop = trade["stop_loss"]
            target = trade["target_price"]

            if trade["side"] == "buy":
                if stop is not None and price <= stop:
                    result = self.close_trade(trade["id"], price, reason="stopped_out")
                    if result:
                        closed.append(result)
                elif target is not None and price >= target:
                    result = self.close_trade(trade["id"], price, reason="target_hit")
                    if result:
                        closed.append(result)
            else:  # sell / short
                if stop is not None and price >= stop:
                    result = self.close_trade(trade["id"], price, reason="stopped_out")
                    if result:
                        closed.append(result)
                elif target is not None and price <= target:
                    result = self.close_trade(trade["id"], price, reason="target_hit")
                    if result:
                        closed.append(result)

        return closed

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_open_positions(self) -> list[dict]:
        """Return all open paper trades."""
        return self._fetch_all(
            "SELECT * FROM paper_trades WHERE status = 'open' ORDER BY created_at DESC"
        )

    def get_portfolio_value(self, current_prices: dict) -> float:
        """
        Calculate total portfolio value: starting capital + realised PnL
        from closed trades + unrealised PnL from open positions.
        """
        # Realised PnL
        row = self._fetch_one(
            "SELECT COALESCE(SUM(pnl_dollars), 0.0) AS total FROM paper_trades WHERE status != 'open'"
        )
        realised = row["total"] if row else 0.0

        # Unrealised PnL
        open_trades = self.get_open_positions()
        unrealised = 0.0
        for trade in open_trades:
            price = current_prices.get(trade["symbol"])
            if price is None:
                continue
            if trade["side"] == "buy":
                unrealised += (price - trade["entry_price"]) * trade["quantity"]
            else:
                unrealised += (trade["entry_price"] - price) * trade["quantity"]

        return round(self.starting_capital + realised + unrealised, 2)

    def get_trade_history(self, limit: int = 50) -> list[dict]:
        """Return recent closed trades, newest first."""
        return self._fetch_all(
            "SELECT * FROM paper_trades WHERE status != 'open' ORDER BY closed_at DESC LIMIT ?",
            (limit,),
        )

    def get_daily_pnl(self) -> float:
        """Return today's total realised PnL from paper trades."""
        today_str = date.today().isoformat()
        row = self._fetch_one(
            """SELECT COALESCE(SUM(pnl_dollars), 0.0) AS total
               FROM paper_trades
               WHERE status != 'open' AND closed_at LIKE ?""",
            (f"{today_str}%",),
        )
        return round(row["total"], 2) if row else 0.0

    def get_performance_summary(self) -> dict:
        """
        Aggregate performance across all paper trades.

        Returns dict with: total_trades, wins, losses, win_rate,
        total_pnl, best_trade, worst_trade, avg_hold_time_hours.
        """
        closed = self._fetch_all(
            "SELECT * FROM paper_trades WHERE status != 'open'"
        )

        total = len(closed)
        if total == 0:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "avg_hold_time_hours": 0.0,
                "open_positions": len(self.get_open_positions()),
            }

        wins = sum(1 for t in closed if (t["pnl_dollars"] or 0) > 0)
        losses = sum(1 for t in closed if (t["pnl_dollars"] or 0) < 0)
        pnls = [t["pnl_dollars"] or 0.0 for t in closed]

        # Average hold time
        hold_seconds: list[float] = []
        for t in closed:
            if t["created_at"] and t["closed_at"]:
                try:
                    opened = datetime.fromisoformat(t["created_at"])
                    closed_dt = datetime.fromisoformat(t["closed_at"])
                    hold_seconds.append((closed_dt - opened).total_seconds())
                except (ValueError, TypeError):
                    pass

        avg_hold_hours = 0.0
        if hold_seconds:
            avg_hold_hours = round(sum(hold_seconds) / len(hold_seconds) / 3600, 2)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / total * 100, 2) if total else 0.0,
            "total_pnl": round(sum(pnls), 2),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
            "avg_hold_time_hours": avg_hold_hours,
            "open_positions": len(self.get_open_positions()),
        }
