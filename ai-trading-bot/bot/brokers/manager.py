"""
BrokerManager - orchestrates all broker integrations.

Responsibilities:
- Route trades to the correct broker based on trade type
- Aggregate positions and equity across all connected brokers
- Unified P&L tracking
- Configurable routing rules (from config.yaml or defaults)

Default routing:
    options     -> robinhood  (or alpaca)
    swing       -> fidelity
    day_trade   -> interactive_brokers
    paper       -> alpaca
    crypto      -> robinhood
    signal      -> (stored, not executed)

Configuration in config.yaml:
    brokers:
      routing:
        options: robinhood
        swing: fidelity
        day_trade: interactive_brokers
        paper: alpaca
        crypto: robinhood
      enabled:
        - alpaca
        - robinhood
        - fidelity
        - interactive_brokers
        - tradingview
"""

import logging
from typing import Optional

from bot.config.settings import CONFIG

logger = logging.getLogger(__name__)

# Default routing map
_DEFAULT_ROUTING = {
    "options": "robinhood",
    "swing": "fidelity",
    "day_trade": "interactive_brokers",
    "paper": "alpaca",
    "crypto": "robinhood",
    "signal": "tradingview",
}

# Lazy imports to avoid hard dependency on every library at import time
_BROKER_CLASSES = {
    "alpaca": "bot.brokers.alpaca_broker.AlpacaBroker",
    "robinhood": "bot.brokers.robinhood.RobinhoodBroker",
    "fidelity": "bot.brokers.fidelity.FidelityBroker",
    "interactive_brokers": "bot.brokers.interactive_brokers.IBBroker",
    "tradingview": "bot.brokers.tradingview.TradingViewBroker",
}


