import json
from datetime import datetime
from bot.db.database import get_connection


def record_signal(strategy_id, symbol, signal_action, entry_price):
    """Record a new signal for performance tracking."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO performance (strategy_id, symbol, signal, entry_price, outcome)
           VALUES (?, ?, ?, ?, 'open')""",
        (strategy_id, symbol, signal_action, entry_price),
    )
    conn.commit()
    conn.close()


def close_position(performance_id, exit_price):
    """Close an open position and calculate P&L."""
    conn = get_connection()
    row = conn.execute(
        "SELECT entry_price, signal FROM performance WHERE id = ?",
        (performance_id,),
    ).fetchone()

    if not row:
        conn.close()
        return

    entry = row["entry_price"]
    signal = row["signal"]

    if signal == "BUY":
        pnl_pct = ((exit_price - entry) / entry) * 100
    else:
        pnl_pct = ((entry - exit_price) / entry) * 100

    outcome = "win" if pnl_pct > 0 else "loss"

    conn.execute(
        """UPDATE performance SET exit_price = ?, pnl_pct = ?, outcome = ?, closed_at = ?
           WHERE id = ?""",
        (exit_price, round(pnl_pct, 2), outcome, datetime.now().isoformat(), performance_id),
    )
    conn.commit()
    conn.close()


def get_strategy_stats(strategy_id=None):
    """Get win/loss stats for strategies."""
    conn = get_connection()
    if strategy_id:
        rows = conn.execute(
            """SELECT outcome, COUNT(*) as cnt, AVG(pnl_pct) as avg_pnl
               FROM performance WHERE strategy_id = ? AND outcome != 'open'
               GROUP BY outcome""",
            (strategy_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT strategy_id, outcome, COUNT(*) as cnt, AVG(pnl_pct) as avg_pnl
               FROM performance WHERE outcome != 'open'
               GROUP BY strategy_id, outcome""",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_positions():
    """Get all open positions."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, s.name as strategy_name
           FROM performance p
           LEFT JOIN strategies s ON p.strategy_id = s.id
           WHERE p.outcome = 'open'""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
