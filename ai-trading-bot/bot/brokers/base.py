"""
Abstract base class for all broker integrations.

Every broker (Robinhood, Fidelity, Interactive Brokers, TradingView, Alpaca)
must inherit from BaseBroker and implement all abstract methods to provide a
unified interface for the trading bot.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseBroker(ABC):
    """Abstract base class that defines the broker interface.

    All concrete broker implementations must subclass this and provide
    implementations for every abstract method.  The BrokerManager relies
    on this contract to route trades to the correct broker transparently.
    """

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Establish a connection / authenticate with the broker.

        Returns:
            True if the connection was established successfully, False otherwise.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check whether the broker connection is still alive.

        Returns:
            True if connected and ready to accept commands.
        """
        ...

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    @abstractmethod
    def get_account(self) -> dict:
        """Return account-level information.

        Expected keys (at minimum):
            cash        - available cash balance
            buying_power - total buying power
            equity      - total account equity
            positions   - number of open positions
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return a list of open positions.

        Each position dict should contain at minimum:
            symbol, qty, side, avg_entry, current_price,
            market_value, unrealized_pnl
        """
        ...

    # ------------------------------------------------------------------
    # Stock Orders
    # ------------------------------------------------------------------

    @abstractmethod
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
        """Place a stock / ETF order.

        Args:
            symbol:       Ticker symbol.
            qty:          Number of shares (fractional OK where supported).
            side:         "buy" or "sell".
            order_type:   "market", "limit", or "stop_limit".
            limit_price:  Required for limit / stop_limit orders.
            stop_price:   Required for stop_limit orders.
            time_in_force: "day", "gtc", "ioc", "fok".

        Returns:
            dict with at least: success (bool), order_id, status, error.
        """
        ...

    # ------------------------------------------------------------------
    # Options Orders
    # ------------------------------------------------------------------

    @abstractmethod
    def place_option_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
    ) -> dict:
        """Place an options order.

        Args:
            symbol:      OCC option symbol (e.g. "AAPL250321C00170000").
            qty:         Number of contracts.
            side:        "buy" or "sell".
            order_type:  "market" or "limit".
            limit_price: Recommended for options to avoid bad fills.

        Returns:
            dict with at least: success (bool), order_id, status, error.
        """
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str) -> dict:
        """Retrieve the option chain for a given underlying symbol.

        Returns:
            dict keyed by expiration date, each containing lists of
            call and put contracts with strike, bid, ask, volume,
            open_interest, and greeks where available.
        """
        ...

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Returns:
            True if the cancellation request was accepted.
        """
        ...

    @abstractmethod
    def get_orders(self, status: str = "open") -> list[dict]:
        """List orders filtered by status.

        Args:
            status: "open", "closed", or "all".

        Returns:
            list of order dicts with id, symbol, side, qty, type,
            status, filled_price, submitted_at.
        """
        ...

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker name (e.g. 'robinhood', 'alpaca')."""
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ok(self, order_id: str, symbol: str, side: str, qty: float,
            order_type: str, status: str, filled_price: float = 0.0) -> dict:
        """Build a standardised success response dict."""
        return {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "filled_price": filled_price,
            "status": status,
            "error": "",
        }

    def _fail(self, error: str, symbol: str = "", side: str = "",
              qty: float = 0) -> dict:
        """Build a standardised failure response dict."""
        logger.error("[%s] %s", self.broker_name, error)
        return {
            "success": False,
            "order_id": "",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": "",
            "filled_price": 0,
            "status": "failed",
            "error": error,
        }

    def __repr__(self) -> str:
        connected = "connected" if self.is_connected() else "disconnected"
        return f"<{self.__class__.__name__} [{connected}]>"
