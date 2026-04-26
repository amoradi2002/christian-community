"""
Fidelity broker integration - CSV import and manual tracking.

Fidelity does not provide a public trading API, so this module implements:
- CSV import: parse position/trade exports from Fidelity's website.
- Manual position tracking in SQLite (table: fidelity_positions).
- Alert-only mode: the bot generates swing-trade signals but the user
  executes them manually in Fidelity's interface.
- Swing-trade P&L tracking over time.

HOW TO EXPORT FROM FIDELITY
----------------------------
1. Log in to Fidelity.com -> Accounts -> Positions.
2. Click the "Download" icon (top-right of the positions table).
3. Choose "Download to Spreadsheet (.csv)".
4. Save the file and pass its path to ``import_positions_csv()``.

For trade history:
1. Go to Accounts -> Activity & Orders -> History.
2. Set the date range and click "Download".
3. Save and pass to ``import_trades_csv()``.

Environment variables (optional):
    FIDELITY_CSV_DIR - directory to watch for new CSV exports
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from bot.brokers.base import BaseBroker
from bot.db.database import get_connection

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# SQL for the local tracking table
# ------------------------------------------------------------------
_CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS fidelity_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    qty             REAL NOT NULL DEFAULT 0,
    avg_entry       REAL NOT NULL DEFAULT 0,
    current_price   REAL NOT NULL DEFAULT 0,
    market_value    REAL NOT NULL DEFAULT 0,
    unrealized_pnl  REAL NOT NULL DEFAULT 0,
    account_name    TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    updated_at      TEXT NOT NULL
);
"""

_CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS fidelity_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    qty             REAL NOT NULL,
    price           REAL NOT NULL,
    total           REAL NOT NULL DEFAULT 0,
    trade_date      TEXT NOT NULL,
    description     TEXT DEFAULT '',
    imported_at     TEXT NOT NULL
);
"""

_CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS fidelity_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    action          TEXT NOT NULL,
    reason          TEXT DEFAULT '',
    target_price    REAL DEFAULT 0,
    stop_price      REAL DEFAULT 0,
    created_at      TEXT NOT NULL,
    executed        INTEGER DEFAULT 0,
    executed_at     TEXT DEFAULT ''
);
"""


