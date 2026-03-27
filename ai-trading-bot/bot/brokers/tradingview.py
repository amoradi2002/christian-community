"""
TradingView webhook integration.

Receives alerts from TradingView via HTTP POST webhooks, parses them,
stores them in SQLite, and routes them to the bot's signal system.

Features:
- Flask-based webhook endpoint (POST /webhook/tradingview)
- Parses TradingView alert JSON and plaintext formats
- Supports TradingView {{variable}} template syntax
- Generates Pine Script alert templates
- Stores all received alerts in SQLite for audit

Environment variables (optional):
    TV_WEBHOOK_SECRET - shared secret to authenticate incoming webhooks
    TV_WEBHOOK_PORT   - port for the webhook server (default: 5001)
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from threading import Thread
from typing import Optional

from bot.brokers.base import BaseBroker
from bot.db.database import get_connection

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# SQL
# ------------------------------------------------------------------
_CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS tradingview_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    action          TEXT NOT NULL DEFAULT '',
    price           REAL DEFAULT 0,
    volume          REAL DEFAULT 0,
    timeframe       TEXT DEFAULT '',
    strategy        TEXT DEFAULT '',
    message         TEXT DEFAULT '',
    raw_payload     TEXT DEFAULT '',
    source_ip       TEXT DEFAULT '',
    received_at     TEXT NOT NULL,
    processed       INTEGER DEFAULT 0,
    routed_to       TEXT DEFAULT ''
);
"""


