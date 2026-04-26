"""
Daily P&L Tracker - Granular daily profit/loss tracking with lockout enforcement.

Works alongside the RiskManager to enforce the 3% daily loss lockout rule.
Every closed trade records its P&L here, giving you:
- Per-symbol breakdown of today's performance
- Win/loss counts for the day
- Automatic lockout when losses exceed the daily limit
- Rolling 7-day history for trend analysis

Data is persisted in SQLite so it survives restarts.

Table: daily_pnl_entries
    id          INTEGER PRIMARY KEY
    date        TEXT    (YYYY-MM-DD)
    amount      REAL    (positive = profit, negative = loss)
    symbol      TEXT
    strategy    TEXT
    trade_type  TEXT    ("day", "swing", "options")
    created_at  TEXT    (ISO timestamp)
"""

from datetime import datetime, timedelta

from bot.db.database import get_connection
from bot.engine.risk_manager import load_profile


_TABLE_CREATED = False


def _ensure_table():
    """Create the daily_pnl_entries table if it doesn't exist."""
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            symbol      TEXT    NOT NULL,
            strategy    TEXT    NOT NULL DEFAULT '',
            trade_type  TEXT    NOT NULL DEFAULT 'day',
            created_at  TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_pnl_date
        ON daily_pnl_entries (date)
    """)
    conn.commit()
    conn.close()
    _TABLE_CREATED = True


class DailyPnLTracker:
    """
    Tracks per-trade P&L entries for each calendar day and enforces
    the daily loss lockout rule from the user's risk profile.
    """

    def __init__(self):
        _ensure_table()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_pnl(self, amount: float, symbol: str, strategy: str = "",
                   trade_type: str = "day"):
        """
        Record a P&L entry for today.

        Args:
            amount: Dollar profit (positive) or loss (negative).
            symbol: Ticker symbol.
            strategy: Strategy name that generated the trade.
            trade_type: One of "day", "swing", "options".
        """
        now = datetime.now()
        conn = get_connection()
        conn.execute(
            """INSERT INTO daily_pnl_entries
               (date, amount, symbol, strategy, trade_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                now.strftime("%Y-%m-%d"),
                amount,
                symbol.upper(),
                strategy,
                trade_type,
                now.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_today_pnl(self) -> dict:
        """
        Return a summary of today's P&L.

        Keys:
            total_pnl       - Net P&L for the day
            trade_count     - Number of closed trades recorded today
            winners         - Count of profitable trades
            losers          - Count of losing trades
            is_locked_out   - True if daily loss limit is breached
            pnl_by_symbol   - {symbol: total_pnl} breakdown
        """
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_connection()
        rows = conn.execute(
            "SELECT amount, symbol FROM daily_pnl_entries WHERE date = ?",
            (today,),
        ).fetchall()
        conn.close()

        total_pnl = 0.0
        winners = 0
        losers = 0
        pnl_by_symbol: dict[str, float] = {}

        for row in rows:
            amt = row["amount"]
            sym = row["symbol"]
            total_pnl += amt
            if amt > 0:
                winners += 1
            elif amt < 0:
                losers += 1
            pnl_by_symbol[sym] = pnl_by_symbol.get(sym, 0.0) + amt

        # Round aggregated values
        total_pnl = round(total_pnl, 2)
        pnl_by_symbol = {s: round(v, 2) for s, v in pnl_by_symbol.items()}

        return {
            "total_pnl": total_pnl,
            "trade_count": len(rows),
            "winners": winners,
            "losers": losers,
            "is_locked_out": self.is_locked_out(),
            "pnl_by_symbol": pnl_by_symbol,
        }

    def is_locked_out(self) -> bool:
        """
        True if today's cumulative losses exceed the daily loss limit
        (default 3% of current capital, from the user's risk profile).
        """
        profile = load_profile()
        limit = profile.current_capital * (profile.daily_loss_limit_pct / 100)

        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM daily_pnl_entries WHERE date = ?",
            (today,),
        ).fetchone()
        conn.close()

        total_pnl = row["total"] if row else 0.0
        # Locked out when losses exceed the limit (total_pnl is negative)
        return total_pnl <= -limit

    def get_lockout_reason(self) -> str:
        """
        Human-readable lockout message, or empty string if not locked out.
        """
        if not self.is_locked_out():
            return ""

        profile = load_profile()
        limit = round(profile.current_capital * (profile.daily_loss_limit_pct / 100), 2)

        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM daily_pnl_entries WHERE date = ?",
            (today,),
        ).fetchone()
        conn.close()

        total_pnl = round(row["total"], 2) if row else 0.0

        return (
            f"Daily loss limit reached: ${total_pnl:.2f} lost today "
            f"(limit is ${limit:.2f}, {profile.daily_loss_limit_pct:.1f}% of "
            f"${profile.current_capital:.2f} capital). "
            f"Trading is locked for the rest of the day."
        )

    def get_weekly_daily_pnl(self) -> list[dict]:
        """
        Return daily P&L totals for the last 7 calendar days.

        Each entry: {date, total_pnl, trade_count, winners, losers}
        Ordered oldest to newest.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=6)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        conn = get_connection()
        rows = conn.execute(
            """SELECT date, amount
               FROM daily_pnl_entries
               WHERE date >= ? AND date <= ?
               ORDER BY date, id""",
            (start_str, end_str),
        ).fetchall()
        conn.close()

        # Aggregate by date
        by_date: dict[str, dict] = {}
        for row in rows:
            d = row["date"]
            if d not in by_date:
                by_date[d] = {"date": d, "total_pnl": 0.0, "trade_count": 0,
                              "winners": 0, "losers": 0}
            entry = by_date[d]
            amt = row["amount"]
            entry["total_pnl"] += amt
            entry["trade_count"] += 1
            if amt > 0:
                entry["winners"] += 1
            elif amt < 0:
                entry["losers"] += 1

        # Round P&L values
        for entry in by_date.values():
            entry["total_pnl"] = round(entry["total_pnl"], 2)

        # Build list for all 7 days, filling in zeros for days with no trades
        result = []
        for i in range(7):
            d = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            if d in by_date:
                result.append(by_date[d])
            else:
                result.append({"date": d, "total_pnl": 0.0, "trade_count": 0,
                               "winners": 0, "losers": 0})

        return result

    def reset_day(self):
        """
        Called at market open to signal the start of a new trading day.

        Since entries are keyed by date, there is nothing to "reset" in the
        database -- new entries will naturally land under today's date. This
        method exists for any callers that want an explicit reset hook, and
        it clears the module-level table-creation flag so the table check
        runs again on the next operation (useful after DB migrations).
        """
        global _TABLE_CREATED
        _TABLE_CREATED = False
        _ensure_table()