class FidelityBroker(BaseBroker):
    """Fidelity integration via CSV import and manual position tracking.

    Since Fidelity has no public API, this broker operates in alert-only
    mode: it tracks positions the user manually imports and generates
    alerts (stored in ``fidelity_alerts``) for swing-trade signals.
    """

    def __init__(self):
        self._connected = False
        self._csv_dir = os.getenv("FIDELITY_CSV_DIR", "")
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create SQLite tables if they do not exist."""
        try:
            conn = get_connection()
            conn.executescript(
                _CREATE_POSITIONS_TABLE + _CREATE_TRADES_TABLE + _CREATE_ALERTS_TABLE
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("Fidelity: table creation failed - %s", exc)

    # ------------------------------------------------------------------
    # Connection (no real connection - always "connected")
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Mark the Fidelity tracker as ready.

        There is no real connection to establish.  If FIDELITY_CSV_DIR
        is set we verify the directory exists.
        """
        if self._csv_dir and not Path(self._csv_dir).is_dir():
            logger.warning(
                "Fidelity: FIDELITY_CSV_DIR '%s' does not exist; "
                "CSV auto-import disabled", self._csv_dir,
            )
        self._connected = True
        logger.info("Fidelity: tracker initialised (alert-only mode)")
        return True

    def is_connected(self) -> bool:
        return self._connected

    @property
    def broker_name(self) -> str:
        return "fidelity"

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Return aggregated account information from locally tracked positions."""
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT COALESCE(SUM(market_value), 0) AS equity, "
                "       COUNT(*) AS positions "
                "FROM fidelity_positions WHERE qty > 0"
            ).fetchone()
            conn.close()

            equity = float(row["equity"]) if row else 0.0
            num_positions = int(row["positions"]) if row else 0

            return {
                "cash": 0.0,  # not available without API
                "buying_power": 0.0,
                "equity": equity,
                "positions": num_positions,
                "broker": self.broker_name,
                "note": "Values from last CSV import. Cash/buying_power unavailable.",
            }
        except Exception as exc:
            logger.error("Fidelity: get_account failed - %s", exc)
            return {"error": str(exc), "broker": self.broker_name}

    def get_positions(self) -> list[dict]:
        """Return tracked positions from the local database."""
        positions: list[dict] = []
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM fidelity_positions WHERE qty > 0 ORDER BY symbol"
            ).fetchall()
            conn.close()

            for r in rows:
                positions.append({
                    "symbol": r["symbol"],
                    "qty": r["qty"],
                    "side": "long" if r["qty"] > 0 else "short",
                    "avg_entry": r["avg_entry"],
                    "current_price": r["current_price"],
                    "market_value": r["market_value"],
                    "unrealized_pnl": r["unrealized_pnl"],
                    "account_name": r["account_name"],
                    "broker": self.broker_name,
                })
        except Exception as exc:
            logger.error("Fidelity: get_positions failed - %s", exc)
        return positions

    # ------------------------------------------------------------------
    # Orders - alert-only mode
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> dict:
        """Generate a trade alert (Fidelity has no API for order execution).

        The alert is stored in SQLite and can be surfaced to the user
        via Discord/Telegram/dashboard.
        """
        alert = self._create_alert(
            symbol=symbol,
            action=f"{side} {qty} shares",
            reason=f"{order_type} order | limit={limit_price} stop={stop_price}",
            target_price=limit_price or 0,
            stop_price=stop_price or 0,
        )
        return {
            "success": True,
            "order_id": f"fidelity-alert-{alert['id']}",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "filled_price": 0,
            "status": "alert_created",
            "error": "",
            "note": "Alert-only mode. Execute this trade manually in Fidelity.",
        }

    def place_option_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
    ) -> dict:
        """Generate an options trade alert."""
        alert = self._create_alert(
            symbol=symbol,
            action=f"{side} {qty} option contracts",
            reason=f"{order_type} | limit={limit_price}",
            target_price=limit_price or 0,
        )
        return {
            "success": True,
            "order_id": f"fidelity-alert-{alert['id']}",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "filled_price": 0,
            "status": "alert_created",
            "error": "",
            "note": "Alert-only mode. Execute this options trade manually in Fidelity.",
        }

    def get_option_chain(self, symbol: str) -> dict:
        """Not available for Fidelity (no API)."""
        logger.info("Fidelity: option chain not available - use another broker or data source")
        return {}

    def cancel_order(self, order_id: str) -> bool:
        """Mark an alert as cancelled."""
        try:
            alert_id = order_id.replace("fidelity-alert-", "")
            conn = get_connection()
            conn.execute(
                "DELETE FROM fidelity_alerts WHERE id = ?", (alert_id,)
            )
            conn.commit()
            conn.close()
            logger.info("Fidelity: deleted alert %s", alert_id)
            return True
        except Exception as exc:
            logger.error("Fidelity: cancel_order failed - %s", exc)
            return False

    def get_orders(self, status: str = "open") -> list[dict]:
        """Return alerts as pseudo-orders."""
        orders: list[dict] = []
        try:
            conn = get_connection()
            if status == "open":
                rows = conn.execute(
                    "SELECT * FROM fidelity_alerts WHERE executed = 0 ORDER BY created_at DESC"
                ).fetchall()
            elif status == "closed":
                rows = conn.execute(
                    "SELECT * FROM fidelity_alerts WHERE executed = 1 ORDER BY executed_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fidelity_alerts ORDER BY created_at DESC"
                ).fetchall()
            conn.close()

            for r in rows:
                orders.append({
                    "id": f"fidelity-alert-{r['id']}",
                    "symbol": r["symbol"],
                    "side": r["action"],
                    "qty": 0,
                    "type": "alert",
                    "status": "executed" if r["executed"] else "pending",
                    "filled_price": 0,
                    "submitted_at": r["created_at"],
                    "filled_at": r["executed_at"] or "",
                    "broker": self.broker_name,
                })
        except Exception as exc:
            logger.error("Fidelity: get_orders failed - %s", exc)
        return orders

    # ------------------------------------------------------------------
    # CSV Import
    # ------------------------------------------------------------------

    def import_positions_csv(self, filepath: str) -> int:
        """Import positions from a Fidelity CSV export.

        Fidelity's position CSV typically has columns:
            Account Name/Number, Symbol, Description, Quantity,
            Last Price, Current Value, ...

        Returns:
            Number of positions imported.
        """
        imported = 0
        try:
            conn = get_connection()
            # Clear previous positions before importing fresh snapshot
            conn.execute("DELETE FROM fidelity_positions")

            with open(filepath, "r", newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                now = datetime.now().isoformat()

                for row in reader:
                    symbol = self._clean_csv_value(row.get("Symbol", "")).upper()
                    if not symbol or symbol in ("CASH", "PENDING ACTIVITY", ""):
                        continue

                    qty = self._parse_number(row.get("Quantity", "0"))
                    last_price = self._parse_number(row.get("Last Price", "0"))
                    current_value = self._parse_number(row.get("Current Value", "0"))
                    cost_basis_per_share = self._parse_number(
                        row.get("Cost Basis Per Share", row.get("Average Cost Basis", "0"))
                    )

                    avg_entry = cost_basis_per_share if cost_basis_per_share else (
                        current_value / qty if qty else 0
                    )
                    unrealized_pnl = (last_price - avg_entry) * qty if qty else 0

                    conn.execute(
                        """INSERT INTO fidelity_positions
                           (symbol, qty, avg_entry, current_price, market_value,
                            unrealized_pnl, account_name, description, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            symbol, qty, avg_entry, last_price, current_value,
                            unrealized_pnl,
                            self._clean_csv_value(row.get("Account Name/Number", "")),
                            self._clean_csv_value(row.get("Description", "")),
                            now,
                        ),
                    )
                    imported += 1

            conn.commit()
            conn.close()
            logger.info("Fidelity: imported %d positions from %s", imported, filepath)

        except FileNotFoundError:
            logger.error("Fidelity: CSV file not found: %s", filepath)
        except Exception as exc:
            logger.error("Fidelity: import_positions_csv failed - %s", exc)

        return imported

    def import_trades_csv(self, filepath: str) -> int:
        """Import trade history from a Fidelity CSV export.

        Expected columns: Run Date, Action, Symbol, Description,
                          Quantity, Price, Amount

        Returns:
            Number of trades imported.
        """
        imported = 0
        try:
            conn = get_connection()

            with open(filepath, "r", newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                now = datetime.now().isoformat()

                for row in reader:
                    symbol = self._clean_csv_value(row.get("Symbol", "")).upper()
                    action = self._clean_csv_value(row.get("Action", ""))
                    if not symbol or not action:
                        continue

                    side = "buy" if "bought" in action.lower() or "buy" in action.lower() else "sell"
                    qty = abs(self._parse_number(row.get("Quantity", "0")))
                    price = self._parse_number(row.get("Price", "0"))
                    total = self._parse_number(row.get("Amount", "0"))
                    trade_date = self._clean_csv_value(row.get("Run Date", now))

                    conn.execute(
                        """INSERT INTO fidelity_trades
                           (symbol, side, qty, price, total, trade_date,
                            description, imported_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (symbol, side, qty, price, total, trade_date,
                         self._clean_csv_value(row.get("Description", "")), now),
                    )
                    imported += 1

            conn.commit()
            conn.close()
            logger.info("Fidelity: imported %d trades from %s", imported, filepath)

        except FileNotFoundError:
            logger.error("Fidelity: CSV file not found: %s", filepath)
        except Exception as exc:
            logger.error("Fidelity: import_trades_csv failed - %s", exc)

        return imported

    # ------------------------------------------------------------------
    # Swing-trade P&L
    # ------------------------------------------------------------------

    def get_swing_pnl(self, symbol: Optional[str] = None) -> list[dict]:
        """Calculate realised P&L for swing trades from imported trade data.

        If *symbol* is given, filter to that ticker; otherwise return all.
        """
        results: list[dict] = []
        try:
            conn = get_connection()
            query = "SELECT symbol, side, qty, price, total, trade_date FROM fidelity_trades"
            params: tuple = ()
            if symbol:
                query += " WHERE symbol = ?"
                params = (symbol.upper(),)
            query += " ORDER BY trade_date"

            rows = conn.execute(query, params).fetchall()
            conn.close()

            # Simple FIFO P&L calculation per symbol
            buys: dict[str, list] = {}
            for r in rows:
                sym = r["symbol"]
                if r["side"] == "buy":
                    buys.setdefault(sym, []).append({
                        "qty": r["qty"], "price": r["price"], "date": r["trade_date"],
                    })
                elif r["side"] == "sell" and sym in buys:
                    sell_qty = r["qty"]
                    sell_price = r["price"]
                    realised = 0.0
                    while sell_qty > 0 and buys.get(sym):
                        lot = buys[sym][0]
                        matched = min(sell_qty, lot["qty"])
                        realised += matched * (sell_price - lot["price"])
                        lot["qty"] -= matched
                        sell_qty -= matched
                        if lot["qty"] <= 0:
                            buys[sym].pop(0)

                    results.append({
                        "symbol": sym,
                        "sell_date": r["trade_date"],
                        "sell_price": sell_price,
                        "qty": r["qty"],
                        "realised_pnl": round(realised, 2),
                    })
        except Exception as exc:
            logger.error("Fidelity: get_swing_pnl failed - %s", exc)
        return results

    def mark_alert_executed(self, alert_id: int) -> bool:
        """Mark an alert as manually executed by the user."""
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE fidelity_alerts SET executed = 1, executed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), alert_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.error("Fidelity: mark_alert_executed failed - %s", exc)
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_alert(self, symbol: str, action: str, reason: str = "",
                      target_price: float = 0, stop_price: float = 0) -> dict:
        """Insert a new alert row and return it."""
        try:
            conn = get_connection()
            now = datetime.now().isoformat()
            cur = conn.execute(
                """INSERT INTO fidelity_alerts
                   (symbol, action, reason, target_price, stop_price, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (symbol, action, reason, target_price, stop_price, now),
            )
            conn.commit()
            alert_id = cur.lastrowid
            conn.close()
            logger.info("Fidelity: alert created - %s %s (id=%s)", action, symbol, alert_id)
            return {"id": alert_id, "symbol": symbol, "action": action}
        except Exception as exc:
            logger.error("Fidelity: _create_alert failed - %s", exc)
            return {"id": 0, "symbol": symbol, "action": action}

    @staticmethod
    def _clean_csv_value(val: str) -> str:
        """Strip whitespace and surrounding quotes from a CSV cell."""
        if not val:
            return ""
        return val.strip().strip('"').strip()

    @staticmethod
    def _parse_number(val: str) -> float:
        """Parse a number from a CSV cell, handling $, commas, parens."""
        if not val:
            return 0.0
        cleaned = val.strip().replace("$", "").replace(",", "").replace('"', '')
        negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            negative = True
            cleaned = cleaned[1:-1]
        if cleaned.startswith("-"):
            negative = True
            cleaned = cleaned[1:]
        try:
            num = float(cleaned)
            return -num if negative else num
        except ValueError:
            return 0.0