class TradingViewBroker(BaseBroker):
    """TradingView webhook-based integration.

    This is not a traditional broker -- it receives signals from
    TradingView alerts and feeds them into the bot's signal pipeline.
    Order execution is delegated to other brokers via the BrokerManager.
    """

    def __init__(self):
        self._connected = False
        self._webhook_secret = os.getenv("TV_WEBHOOK_SECRET", "")
        self._webhook_port = int(os.getenv("TV_WEBHOOK_PORT", "5001"))
        self._app = None
        self._server_thread: Optional[Thread] = None
        self._alert_callbacks: list = []
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create the alerts table if it does not exist."""
        try:
            conn = get_connection()
            conn.executescript(_CREATE_ALERTS_TABLE)
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("TradingView: table creation failed - %s", exc)

    # ------------------------------------------------------------------
    # Connection (starts webhook server)
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Start the Flask webhook server in a background thread."""
        try:
            from flask import Flask, request, jsonify  # type: ignore

            self._app = Flask("tradingview_webhook")

            # Suppress Flask's default request logging in production
            wlog = logging.getLogger("werkzeug")
            wlog.setLevel(logging.WARNING)

            @self._app.route("/webhook/tradingview", methods=["POST"])
            def handle_webhook():
                # Authenticate
                if self._webhook_secret:
                    token = request.headers.get("X-Webhook-Secret", "")
                    if token != self._webhook_secret:
                        body_bytes = request.get_data()
                        sig = request.headers.get("X-Signature", "")
                        expected = hashlib.sha256(
                            (self._webhook_secret + body_bytes.decode("utf-8", errors="replace")).encode()
                        ).hexdigest()
                        if sig != expected and token != self._webhook_secret:
                            logger.warning("TradingView: webhook auth failed from %s", request.remote_addr)
                            return jsonify({"error": "unauthorized"}), 401

                alert = self._parse_alert(request)
                self._store_alert(alert, request.remote_addr)
                self._dispatch_alert(alert)

                return jsonify({"status": "ok", "alert_id": alert.get("id", 0)}), 200

            @self._app.route("/webhook/tradingview", methods=["GET"])
            def health_check():
                return jsonify({"status": "running", "broker": "tradingview"}), 200

            self._server_thread = Thread(
                target=lambda: self._app.run(
                    host="0.0.0.0",
                    port=self._webhook_port,
                    debug=False,
                    use_reloader=False,
                ),
                daemon=True,
                name="tradingview-webhook",
            )
            self._server_thread.start()
            self._connected = True
            logger.info("TradingView: webhook server started on port %s", self._webhook_port)
            return True

        except Exception as exc:
            logger.error("TradingView: connect (webhook start) failed - %s", exc)
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected and (
            self._server_thread is not None and self._server_thread.is_alive()
        )

    @property
    def broker_name(self) -> str:
        return "tradingview"

    # ------------------------------------------------------------------
    # Alert Callbacks
    # ------------------------------------------------------------------

    def on_alert(self, callback) -> None:
        """Register a callback invoked for every incoming alert.

        The callback receives a single dict argument (the parsed alert).
        """
        self._alert_callbacks.append(callback)

    def _dispatch_alert(self, alert: dict) -> None:
        """Invoke all registered alert callbacks."""
        for cb in self._alert_callbacks:
            try:
                cb(alert)
            except Exception as exc:
                logger.error("TradingView: alert callback error - %s", exc)

    # ------------------------------------------------------------------
    # Alert Parsing
    # ------------------------------------------------------------------

    def _parse_alert(self, request) -> dict:
        """Parse an incoming webhook request into a normalised alert dict.

        Supports:
        - JSON body: {"ticker": "AAPL", "action": "buy", "price": 170, ...}
        - Plaintext body: "AAPL buy 170"
        - TradingView {{variable}} syntax is expected to be resolved
          by TradingView before the alert reaches us.
        """
        alert: dict = {
            "ticker": "",
            "action": "",
            "price": 0.0,
            "volume": 0.0,
            "timeframe": "",
            "strategy": "",
            "message": "",
        }

        content_type = request.content_type or ""

        if "json" in content_type:
            try:
                data = request.get_json(force=True, silent=True) or {}
                alert["ticker"] = str(data.get("ticker", data.get("symbol", ""))).upper()
                alert["action"] = str(data.get("action", data.get("side", data.get("order", "")))).lower()
                alert["price"] = float(data.get("price", data.get("close", 0)))
                alert["volume"] = float(data.get("volume", 0))
                alert["timeframe"] = str(data.get("timeframe", data.get("interval", "")))
                alert["strategy"] = str(data.get("strategy", data.get("strategy_name", "")))
                alert["message"] = str(data.get("message", data.get("comment", "")))
                alert["raw"] = json.dumps(data)
            except Exception as exc:
                logger.warning("TradingView: JSON parse error - %s", exc)
                alert["raw"] = request.get_data(as_text=True)
        else:
            # Plaintext: try "TICKER ACTION PRICE" format
            text = request.get_data(as_text=True).strip()
            alert["raw"] = text
            alert["message"] = text
            parts = text.split()
            if len(parts) >= 1:
                alert["ticker"] = parts[0].upper()
            if len(parts) >= 2:
                alert["action"] = parts[1].lower()
            if len(parts) >= 3:
                try:
                    alert["price"] = float(parts[2])
                except ValueError:
                    pass

        return alert

    # ------------------------------------------------------------------
    # Alert Storage
    # ------------------------------------------------------------------

    def _store_alert(self, alert: dict, source_ip: str = "") -> None:
        """Persist the alert to SQLite."""
        try:
            conn = get_connection()
            now = datetime.now().isoformat()
            cur = conn.execute(
                """INSERT INTO tradingview_alerts
                   (ticker, action, price, volume, timeframe, strategy,
                    message, raw_payload, source_ip, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.get("ticker", ""),
                    alert.get("action", ""),
                    alert.get("price", 0),
                    alert.get("volume", 0),
                    alert.get("timeframe", ""),
                    alert.get("strategy", ""),
                    alert.get("message", ""),
                    alert.get("raw", ""),
                    source_ip,
                    now,
                ),
            )
            conn.commit()
            alert["id"] = cur.lastrowid
            conn.close()
            logger.info(
                "TradingView: stored alert #%s - %s %s @ %s",
                alert["id"], alert["action"], alert["ticker"], alert["price"],
            )
        except Exception as exc:
            logger.error("TradingView: _store_alert failed - %s", exc)

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Return the most recent stored alerts."""
        alerts: list[dict] = []
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM tradingview_alerts ORDER BY received_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            for r in rows:
                alerts.append(dict(r))
        except Exception as exc:
            logger.error("TradingView: get_recent_alerts failed - %s", exc)
        return alerts

    def mark_alert_processed(self, alert_id: int, routed_to: str = "") -> bool:
        """Mark an alert as processed by the signal system."""
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE tradingview_alerts SET processed = 1, routed_to = ? WHERE id = ?",
                (routed_to, alert_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.error("TradingView: mark_alert_processed failed - %s", exc)
            return False

    # ------------------------------------------------------------------
    # Account / Position stubs (TradingView is signal-only)
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        return {
            "cash": 0, "buying_power": 0, "equity": 0, "positions": 0,
            "broker": self.broker_name,
            "note": "TradingView is signal-only; no account data.",
        }

    def get_positions(self) -> list[dict]:
        return []

    def place_order(self, symbol, qty, side, order_type="market",
                    limit_price=None, stop_price=None, time_in_force="day") -> dict:
        """TradingView cannot execute orders directly."""
        return self._fail(
            "TradingView is signal-only. Route this order to a real broker.",
            symbol, side, qty,
        )

    def place_option_order(self, symbol, qty, side, order_type="limit",
                           limit_price=None) -> dict:
        return self._fail(
            "TradingView is signal-only. Route this order to a real broker.",
            symbol, side, qty,
        )

    def get_option_chain(self, symbol: str) -> dict:
        return {}

    def cancel_order(self, order_id: str) -> bool:
        logger.info("TradingView: cancel_order is a no-op (signal-only)")
        return False

    def get_orders(self, status: str = "open") -> list[dict]:
        """Return recent alerts as pseudo-orders."""
        alerts = self.get_recent_alerts(limit=100)
        orders: list[dict] = []
        for a in alerts:
            if status == "open" and a.get("processed"):
                continue
            if status == "closed" and not a.get("processed"):
                continue
            orders.append({
                "id": f"tv-alert-{a.get('id', 0)}",
                "symbol": a.get("ticker", ""),
                "side": a.get("action", ""),
                "qty": 0,
                "type": "alert",
                "status": "processed" if a.get("processed") else "pending",
                "filled_price": a.get("price", 0),
                "submitted_at": a.get("received_at", ""),
                "filled_at": "",
                "broker": self.broker_name,
            })
        return orders

    # ------------------------------------------------------------------
    # Pine Script Templates
    # ------------------------------------------------------------------

    @staticmethod
    def generate_pine_alert_template(strategy_name: str = "AI Bot Signal") -> str:
        """Generate a Pine Script alert message template.

        Use this in TradingView's alert dialog as the "Message" field.
        The {{variables}} are replaced by TradingView at alert-fire time.
        """
        template = json.dumps({
            "ticker": "{{ticker}}",
            "action": "{{strategy.order.action}}",
            "price": "{{close}}",
            "volume": "{{volume}}",
            "timeframe": "{{interval}}",
            "strategy": strategy_name,
            "message": "{{strategy.order.comment}}",
            "time": "{{time}}",
            "exchange": "{{exchange}}",
        }, indent=2)

        return (
            f"// --- TradingView Alert Message Template ---\n"
            f"// Copy the JSON below into TradingView's alert 'Message' field.\n"
            f"// Make sure webhook URL points to: http://YOUR_SERVER:{os.getenv('TV_WEBHOOK_PORT', '5001')}/webhook/tradingview\n"
            f"//\n"
            f"{template}\n"
        )

    @staticmethod
    def generate_pine_script_example() -> str:
        """Return a minimal Pine Script v5 strategy that fires webhook alerts."""
        return '''
//@version=5
strategy("AI Bot Webhook Strategy", overlay=true)

// Simple example: EMA crossover
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)

if ta.crossover(fast, slow)
    strategy.entry("Long", strategy.long, comment="EMA crossover BUY")

if ta.crossunder(fast, slow)
    strategy.close("Long", comment="EMA crossunder SELL")

plot(fast, color=color.green, title="Fast EMA")
plot(slow, color=color.red, title="Slow EMA")

// To use:
// 1. Add this strategy to your chart
// 2. Create an alert on this strategy
// 3. Set "Webhook URL" to http://YOUR_SERVER:5001/webhook/tradingview
// 4. In the alert Message, paste the JSON template from
//    TradingViewBroker.generate_pine_alert_template()
'''