def _import_broker_class(dotted_path: str):
    """Dynamically import and return a broker class."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class BrokerManager:
    """Central manager that owns broker instances and routes trades."""

    def __init__(self):
        self._brokers: dict = {}  # name -> BaseBroker instance
        self._routing: dict = {}
        self._load_config()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """Read broker routing and enabled list from config.yaml."""
        broker_cfg = CONFIG.get("brokers", {})
        self._routing = {**_DEFAULT_ROUTING, **broker_cfg.get("routing", {})}

        enabled = broker_cfg.get("enabled", [])
        if not enabled:
            # Default: only enable alpaca (the existing broker)
            enabled = ["alpaca"]

        for name in enabled:
            if name in _BROKER_CLASSES:
                try:
                    cls = _import_broker_class(_BROKER_CLASSES[name])
                    self._brokers[name] = cls()
                    logger.info("BrokerManager: registered broker '%s'", name)
                except Exception as exc:
                    logger.error("BrokerManager: failed to instantiate '%s' - %s", name, exc)
            else:
                logger.warning("BrokerManager: unknown broker name '%s'", name)

    # ------------------------------------------------------------------
    # Broker Access
    # ------------------------------------------------------------------

    def get_broker(self, name: str):
        """Return a broker instance by name, or None if not registered."""
        broker = self._brokers.get(name)
        if broker is None:
            logger.warning("BrokerManager: broker '%s' not registered", name)
        return broker

    def list_brokers(self) -> list[str]:
        """Return names of all registered brokers."""
        return list(self._brokers.keys())

    def connect_all(self) -> dict[str, bool]:
        """Attempt to connect every registered broker.

        Returns a dict mapping broker name -> success boolean.
        """
        results: dict[str, bool] = {}
        for name, broker in self._brokers.items():
            try:
                ok = broker.connect()
                results[name] = ok
                status = "connected" if ok else "FAILED"
                logger.info("BrokerManager: %s -> %s", name, status)
            except Exception as exc:
                results[name] = False
                logger.error("BrokerManager: %s connect error - %s", name, exc)
        return results

    def connect_broker(self, name: str) -> bool:
        """Connect a single broker by name."""
        broker = self.get_broker(name)
        if broker is None:
            return False
        try:
            return broker.connect()
        except Exception as exc:
            logger.error("BrokerManager: connect_broker '%s' error - %s", name, exc)
            return False

    # ------------------------------------------------------------------
    # Trade Routing
    # ------------------------------------------------------------------

    def route_trade(self, signal: dict) -> dict:
        """Route a trade signal to the appropriate broker and execute it.

        The signal dict should contain:
            trade_type:  "options", "swing", "day_trade", "paper", "crypto"
            symbol:      ticker or OCC symbol
            qty:         number of shares / contracts
            side:        "buy" or "sell"
            order_type:  "market", "limit", "stop_limit"  (default: "market")
            limit_price: (optional)
            stop_price:  (optional)

        Returns:
            The order result dict from the target broker.
        """
        trade_type = signal.get("trade_type", "paper")
        broker_name = self._routing.get(trade_type, "alpaca")
        broker = self.get_broker(broker_name)

        if broker is None:
            msg = f"No broker registered for trade_type='{trade_type}' (mapped to '{broker_name}')"
            logger.error("BrokerManager: %s", msg)
            return {"success": False, "error": msg}

        if not broker.is_connected():
            logger.info("BrokerManager: auto-connecting '%s'", broker_name)
            if not broker.connect():
                return {"success": False, "error": f"Cannot connect to {broker_name}"}

        symbol = signal.get("symbol", "")
        qty = signal.get("qty", 0)
        side = signal.get("side", "buy")
        order_type = signal.get("order_type", "market")
        limit_price = signal.get("limit_price")
        stop_price = signal.get("stop_price")

        # Decide whether to use the options or stock order path
        if trade_type == "options":
            result = broker.place_option_order(
                symbol=symbol,
                qty=int(qty),
                side=side,
                order_type=order_type,
                limit_price=limit_price,
            )
        else:
            result = broker.place_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
            )

        result["routed_to"] = broker_name
        result["trade_type"] = trade_type
        logger.info(
            "BrokerManager: routed %s %s %s %s -> %s (success=%s)",
            trade_type, side, qty, symbol, broker_name, result.get("success"),
        )
        return result

    # ------------------------------------------------------------------
    # Aggregated Views
    # ------------------------------------------------------------------

    def get_all_positions(self) -> list[dict]:
        """Aggregate open positions across all connected brokers."""
        all_positions: list[dict] = []
        for name, broker in self._brokers.items():
            if not broker.is_connected():
                continue
            try:
                positions = broker.get_positions()
                all_positions.extend(positions)
            except Exception as exc:
                logger.error("BrokerManager: get_positions from '%s' failed - %s", name, exc)
        return all_positions

    def get_total_equity(self) -> dict:
        """Sum equity across all connected brokers.

        Returns:
            dict with per-broker equity and a grand total.
        """
        breakdown: dict[str, float] = {}
        total = 0.0

        for name, broker in self._brokers.items():
            if not broker.is_connected():
                continue
            try:
                account = broker.get_account()
                equity = float(account.get("equity", 0))
                breakdown[name] = equity
                total += equity
            except Exception as exc:
                logger.error("BrokerManager: get_account from '%s' failed - %s", name, exc)
                breakdown[name] = 0.0

        return {"total_equity": total, "breakdown": breakdown}

    def get_all_orders(self, status: str = "open") -> list[dict]:
        """Aggregate orders from all connected brokers."""
        all_orders: list[dict] = []
        for name, broker in self._brokers.items():
            if not broker.is_connected():
                continue
            try:
                orders = broker.get_orders(status=status)
                all_orders.extend(orders)
            except Exception as exc:
                logger.error("BrokerManager: get_orders from '%s' failed - %s", name, exc)
        return all_orders

    def get_unified_pnl(self) -> dict:
        """Compute a unified P&L view across all brokers.

        Returns:
            dict with total unrealised P&L and per-broker breakdown.
        """
        breakdown: dict[str, float] = {}
        total_pnl = 0.0

        for name, broker in self._brokers.items():
            if not broker.is_connected():
                continue
            try:
                positions = broker.get_positions()
                broker_pnl = sum(
                    float(p.get("unrealized_pnl", 0)) for p in positions
                )
                breakdown[name] = round(broker_pnl, 2)
                total_pnl += broker_pnl
            except Exception as exc:
                logger.error("BrokerManager: PnL calc from '%s' failed - %s", name, exc)
                breakdown[name] = 0.0

        return {"total_unrealized_pnl": round(total_pnl, 2), "breakdown": breakdown}

    def sync_positions(self) -> dict:
        """Refresh positions from all connected brokers and return a summary.

        This is the primary method the dashboard or scheduler should call
        to keep the unified position view up to date.
        """
        summary: dict = {}
        for name, broker in self._brokers.items():
            if not broker.is_connected():
                summary[name] = {"status": "disconnected", "positions": 0}
                continue
            try:
                positions = broker.get_positions()
                summary[name] = {
                    "status": "ok",
                    "positions": len(positions),
                    "total_value": sum(float(p.get("market_value", 0)) for p in positions),
                }
            except Exception as exc:
                summary[name] = {"status": f"error: {exc}", "positions": 0}
                logger.error("BrokerManager: sync_positions '%s' failed - %s", name, exc)

        logger.info("BrokerManager: positions synced - %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def cancel_order(self, broker_name: str, order_id: str) -> bool:
        """Cancel an order on a specific broker."""
        broker = self.get_broker(broker_name)
        if broker is None:
            return False
        try:
            return broker.cancel_order(order_id)
        except Exception as exc:
            logger.error("BrokerManager: cancel_order on '%s' failed - %s", broker_name, exc)
            return False

    def get_option_chain(self, symbol: str, broker_name: Optional[str] = None) -> dict:
        """Fetch option chain, preferring the specified broker or falling back."""
        preferred_order = [broker_name] if broker_name else []
        preferred_order.extend(["interactive_brokers", "robinhood", "alpaca"])

        for name in preferred_order:
            broker = self.get_broker(name)
            if broker is None or not broker.is_connected():
                continue
            try:
                chain = broker.get_option_chain(symbol)
                if chain:
                    return chain
            except Exception as exc:
                logger.warning("BrokerManager: option chain from '%s' failed - %s", name, exc)

        logger.warning("BrokerManager: no broker could provide option chain for %s", symbol)
        return {}

    def __repr__(self) -> str:
        connected = [n for n, b in self._brokers.items() if b.is_connected()]
        return f"<BrokerManager brokers={list(self._brokers.keys())} connected={connected}>"
