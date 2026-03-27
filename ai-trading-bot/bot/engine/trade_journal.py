"""
Trade Journal System

From the trading skill:
- Log every trade with structured format
- Weekly review with win rate, R multiples, best/worst trade analysis
- Track process score separate from result score
- One lesson per trade

Trade Score: Process /5 (followed rules?) + Result /5 (hit target?) = /10
Target 7+ on process consistently.
"""

import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from bot.db.database import get_connection


@dataclass
class JournalEntry:
    id: int = 0
    date: str = ""
    symbol: str = ""
    style: str = ""  # "day", "swing", "options"
    direction: str = ""  # "long", "short"
    setup: str = ""
    catalyst: str = ""
    catalyst_tier: str = ""

    entry_price: float = 0.0
    entry_time: str = ""
    exit_price: float = 0.0
    exit_time: str = ""
    shares: float = 0.0

    stop_loss: float = 0.0
    target: float = 0.0
    risk_reward_planned: float = 0.0

    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0  # Actual R (positive = winner, negative = loser)

    why_entered: str = ""
    why_exited: str = ""
    what_did_right: str = ""
    what_id_change: str = ""
    lesson: str = ""
    emotion: str = ""  # "Calm", "FOMO", "Revenge", "Confident", "Anxious"

    process_score: int = 0  # /5
    result_score: int = 0   # /5

    candle_pattern: str = ""
    sector: str = ""
    tags: list = field(default_factory=list)

    status: str = "open"  # "open", "closed", "cancelled"
    created_at: str = ""
    closed_at: str = ""

    def total_score(self) -> int:
        return self.process_score + self.result_score

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "symbol": self.symbol,
            "style": self.style,
            "direction": self.direction,
            "setup": self.setup,
            "catalyst": self.catalyst,
            "catalyst_tier": self.catalyst_tier,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "shares": self.shares,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "risk_reward_planned": self.risk_reward_planned,
            "pnl_dollars": self.pnl_dollars,
            "pnl_pct": self.pnl_pct,
            "r_multiple": self.r_multiple,
            "why_entered": self.why_entered,
            "why_exited": self.why_exited,
            "what_did_right": self.what_did_right,
            "what_id_change": self.what_id_change,
            "lesson": self.lesson,
            "emotion": self.emotion,
            "process_score": self.process_score,
            "result_score": self.result_score,
            "candle_pattern": self.candle_pattern,
            "sector": self.sector,
            "tags": self.tags,
            "status": self.status,
            "total_score": self.total_score(),
        }


