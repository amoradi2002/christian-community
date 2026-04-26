import json
from bot.db.database import get_connection


def save_strategy(name, strategy_type, description, rules, is_active=True):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO strategies (name, type, description, rules_json, is_active)
           VALUES (?, ?, ?, ?, ?)""",
        (name, strategy_type, description, json.dumps(rules), int(is_active)),
    )
    conn.commit()
    conn.close()


def get_strategy(strategy_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_strategy_by_name(name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM strategies WHERE name = ?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_strategies(active_only=True):
    conn = get_connection()
    if active_only:
        rows = conn.execute("SELECT * FROM strategies WHERE is_active = 1").fetchall()
    else:
        rows = conn.execute("SELECT * FROM strategies").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_strategy(strategy_id, is_active):
    conn = get_connection()
    conn.execute(
        "UPDATE strategies SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (int(is_active), strategy_id),
    )
    conn.commit()
    conn.close()


def delete_strategy(strategy_id):
    conn = get_connection()
    conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()
