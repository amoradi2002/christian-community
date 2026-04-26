"""
Interactive Brokers integration via ib_insync (TWS API).

Supports:
- Full stock and options order execution
- Day-trading features: bracket orders, OCO orders, trailing stops
- Real-time market data and P&L tracking
- Options with full Greeks
- Connection to TWS or IB Gateway

Environment variables (set in .env):
    IB_HOST      - TWS/Gateway host (default: 127.0.0.1)
    IB_PORT      - TWS/Gateway port (default: 7497 for paper, 7496 for live)
    IB_CLIENT_ID - unique client ID (default: 1)
    IB_ACCOUNT   - IB account number (optional, for multi-account setups)
"""

import logging
import os
from datetime import datetime
from typing import Optional

from bot.brokers.base import BaseBroker
from bot.db.database import get_connection

logger = logging.getLogger(__name__)


class IBBroker(BaseBroker):
    """Interactive Brokers implementation using ib_insync."""

    def __init__(self):
        self._ib = None  # ib_insync.IB instance
        self._connected = False
        self._host = os.getenv("IB_HOST", "127.0.0.1")
        self._port = int(os.getenv("IB_PORT", "7497"))
        self._client_id = int(os.getenv("IB_CLIENT_ID", "1"))
        self._account = os.getenv("IB_ACCOUNT", "")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to TWS or IB Gateway."""
        try:
            from ib_insync import IB  # type: ignore

            self._ib = IB()
            self._ib.connect(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                readonly=False,
                account=self._account or "",
            )
            self._connected = self._ib.isConnected()

            if self._connected:
                logger.info(
                    "IB: connected to %s:%s (clientId=%s, account=%s)",
                    self._host, self._port, self._client_id,
                    self._account or "default",
                )
                # Request account updates
                if self._account:
                    self._ib.reqAccountUpdates(subscribe=True, account=self._account)
            else:
                logger.error("IB: connection returned but isConnected() is False")

            return self._connected
        except Exception as exc:
            logger.error("IB: connect failed - %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Cleanly disconnect from TWS/Gateway."""
        if self._ib and self._connected:
            try:
                self._ib.disconnect()
                logger.info("IB: disconnected")
            except Exception as exc:
                logger.error("IB: disconnect error - %s", exc)
            finally:
                self._connected = False

    def is_connected(self) -> bool:
        if self._ib is None:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            self._connected = False
            return False

    @property
    def broker_name(self) -> str:
        return "interactive_brokers"

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Fetch account summary from IB."""
        try:
            self._ensure_connected()
            summary = self._ib.accountSummary(self._account) if self._account else self._ib.accountSummary()

            values: dict[str, str] = {}
            for item in summary:
                values[item.tag] = item.value

            return {
                "cash": float(values.get("TotalCashValue", 0)),
                "buying_power": float(values.get("BuyingPower", 0)),
                "equity": float(values.get("NetLiquidation", 0)),
                "positions": len(self._ib.positions()),
                "unrealized_pnl": float(values.get("UnrealizedPnL", 0)),
                "realized_pnl": float(values.get("RealizedPnL", 0)),
                "margin_used": float(values.get("InitMarginReq", 0)),
                "broker": self.broker_name,
            }
        except Exception as exc:
            logger.error("IB: get_account failed - %s", exc)
            return {"error": str(exc), "broker": self.broker_name}

    def get_positions(self) -> list[dict]:
        """Return all open positions from IB."""
        positions: list[dict] = []
        try:
            self._ensure_connected()

            for pos in self._ib.positions():
                contract = pos.contract
                symbol = contract.localSymbol or contract.symbol
                qty = float(pos.position)
                avg_cost = float(pos.avgCost)

                # For options, avgCost is per share (multiply by 100 for per-contract)
                asset_type = "stock"
                if contract.secType == "OPT":
                    asset_type = "option"
                elif contract.secType == "FUT":
                    asset_type = "future"

                # Attempt to get current price via portfolio items
                current_price = avg_cost  # fallback
                for pf_item in self._ib.portfolio():
                    if pf_item.contract.conId == contract.conId:
                        current_price = float(pf_item.marketPrice)
                        break

                market_value = qty * current_price
                if asset_type == "option":
                    market_value = qty * current_price * 100

                unrealized_pnl = 0.0
                for pf_item in self._ib.portfolio():
                    if pf_item.contract.conId == contract.conId:
                        unrealized_pnl = float(pf_item.unrealizedPNL)
                        break

                positions.append({
                    "symbol": symbol,
                    "qty": qty,
                    "side": "long" if qty > 0 else "short",
                    "avg_entry": avg_cost,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "asset_type": asset_type,
                    "sec_type": contract.secType,
                    "exchange": contract.exchange,
                    "broker": self.broker_name,
                })

        except Exception as exc:
            logger.error("IB: get_positions failed - %s", exc)
        return positions

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
        """Place a stock order via IB."""
        try:
            from ib_insync import Stock, Order, MarketOrder, LimitOrder, StopOrder  # type: ignore
            self._ensure_connected()

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            action = "BUY" if side.lower() == "buy" else "SELL"
            tif = self._map_tif(time_in_force)

            if order_type == "market":
                order = MarketOrder(action, qty)
            elif order_type == "limit" and limit_price is not None:
                order = LimitOrder(action, qty, limit_price)
            elif order_type == "stop" and stop_price is not None:
                order = StopOrder(action, qty, stop_price)
            elif order_type == "stop_limit" and limit_price is not None and stop_price is not None:
                order = Order(
                    action=action,
                    totalQuantity=qty,
                    orderType="STP LMT",
                    lmtPrice=limit_price,
                    auxPrice=stop_price,
                )
            else:
                return self._fail(f"Invalid order_type '{order_type}' or missing prices", symbol, side, qty)

            order.tif = tif
            if self._account:
                order.account = self._account

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)  # give IB time to acknowledge

            order_id = str(trade.order.orderId)
            status = trade.orderStatus.status
            filled_price = trade.orderStatus.avgFillPrice or 0.0

            self._log_trade(order_id, symbol, side, qty, order_type, filled_price, status)
            return self._ok(order_id, symbol, side, qty, order_type, status, filled_price)

        except Exception as exc:
            return self._fail(f"place_order error: {exc}", symbol, side, qty)

    # ------------------------------------------------------------------
    # Day-trading specific orders
    # ------------------------------------------------------------------

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
        take_profit: float,
        stop_loss: float,
    ) -> dict:
        """Place a bracket order (entry + take-profit + stop-loss).

        This is the bread-and-butter for day trading: one order to enter,
        with automatic profit target and stop-loss attached.
        """
        try:
            from ib_insync import Stock  # type: ignore
            self._ensure_connected()

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            action = "BUY" if side.lower() == "buy" else "SELL"
            reverse = "SELL" if side.lower() == "buy" else "BUY"

            bracket = self._ib.bracketOrder(
                action=action,
                quantity=qty,
                limitPrice=limit_price,
                takeProfitPrice=take_profit,
                stopLossPrice=stop_loss,
            )

            if self._account:
                for o in bracket:
                    o.account = self._account

            trades = []
            for o in bracket:
                trade = self._ib.placeOrder(contract, o)
                trades.append(trade)

            self._ib.sleep(1)

            parent_id = str(trades[0].order.orderId) if trades else ""
            status = trades[0].orderStatus.status if trades else "unknown"

            self._log_trade(parent_id, symbol, side, qty, "bracket", limit_price, status)
            logger.info(
                "IB: bracket order placed for %s %s %s @ %.2f "
                "(TP=%.2f, SL=%.2f)",
                side, qty, symbol, limit_price, take_profit, stop_loss,
            )

            return self._ok(parent_id, symbol, side, qty, "bracket", status, limit_price)

        except Exception as exc:
            return self._fail(f"place_bracket_order error: {exc}", symbol, side, qty)

    def place_oco_order(
        self,
        symbol: str,
        qty: float,
        take_profit_price: float,
        stop_loss_price: float,
    ) -> dict:
        """Place an OCO (One-Cancels-Other) order to close an existing position.

        Useful when you are already in a position and want both a
        take-profit and stop-loss exit.
        """
        try:
            from ib_insync import Stock, LimitOrder, StopOrder, Order  # type: ignore
            self._ensure_connected()

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            oco_group = f"oco_{symbol}_{int(datetime.now().timestamp())}"

            # Take-profit (limit sell)
            tp_order = LimitOrder("SELL", qty, take_profit_price)
            tp_order.ocaGroup = oco_group
            tp_order.ocaType = 1  # Cancel all remaining
            tp_order.tif = "GTC"
            if self._account:
                tp_order.account = self._account

            # Stop-loss
            sl_order = StopOrder("SELL", qty, stop_loss_price)
            sl_order.ocaGroup = oco_group
            sl_order.ocaType = 1
            sl_order.tif = "GTC"
            if self._account:
                sl_order.account = self._account

            tp_trade = self._ib.placeOrder(contract, tp_order)
            sl_trade = self._ib.placeOrder(contract, sl_order)
            self._ib.sleep(1)

            tp_id = str(tp_trade.order.orderId)
            sl_id = str(sl_trade.order.orderId)

            logger.info(
                "IB: OCO placed for %s %s (TP=%s @ %.2f, SL=%s @ %.2f)",
                qty, symbol, tp_id, take_profit_price, sl_id, stop_loss_price,
            )

            return self._ok(
                f"{tp_id}/{sl_id}", symbol, "sell", qty, "oco",
                "submitted", 0,
            )
        except Exception as exc:
            return self._fail(f"place_oco_order error: {exc}", symbol, "sell", qty)

    def place_trailing_stop(
        self,
        symbol: str,
        qty: float,
        trail_amount: Optional[float] = None,
        trail_percent: Optional[float] = None,
    ) -> dict:
        """Place a trailing stop order.

        Provide either trail_amount (dollar amount) or trail_percent.
        """
        try:
            from ib_insync import Stock, Order  # type: ignore
            self._ensure_connected()

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            order = Order(
                action="SELL",
                totalQuantity=qty,
                orderType="TRAIL",
                tif="GTC",
            )
            if trail_amount is not None:
                order.auxPrice = trail_amount
            elif trail_percent is not None:
                order.trailingPercent = trail_percent
            else:
                return self._fail("Must provide trail_amount or trail_percent", symbol, "sell", qty)

            if self._account:
                order.account = self._account

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)

            order_id = str(trade.order.orderId)
            status = trade.orderStatus.status

            logger.info(
                "IB: trailing stop for %s %s (amt=%s, pct=%s)",
                qty, symbol, trail_amount, trail_percent,
            )
            return self._ok(order_id, symbol, "sell", qty, "trailing_stop", status)

        except Exception as exc:
            return self._fail(f"place_trailing_stop error: {exc}", symbol, "sell", qty)

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
        """Place an options order on IB.

        *symbol* should be an OCC-style symbol or the underlying with
        additional parameters parsed out.
        """
        try:
            from ib_insync import Option, LimitOrder, MarketOrder  # type: ignore
            self._ensure_connected()

            parsed = self._parse_occ_to_ib(symbol)
            if parsed is None:
                return self._fail(f"Cannot parse option symbol: {symbol}", symbol, side, qty)

            contract = Option(**parsed)
            self._ib.qualifyContracts(contract)

            action = "BUY" if side.lower() == "buy" else "SELL"

            if order_type == "limit" and limit_price is not None:
                order = LimitOrder(action, qty, limit_price)
            elif order_type == "market":
                order = MarketOrder(action, qty)
            else:
                return self._fail("Options should use limit orders with a price", symbol, side, qty)

            if self._account:
                order.account = self._account

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)

            order_id = str(trade.order.orderId)
            status = trade.orderStatus.status
            filled_price = trade.orderStatus.avgFillPrice or 0.0

            self._log_trade(order_id, symbol, side, qty, order_type, filled_price, status)
            return self._ok(order_id, symbol, side, qty, order_type, status, filled_price)

        except Exception as exc:
            return self._fail(f"place_option_order error: {exc}", symbol, side, qty)

    def get_option_chain(self, symbol: str) -> dict:
        """Retrieve option chain with Greeks for an underlying symbol."""
        chain: dict = {}
        try:
            from ib_insync import Stock, Option  # type: ignore
            self._ensure_connected()

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            chains = self._ib.reqSecDefOptParams(
                contract.symbol, "", contract.secType, contract.conId,
            )
            if not chains:
                logger.warning("IB: no option chains found for %s", symbol)
                return {}

            # Use the SMART exchange chain
            ib_chain = None
            for c in chains:
                if c.exchange == "SMART":
                    ib_chain = c
                    break
            if ib_chain is None:
                ib_chain = chains[0]

            expirations = sorted(ib_chain.expirations)[:6]
            strikes = sorted(ib_chain.strikes)

            for exp in expirations:
                calls = []
                puts = []

                # Request a subset of strikes around current price
                try:
                    ticker = self._ib.reqMktData(contract, "", False, False)
                    self._ib.sleep(2)
                    current_price = ticker.marketPrice() or ticker.close or 0
                    self._ib.cancelMktData(contract)
                except Exception:
                    current_price = 0

                # Filter strikes near the money
                if current_price > 0:
                    near_strikes = [s for s in strikes if abs(s - current_price) / current_price < 0.15]
                else:
                    near_strikes = strikes[:20]

                for strike in near_strikes:
                    for right in ("C", "P"):
                        try:
                            opt = Option(symbol, exp, strike, right, "SMART")
                            self._ib.qualifyContracts(opt)
                            ticker = self._ib.reqMktData(opt, "106", False, False)
                            self._ib.sleep(0.5)

                            entry = {
                                "strike": strike,
                                "bid": ticker.bid or 0,
                                "ask": ticker.ask or 0,
                                "last": ticker.last or 0,
                                "volume": ticker.volume or 0,
                                "open_interest": 0,
                                "implied_volatility": getattr(ticker, "impliedVolatility", 0) or 0,
                                "delta": getattr(ticker, "delta", 0) or 0,
                                "gamma": getattr(ticker, "gamma", 0) or 0,
                                "theta": getattr(ticker, "theta", 0) or 0,
                                "vega": getattr(ticker, "vega", 0) or 0,
                            }

                            self._ib.cancelMktData(opt)

                            if right == "C":
                                calls.append(entry)
                            else:
                                puts.append(entry)
                        except Exception as exc:
                            logger.debug("IB: option data error %s %s %s %s: %s",
                                         symbol, exp, strike, right, exc)

                chain[exp] = {"calls": calls, "puts": puts}

        except Exception as exc:
            logger.error("IB: get_option_chain failed for %s - %s", symbol, exc)
        return chain

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by order ID."""
        try:
            self._ensure_connected()

            for trade in self._ib.openTrades():
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    self._ib.sleep(1)
                    logger.info("IB: cancelled order %s", order_id)
                    return True

            logger.warning("IB: order %s not found in open trades", order_id)
            return False
        except Exception as exc:
            logger.error("IB: cancel_order %s failed - %s", order_id, exc)
            return False

    def get_orders(self, status: str = "open") -> list[dict]:
        """Return orders from IB."""
        orders: list[dict] = []
        try:
            self._ensure_connected()

            if status == "open":
                trade_list = self._ib.openTrades()
            else:
                trade_list = self._ib.trades()

            for trade in trade_list:
                o = trade.order
                s = trade.orderStatus
                c = trade.contract

                order_status = s.status
                if status == "closed" and order_status in ("Submitted", "PreSubmitted"):
                    continue

                orders.append({
                    "id": str(o.orderId),
                    "symbol": c.localSymbol or c.symbol,
                    "side": o.action.lower(),
                    "qty": float(o.totalQuantity),
                    "type": o.orderType,
                    "status": order_status,
                    "filled_price": s.avgFillPrice or 0,
                    "submitted_at": "",
                    "filled_at": "",
                    "broker": self.broker_name,
                })

        except Exception as exc:
            logger.error("IB: get_orders failed - %s", exc)
        return orders

    # ------------------------------------------------------------------
    # Real-time P&L
    # ------------------------------------------------------------------

    def get_realtime_pnl(self) -> dict:
        """Get real-time P&L from IB account."""
        try:
            self._ensure_connected()
            pnl = self._ib.reqPnL(self._account or "")
            self._ib.sleep(1)

            result = {
                "daily_pnl": pnl.dailyPnL or 0,
                "unrealized_pnl": pnl.unrealizedPnL or 0,
                "realized_pnl": pnl.realizedPnL or 0,
                "broker": self.broker_name,
            }
            self._ib.cancelPnL(pnl)
            return result
        except Exception as exc:
            logger.error("IB: get_realtime_pnl failed - %s", exc)
            return {"daily_pnl": 0, "unrealized_pnl": 0, "realized_pnl": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Reconnect if the connection was dropped."""
        if not self.is_connected():
            logger.warning("IB: connection lost, attempting reconnect")
            self.connect()
            if not self.is_connected():
                raise ConnectionError("IB: unable to reconnect to TWS/Gateway")

    @staticmethod
    def _map_tif(tif: str) -> str:
        """Map generic TIF strings to IB TIF codes."""
        mapping = {
            "day": "DAY",
            "gtc": "GTC",
            "ioc": "IOC",
            "fok": "FOK",
            "gfd": "DAY",
        }
        return mapping.get(tif.lower(), "DAY")

    @staticmethod
    def _parse_occ_to_ib(occ: str) -> Optional[dict]:
        """Convert an OCC option symbol to ib_insync Option kwargs.

        Example: AAPL250321C00170000
            -> symbol="AAPL", lastTradeDateOrContractMonth="20250321",
               strike=170.0, right="C", exchange="SMART"
        """
        try:
            type_idx = None
            for i in range(len(occ) - 1, 5, -1):
                if occ[i] in ("C", "P"):
                    if occ[i + 1:].isdigit() and occ[i - 6:i].isdigit():
                        type_idx = i
                        break
            if type_idx is None:
                return None

            underlying = occ[:type_idx - 6].rstrip()
            date_str = occ[type_idx - 6:type_idx]
            right = occ[type_idx]
            strike = int(occ[type_idx + 1:]) / 1000

            return {
                "symbol": underlying,
                "lastTradeDateOrContractMonth": f"20{date_str}",
                "strike": strike,
                "right": right,
                "exchange": "SMART",
            }
        except Exception:
            return None

    def _log_trade(self, order_id: str, symbol: str, side: str,
                   qty: float, order_type: str, filled_price: float,
                   status: str) -> None:
        """Persist trade to SQLite."""
        try:
            conn = get_connection()
            conn.execute(
                """INSERT INTO trades
                   (order_id, symbol, side, qty, order_type, filled_price, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, symbol, side, qty, order_type, filled_price,
                 status, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.debug("IB: trade logging failed - %s", exc)
