"""
Strategy Performance Tracker

Tracks how each trading strategy performs over time so we can:
- Identify which strategies are working and which aren't
- Auto-disable consistently losing strategies
- Compare win rates, R-multiples, and P&L across strategies
- Make data-driven decisions about strategy allocation
"""

from datetime import datetime

from bot.db.database import get_connection


def init_strategy_tracker_table():
    """Create the strategy_performance table if it doesn't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_performance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name   TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            signal_action   TEXT NOT NULL,
            confidence      REAL NOT NULL,
            entry_price     REAL NOT NULL,
            exit_price      REAL,
            pnl_dollars     REAL,
            r_multiple      REAL,
            outcome         TEXT,
            style           TEXT,
            setup           TEXT,
            created_at      TEXT NOT NULL,
            closed_at       TEXT
        )
    """)
    conn.commit()
    conn.close()


def record_signal(
    strategy_name: str,
    symbol: str,
    action: str,
    confidence: float,
    entry_price: float,
    style: str = "general",
    setup: str = None,
) -> int:
    """
    Log when a signal fires. Returns the record ID.

    Args:
        strategy_name: Name of the strategy that produced the signal.
        symbol: Ticker symbol (e.g. "AAPL").
        action: "BUY" or "SELL".
        confidence: Signal confidence 0.0-1.0.
        entry_price: Price at signal time.
        style: Trading style — "day", "swing", or "general".
        setup: Optional setup name (e.g. "VWAP Reclaim", "Gap and Go").

    Returns:
        The integer ID of the new record.
    """
    init_strategy_tracker_table()
    conn = get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """
        INSERT INTO strategy_performance
            (strategy_name, symbol, signal_action, confidence,
             entry_price, outcome, style, setup, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
        """,
        (strategy_name, symbol.upper(), action.upper(), confidence,
         entry_price, style, setup, now),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def close_signal(signal_id: int, exit_price: float) -> dict:
    """
    Close out an open signal and calculate P&L and R-multiple.

    For BUY signals: pnl = exit - entry
    For SELL signals: pnl = entry - exit
    R-multiple uses 2% of entry as default risk.

    Returns a dict with the closed record details.
    """
    init_strategy_tracker_table()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM strategy_performance WHERE id = ?", (signal_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise ValueError(f"Strategy performance record {signal_id} not found")

    if row["outcome"] != "open":
        conn.close()
        raise ValueError(f"Record {signal_id} is already closed (outcome={row['outcome']})")

    entry_price = row["entry_price"]
    action = row["signal_action"]

    # Calculate P&L based on direction
    if action == "BUY":
        pnl_dollars = exit_price - entry_price
    else:  # SELL
        pnl_dollars = entry_price - exit_price

    # R-multiple: use 2% of entry as default risk per share
    risk = entry_price * 0.02
    r_multiple = pnl_dollars / risk if risk > 0 else 0.0

    outcome = "win" if pnl_dollars > 0 else "loss"
    now = datetime.now().isoformat()

    conn.execute(
        """
        UPDATE strategy_performance SET
            exit_price = ?,
            pnl_dollars = ?,
            r_multiple = ?,
            outcome = ?,
            closed_at = ?
        WHERE id = ?
        """,
        (exit_price, round(pnl_dollars, 4), round(r_multiple, 2),
         outcome, now, signal_id),
    )
    conn.commit()

    # Re-fetch the updated row
    updated = conn.execute(
        "SELECT * FROM strategy_performance WHERE id = ?", (signal_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(updated)


def get_strategy_stats() -> dict:
    """
    Returns a dict keyed by strategy_name with aggregated stats:
        total_signals, wins, losses, win_rate, avg_r, total_pnl, avg_confidence

    Only closed trades (win/loss) are counted toward wins/losses/win_rate/avg_r/total_pnl.
    avg_confidence includes all signals (open and closed).
    """
    init_strategy_tracker_table()
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strategy_name,
            COUNT(*) AS total_signals,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
            AVG(CASE WHEN outcome IN ('win', 'loss') THEN r_multiple END) AS avg_r,
            SUM(CASE WHEN outcome IN ('win', 'loss') THEN pnl_dollars ELSE 0 END) AS total_pnl,
            AVG(confidence) AS avg_confidence
        FROM strategy_performance
        GROUP BY strategy_name
        ORDER BY strategy_name
    """).fetchall()
    conn.close()

    stats = {}
    for r in rows:
        closed = (r["wins"] or 0) + (r["losses"] or 0)
        wins = r["wins"] or 0
        win_rate = wins / closed if closed > 0 else 0.0
        stats[r["strategy_name"]] = {
            "total_signals": r["total_signals"],
            "wins": wins,
            "losses": r["losses"] or 0,
            "win_rate": round(win_rate, 4),
            "avg_r": round(r["avg_r"] or 0, 2),
            "total_pnl": round(r["total_pnl"] or 0, 2),
            "avg_confidence": round(r["avg_confidence"] or 0, 4),
        }
    return stats


def get_best_strategies(n: int = 5) -> list[dict]:
    """
    Top N strategies by win rate, requiring a minimum of 5 closed trades.

    Returns a list of dicts with strategy_name and stats.
    """
    init_strategy_tracker_table()
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strategy_name,
            COUNT(*) AS total_signals,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
            AVG(CASE WHEN outcome IN ('win', 'loss') THEN r_multiple END) AS avg_r,
            SUM(CASE WHEN outcome IN ('win', 'loss') THEN pnl_dollars ELSE 0 END) AS total_pnl,
            AVG(confidence) AS avg_confidence
        FROM strategy_performance
        GROUP BY strategy_name
        HAVING (SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)
              + SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END)) >= 5
        ORDER BY
            CAST(SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS REAL)
            / (SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)
             + SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END)) DESC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        closed = (r["wins"] or 0) + (r["losses"] or 0)
        wins = r["wins"] or 0
        win_rate = wins / closed if closed > 0 else 0.0
        results.append({
            "strategy_name": r["strategy_name"],
            "total_signals": r["total_signals"],
            "wins": wins,
            "losses": r["losses"] or 0,
            "win_rate": round(win_rate, 4),
            "avg_r": round(r["avg_r"] or 0, 2),
            "total_pnl": round(r["total_pnl"] or 0, 2),
            "avg_confidence": round(r["avg_confidence"] or 0, 4),
        })
    return results


def get_worst_strategies(n: int = 5) -> list[dict]:
    """
    Bottom N strategies by win rate, requiring a minimum of 5 closed trades.

    Returns a list of dicts with strategy_name and stats.
    """
    init_strategy_tracker_table()
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strategy_name,
            COUNT(*) AS total_signals,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
            AVG(CASE WHEN outcome IN ('win', 'loss') THEN r_multiple END) AS avg_r,
            SUM(CASE WHEN outcome IN ('win', 'loss') THEN pnl_dollars ELSE 0 END) AS total_pnl,
            AVG(confidence) AS avg_confidence
        FROM strategy_performance
        GROUP BY strategy_name
        HAVING (SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)
              + SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END)) >= 5
        ORDER BY
            CAST(SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS REAL)
            / (SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)
             + SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END)) ASC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        closed = (r["wins"] or 0) + (r["losses"] or 0)
        wins = r["wins"] or 0
        win_rate = wins / closed if closed > 0 else 0.0
        results.append({
            "strategy_name": r["strategy_name"],
            "total_signals": r["total_signals"],
            "wins": wins,
            "losses": r["losses"] or 0,
            "win_rate": round(win_rate, 4),
            "avg_r": round(r["avg_r"] or 0, 2),
            "total_pnl": round(r["total_pnl"] or 0, 2),
            "avg_confidence": round(r["avg_confidence"] or 0, 4),
        })
    return results


def get_strategy_history(strategy_name: str, limit: int = 50) -> list[dict]:
    """
    Recent trades for a specific strategy, ordered newest first.

    Returns a list of dicts with full record details.
    """
    init_strategy_tracker_table()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM strategy_performance
        WHERE strategy_name = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (strategy_name, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def should_disable_strategy(
    strategy_name: str,
    min_trades: int = 10,
    min_win_rate: float = 0.3,
) -> bool:
    """
    Returns True if a strategy underperforms and should be disabled.

    A strategy is flagged for disabling when:
    - It has at least `min_trades` closed trades, AND
    - Its win rate is below `min_win_rate`

    If the strategy has fewer than `min_trades` closed trades,
    returns False (not enough data to judge).
    """
    init_strategy_tracker_table()
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses
        FROM strategy_performance
        WHERE strategy_name = ? AND outcome IN ('win', 'loss')
        """,
        (strategy_name,),
    ).fetchone()
    conn.close()

    if not row:
        return False

    wins = row["wins"] or 0
    losses = row["losses"] or 0
    closed = wins + losses

    if closed < min_trades:
        return False

    win_rate = wins / closed
    return win_rate < min_win_rate


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return {
        "id": row["id"],
        "strategy_name": row["strategy_name"],
        "symbol": row["symbol"],
        "signal_action": row["signal_action"],
        "confidence": row["confidence"],
        "entry_price": row["entry_price"],
        "exit_price": row["exit_price"],
        "pnl_dollars": row["pnl_dollars"],
        "r_multiple": row["r_multiple"],
        "outcome": row["outcome"],
        "style": row["style"],
        "setup": row["setup"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
    }