def init_journal_table():
    """Create the trade journal table if it doesn't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            style           TEXT,
            direction       TEXT,
            setup           TEXT,
            catalyst        TEXT,
            catalyst_tier   TEXT,
            entry_price     REAL,
            entry_time      TEXT,
            exit_price      REAL,
            exit_time       TEXT,
            shares          REAL,
            stop_loss       REAL,
            target          REAL,
            rr_planned      REAL,
            pnl_dollars     REAL DEFAULT 0,
            pnl_pct         REAL DEFAULT 0,
            r_multiple      REAL DEFAULT 0,
            why_entered     TEXT,
            why_exited      TEXT,
            what_did_right  TEXT,
            what_id_change  TEXT,
            lesson          TEXT,
            emotion         TEXT,
            process_score   INTEGER DEFAULT 0,
            result_score    INTEGER DEFAULT 0,
            candle_pattern  TEXT,
            sector          TEXT,
            tags_json       TEXT DEFAULT '[]',
            status          TEXT DEFAULT 'open',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at       TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def log_trade(entry: JournalEntry) -> int:
    """Log a new trade to the journal. Returns the entry ID."""
    init_journal_table()
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO trade_journal
        (date, symbol, style, direction, setup, catalyst, catalyst_tier,
         entry_price, entry_time, shares, stop_loss, target, rr_planned,
         why_entered, candle_pattern, sector, tags_json, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entry.date or datetime.now().strftime("%Y-%m-%d"),
        entry.symbol, entry.style, entry.direction, entry.setup,
        entry.catalyst, entry.catalyst_tier,
        entry.entry_price, entry.entry_time, entry.shares,
        entry.stop_loss, entry.target, entry.risk_reward_planned,
        entry.why_entered, entry.candle_pattern, entry.sector,
        json.dumps(entry.tags), "open",
    ))
    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def close_trade(
    entry_id: int,
    exit_price: float,
    exit_time: str = "",
    why_exited: str = "",
    what_did_right: str = "",
    what_id_change: str = "",
    lesson: str = "",
    emotion: str = "",
    process_score: int = 0,
    result_score: int = 0,
) -> JournalEntry:
    """Close an open trade and calculate P&L."""
    init_journal_table()
    conn = get_connection()
    row = conn.execute("SELECT * FROM trade_journal WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Trade journal entry {entry_id} not found")

    entry_price = row["entry_price"]
    shares = row["shares"] or 1
    direction = row["direction"]
    stop_loss = row["stop_loss"]

    # Calculate P&L
    if direction == "short":
        pnl_dollars = (entry_price - exit_price) * shares
    else:
        pnl_dollars = (exit_price - entry_price) * shares

    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
    if direction == "short":
        pnl_pct = -pnl_pct

    # Calculate R multiple
    risk_per_share = abs(entry_price - stop_loss) if stop_loss > 0 else entry_price * 0.02
    if direction == "short":
        actual_per_share = entry_price - exit_price
    else:
        actual_per_share = exit_price - entry_price
    r_multiple = actual_per_share / risk_per_share if risk_per_share > 0 else 0

    now = datetime.now().isoformat()
    conn.execute("""
        UPDATE trade_journal SET
            exit_price = ?, exit_time = ?, pnl_dollars = ?, pnl_pct = ?,
            r_multiple = ?, why_exited = ?, what_did_right = ?,
            what_id_change = ?, lesson = ?, emotion = ?,
            process_score = ?, result_score = ?, status = 'closed', closed_at = ?
        WHERE id = ?
    """, (
        exit_price, exit_time or now, round(pnl_dollars, 2), round(pnl_pct, 2),
        round(r_multiple, 2), why_exited, what_did_right,
        what_id_change, lesson, emotion,
        process_score, result_score, now, entry_id,
    ))
    conn.commit()
    conn.close()

    return get_trade(entry_id)


def get_trade(entry_id: int) -> JournalEntry:
    """Get a specific journal entry."""
    init_journal_table()
    conn = get_connection()
    row = conn.execute("SELECT * FROM trade_journal WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Trade {entry_id} not found")
    return _row_to_entry(row)


def get_trades(status: str = None, symbol: str = None, style: str = None,
               limit: int = 50) -> list[JournalEntry]:
    """Get trade journal entries with optional filters."""
    init_journal_table()
    conn = get_connection()
    query = "SELECT * FROM trade_journal WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())
    if style:
        query += " AND style = ?"
        params.append(style)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_entry(r) for r in rows]


def weekly_review(weeks_ago: int = 0) -> dict:
    """
    Generate weekly review stats.

    Weekly Review (Sunday):
    - Total P&L
    - Win rate
    - Avg R winner vs loser
    - Best trade (why)
    - Worst trade (why)
    - Rule broken?
    - One focus for next week
    """
    init_journal_table()
    conn = get_connection()

    # Calculate date range
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday() + 7 * weeks_ago)
    end_of_week = start_of_week + timedelta(days=7)
    start_str = start_of_week.strftime("%Y-%m-%d")
    end_str = end_of_week.strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT * FROM trade_journal
        WHERE status = 'closed' AND date >= ? AND date < ?
        ORDER BY pnl_dollars DESC
    """, (start_str, end_str)).fetchall()
    conn.close()

    trades = [_row_to_entry(r) for r in rows]

    if not trades:
        return {
            "week": f"{start_str} to {end_str}",
            "total_trades": 0,
            "message": "No closed trades this week",
        }

    winners = [t for t in trades if t.pnl_dollars > 0]
    losers = [t for t in trades if t.pnl_dollars < 0]
    total_pnl = sum(t.pnl_dollars for t in trades)
    win_rate = len(winners) / len(trades) if trades else 0

    avg_r_winner = sum(t.r_multiple for t in winners) / len(winners) if winners else 0
    avg_r_loser = sum(t.r_multiple for t in losers) / len(losers) if losers else 0

    best = trades[0] if trades else None
    worst = trades[-1] if trades else None

    avg_process = sum(t.process_score for t in trades) / len(trades) if trades else 0

    # Detect broken rules
    rules_broken = []
    for t in trades:
        if t.process_score < 3:
            rules_broken.append(f"{t.symbol}: Low process score ({t.process_score}/5)")
        if t.risk_reward_planned > 0 and t.risk_reward_planned < 2.0:
            rules_broken.append(f"{t.symbol}: Took trade with R:R below 2:1")

    return {
        "week": f"{start_str} to {end_str}",
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(win_rate * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_r_winner": round(avg_r_winner, 2),
        "avg_r_loser": round(avg_r_loser, 2),
        "avg_process_score": round(avg_process, 1),
        "best_trade": best.to_dict() if best else None,
        "worst_trade": worst.to_dict() if worst else None,
        "rules_broken": rules_broken,
        "by_style": {
            "day": len([t for t in trades if t.style == "day"]),
            "swing": len([t for t in trades if t.style == "swing"]),
            "options": len([t for t in trades if t.style == "options"]),
        },
    }


def _row_to_entry(row) -> JournalEntry:
    """Convert a database row to a JournalEntry."""
    return JournalEntry(
        id=row["id"],
        date=row["date"],
        symbol=row["symbol"],
        style=row["style"] or "",
        direction=row["direction"] or "",
        setup=row["setup"] or "",
        catalyst=row["catalyst"] or "",
        catalyst_tier=row["catalyst_tier"] or "",
        entry_price=row["entry_price"] or 0,
        entry_time=row["entry_time"] or "",
        exit_price=row["exit_price"] or 0,
        exit_time=row["exit_time"] or "",
        shares=row["shares"] or 0,
        stop_loss=row["stop_loss"] or 0,
        target=row["target"] or 0,
        risk_reward_planned=row["rr_planned"] or 0,
        pnl_dollars=row["pnl_dollars"] or 0,
        pnl_pct=row["pnl_pct"] or 0,
        r_multiple=row["r_multiple"] or 0,
        why_entered=row["why_entered"] or "",
        why_exited=row["why_exited"] or "",
        what_did_right=row["what_did_right"] or "",
        what_id_change=row["what_id_change"] or "",
        lesson=row["lesson"] or "",
        emotion=row["emotion"] or "",
        process_score=row["process_score"] or 0,
        result_score=row["result_score"] or 0,
        candle_pattern=row["candle_pattern"] or "",
        sector=row["sector"] or "",
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        status=row["status"] or "open",
        created_at=row["created_at"] or "",
        closed_at=row["closed_at"] or "",
    )
