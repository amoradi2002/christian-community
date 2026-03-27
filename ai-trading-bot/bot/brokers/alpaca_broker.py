"""
Alpaca broker adapter - wraps the existing bot/engine/trader.py into
the BaseBroker interface.

This module delegates all operations to the functions already defined in
trader.py so that the existing Alpaca paper/live trading functionality
is accessible through the unified BrokerManager.

Environment variables (same as trader.py):
    ALPACA_API_KEY     - Alpaca API key
    ALPACA_SECRET_KEY  - Alpaca secret key
    ALPACA_PAPER       - "true" (default) for paper trading, "false" for live
"""

import logging
import os
from typing import Optional

from bot.brokers.base import BaseBroker
from bot.engine import trader as alpaca_trader

logger = logging.getLogger(__name__)


class AlpacaBroker(BaseBroker):
    """BaseBroker adapter that delegates to bot.engine.trader functions."""

    def __init__(self):
        self._connected = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Verify Alpaca credentials by fetching the account."""
        try:
            info = alpaca_trader.get_account_info()
            if "error" in info:
                logger.error("Alpaca: connection check failed - %s", info["error"])
                self._connected = False
                return False

            paper = info.get("paper", True)
            mode = "paper" if paper else "LIVE"
            logger.info("Alpaca: connected (%s mode) | equity=$%.2f",
                        mode, info.get("equity", 0))
            self._connected = True
            return True

        except Exception as exc:
            logger.error("Alpaca: connect failed - %s", exc)
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    @property
    def broker_name(self) -> str:
        return "alpaca"

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        try:
            info = alpaca_trader.get_account_info()
            if "error" in info:
                return {"error": info["error"], "broker": self.broker_name}
            info["broker"] = self.broker_name
            return info
        except Exception as exc:
            logger.error("Alpaca: get_account failed - %s", exc)
            return {"error": str(exc), "broker": self.broker_name}

    def get_positions(self) -> list[dict]:
        try:
            positions = alpaca_trader.get_positions()
            for p in positions:
                p["broker"] = self.broker_name
            return positions
        except Exception as exc:
            logger.error("Alpaca: get_positions failed - %s", exc)
            return []

    # ------------------------------------------------------------------
    # Stock Orders
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
        try:
            result = alpaca_trader.place_stock_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                time_in_force=time_in_force,
            )
            d = result.to_dict()
            d["broker"] = self.broker_name
            return d
        except Exception as exc:
            return self._fail(f"place_order error: {exc}", symbol, side, qty)

    # ------------------------------------------------------------------
    # Options Orders
    # ------------------------------------------------------------------

    def place_option_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
    ) -> dict:
        try:
            result = alpaca_trader.place_option_order(
                contract_symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
            )
            d = result.to_dict()
            d["broker"] = self.broker_name
            return d
        except Exception as exc:
            return self._fail(f"place_option_order error: {exc}", symbol, side, qty)

    def get_option_chain(self, symbol: str) -> dict:
        """Alpaca option chain retrieval.

        Alpaca's options support is limited compared to dedicated
        options brokers.  Return an empty dict if not available.
        """
        logger.info("Alpaca: option chain retrieval not natively supported via trader.py")
        return {}

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> bool:
        try:
            return alpaca_trader.cancel_order(order_id)
        except Exception as exc:
            logger.error("Alpaca: cancel_order failed - %s", exc)
            return False

    def get_orders(self, status: str = "open") -> list[dict]:
        try:
            orders = alpaca_trader.get_orders(status=status)
            for o in orders:
                o["broker"] = self.broker_name
            return orders
        except Exception as exc:
            logger.error("Alpaca: get_orders failed - %s", exc)
            return []
