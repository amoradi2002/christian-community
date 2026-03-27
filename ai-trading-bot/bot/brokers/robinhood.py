"""
Robinhood broker integration via the robin_stocks library.

Supports:
- Stock and crypto trading
- Full options support (buy/sell calls/puts, spreads, option chain with Greeks)
- Position tracking and order history
- MFA authentication

Environment variables (set in .env):
    ROBINHOOD_USERNAME  - Robinhood account email
    ROBINHOOD_PASSWORD  - Robinhood account password
    ROBINHOOD_MFA_CODE  - TOTP secret for MFA (optional; omit for SMS-based MFA)
"""

import logging
import os
from datetime import datetime
from typing import Optional

from bot.brokers.base import BaseBroker
from bot.db.database import get_connection

logger = logging.getLogger(__name__)


class RobinhoodBroker(BaseBroker):
    """Broker implementation for Robinhood using robin_stocks."""

    def __init__(self):
        self._connected = False
        self._login_response = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Authenticate with Robinhood.

        Uses ROBINHOOD_USERNAME, ROBINHOOD_PASSWORD from .env.
        If ROBINHOOD_MFA_CODE is set it is treated as a TOTP secret and
        used to generate the current one-time code automatically.
        """
        try:
            import robin_stocks.robinhood as rh  # type: ignore

            username = os.getenv("ROBINHOOD_USERNAME", "")
            password = os.getenv("ROBINHOOD_PASSWORD", "")
            mfa_secret = os.getenv("ROBINHOOD_MFA_CODE", "")

            if not username or not password:
                logger.error("ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set in .env")
                return False

            login_kwargs: dict = {
                "username": username,
                "password": password,
                "expiresIn": 86400,
                "store_session": True,
            }

            # If an MFA TOTP secret is provided, generate the code automatically
            if mfa_secret:
                try:
                    import pyotp  # type: ignore
                    totp = pyotp.TOTP(mfa_secret)
                    login_kwargs["mfa_code"] = totp.now()
                except ImportError:
                    logger.warning("pyotp not installed; falling back to SMS MFA prompt")

            self._login_response = rh.login(**login_kwargs)
            self._connected = self._login_response is not None
            if self._connected:
                logger.info("Robinhood: authenticated as %s", username)
            else:
                logger.error("Robinhood: login returned None")
            return self._connected

        except Exception as exc:
            logger.error("Robinhood: login failed - %s", exc)
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    @property
    def broker_name(self) -> str:
        return "robinhood"

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Fetch account summary from Robinhood."""
        try:
            import robin_stocks.robinhood as rh

            profile = rh.profiles.load_account_profile()
            portfolio = rh.profiles.load_portfolio_profile()

            return {
                "cash": float(profile.get("cash", 0)),
                "buying_power": float(profile.get("buying_power", 0)),
                "equity": float(portfolio.get("equity", 0)),
                "extended_hours_equity": float(portfolio.get("extended_hours_equity", 0) or 0),
                "positions": len(rh.account.get_open_stock_positions()),
                "broker": self.broker_name,
            }
        except Exception as exc:
            logger.error("Robinhood: get_account failed - %s", exc)
            return {"error": str(exc), "broker": self.broker_name}

    def get_positions(self) -> list[dict]:
        """Return all open stock positions from Robinhood."""
        positions: list[dict] = []
        try:
            import robin_stocks.robinhood as rh

            stock_positions = rh.account.get_open_stock_positions()
            for pos in stock_positions:
                instrument_url = pos.get("instrument", "")
                instrument_data = rh.stocks.get_instrument_by_url(instrument_url) if instrument_url else {}
                symbol = instrument_data.get("symbol", "UNKNOWN")
                qty = float(pos.get("quantity", 0))
                avg_buy = float(pos.get("average_buy_price", 0))

                # Fetch current quote
                try:
                    quote = rh.stocks.get_latest_price(symbol)
                    current_price = float(quote[0]) if quote and quote[0] else avg_buy
                except Exception:
                    current_price = avg_buy

                market_value = qty * current_price
                unrealized_pnl = (current_price - avg_buy) * qty

                positions.append({
                    "symbol": symbol,
                    "qty": qty,
                    "side": "long",
                    "avg_entry": avg_buy,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "broker": self.broker_name,
                })

            # Also include option positions
            option_positions = self._get_option_positions()
            positions.extend(option_positions)

        except Exception as exc:
            logger.error("Robinhood: get_positions failed - %s", exc)
        return positions

    def _get_option_positions(self) -> list[dict]:
        """Fetch open option positions."""
        results: list[dict] = []
        try:
            import robin_stocks.robinhood as rh

            option_positions = rh.options.get_open_option_positions()
            for pos in option_positions:
                chain_symbol = pos.get("chain_symbol", "UNKNOWN")
                qty = float(pos.get("quantity", 0))
                avg_price = float(pos.get("average_price", 0)) / 100  # per contract
                option_type = pos.get("type", "unknown")
                direction = pos.get("direction", "debit")

                results.append({
                    "symbol": chain_symbol,
                    "qty": qty,
                    "side": "long" if direction == "debit" else "short",
                    "avg_entry": avg_price,
                    "current_price": avg_price,  # real-time price fetched separately
                    "market_value": avg_price * qty * 100,
                    "unrealized_pnl": 0,
                    "option_type": option_type,
                    "broker": self.broker_name,
                    "asset_class": "option",
                })
        except Exception as exc:
            logger.error("Robinhood: _get_option_positions failed - %s", exc)
        return results

    def get_crypto_positions(self) -> list[dict]:
        """Fetch open crypto positions on Robinhood."""
        results: list[dict] = []
        try:
            import robin_stocks.robinhood as rh

            crypto_positions = rh.crypto.get_crypto_positions()
            for pos in crypto_positions:
                currency = pos.get("currency", {})
                symbol = currency.get("code", "UNKNOWN")
                qty = float(pos.get("quantity_available", 0))
                cost_basis = float(pos.get("cost_bases", [{}])[0].get("direct_cost_basis", 0)) if pos.get("cost_bases") else 0

                if qty <= 0:
                    continue

                avg_entry = cost_basis / qty if qty > 0 else 0

                results.append({
                    "symbol": symbol,
                    "qty": qty,
                    "side": "long",
                    "avg_entry": avg_entry,
                    "current_price": avg_entry,
                    "market_value": cost_basis,
                    "unrealized_pnl": 0,
                    "broker": self.broker_name,
                    "asset_class": "crypto",
                })
        except Exception as exc:
            logger.error("Robinhood: get_crypto_positions failed - %s", exc)
        return results

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
        time_in_force: str = "gfd",
    ) -> dict:
        """Place a stock order on Robinhood."""
        try:
            import robin_stocks.robinhood as rh

            order_fn = rh.orders.order_buy_market if side.lower() == "buy" else rh.orders.order_sell_market

            if order_type == "market":
                if side.lower() == "buy":
                    result = rh.orders.order_buy_market(symbol, qty, timeInForce=time_in_force)
                else:
                    result = rh.orders.order_sell_market(symbol, qty, timeInForce=time_in_force)
            elif order_type == "limit" and limit_price is not None:
                if side.lower() == "buy":
                    result = rh.orders.order_buy_limit(symbol, qty, limit_price, timeInForce=time_in_force)
                else:
                    result = rh.orders.order_sell_limit(symbol, qty, limit_price, timeInForce=time_in_force)
            elif order_type == "stop_limit" and limit_price is not None and stop_price is not None:
                if side.lower() == "buy":
                    result = rh.orders.order_buy_stop_limit(symbol, qty, limit_price, stop_price, timeInForce=time_in_force)
                else:
                    result = rh.orders.order_sell_stop_limit(symbol, qty, limit_price, stop_price, timeInForce=time_in_force)
            else:
                return self._fail(f"Invalid order_type '{order_type}' or missing prices", symbol, side, qty)

            if result and "id" in result:
                order_id = result["id"]
                status = result.get("state", "queued")
                filled_price = float(result.get("average_price", 0) or 0)
                self._log_trade(order_id, symbol, side, qty, order_type, filled_price, status)
                return self._ok(order_id, symbol, side, qty, order_type, status, filled_price)

            error_msg = result.get("detail", str(result)) if isinstance(result, dict) else str(result)
            return self._fail(f"Order rejected: {error_msg}", symbol, side, qty)

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
        """Place an options order on Robinhood.

        Args:
            symbol: This can be the underlying ticker; additional params
                    (expiration, strike, option_type) should be packed
                    into kwargs or pre-resolved to an option URL.
            qty:    Number of contracts.
            side:   "buy" or "sell".
        """
        try:
            import robin_stocks.robinhood as rh

            # For Robinhood, options are traded by specifying the underlying
            # plus expiration / strike / type.  If `symbol` is an OCC symbol
            # we parse it; otherwise treat as underlying needing more info.
            parsed = self._parse_occ_symbol(symbol)
            if parsed is None:
                return self._fail(
                    f"Cannot parse OCC option symbol: {symbol}. "
                    "Expected format like AAPL250321C00170000",
                    symbol, side, qty,
                )

            underlying, exp_date, opt_type, strike = parsed

            if side.lower() == "buy":
                result = rh.orders.order_buy_option_limit(
                    positionEffect="open",
                    creditOrDebit="debit",
                    price=limit_price or 0.01,
                    symbol=underlying,
                    quantity=qty,
                    expirationDate=exp_date,
                    strike=strike,
                    optionType=opt_type,
                    timeInForce="gfd",
                )
            else:
                result = rh.orders.order_sell_option_limit(
                    positionEffect="close",
                    creditOrDebit="credit",
                    price=limit_price or 0.01,
                    symbol=underlying,
                    quantity=qty,
                    expirationDate=exp_date,
                    strike=strike,
                    optionType=opt_type,
                    timeInForce="gfd",
                )

            if result and "id" in result:
                order_id = result["id"]
                status = result.get("state", "queued")
                filled_price = float(result.get("average_price", 0) or 0)
                self._log_trade(order_id, symbol, side, qty, order_type, filled_price, status)
                return self._ok(order_id, symbol, side, qty, order_type, status, filled_price)

            error_msg = result.get("detail", str(result)) if isinstance(result, dict) else str(result)
            return self._fail(f"Option order rejected: {error_msg}", symbol, side, qty)

        except Exception as exc:
            return self._fail(f"place_option_order error: {exc}", symbol, side, qty)

    def place_option_spread(
        self,
        symbol: str,
        qty: int,
        spread_type: str,
        buy_strike: float,
        sell_strike: float,
        expiration: str,
        option_type: str = "call",
        limit_price: Optional[float] = None,
    ) -> dict:
        """Place an option spread (vertical, etc.) on Robinhood.

        Args:
            spread_type: "debit" or "credit".
        """
        try:
            import robin_stocks.robinhood as rh

            price = limit_price or 0.01
            credit_or_debit = "debit" if spread_type == "debit" else "credit"

            result = rh.orders.order_option_spread(
                direction=credit_or_debit,
                price=price,
                symbol=symbol,
                quantity=qty,
                spread={
                    "expirationDate": expiration,
                    "strike": [buy_strike, sell_strike],
                    "optionType": option_type,
                },
                timeInForce="gfd",
            )

            if result and "id" in result:
                order_id = result["id"]
                status = result.get("state", "queued")
                desc = f"{symbol} {option_type} spread {buy_strike}/{sell_strike}"
                self._log_trade(order_id, desc, "spread", qty, spread_type, price, status)
                return self._ok(order_id, desc, "spread", qty, spread_type, status, price)

            error_msg = result.get("detail", str(result)) if isinstance(result, dict) else str(result)
            return self._fail(f"Spread order rejected: {error_msg}", symbol, "spread", qty)

        except Exception as exc:
            return self._fail(f"place_option_spread error: {exc}", symbol, "spread", qty)

    def get_option_chain(self, symbol: str) -> dict:
        """Return the full option chain with Greeks for an underlying symbol."""
        chain: dict = {}
        try:
            import robin_stocks.robinhood as rh

            chain_info = rh.options.get_chains(symbol)
            if not chain_info or "id" not in chain_info:
                logger.warning("Robinhood: no option chain found for %s", symbol)
                return {}

            expiration_dates = chain_info.get("expiration_dates", [])

            for exp_date in expiration_dates[:6]:  # limit to nearest 6 expirations
                calls = []
                puts = []

                try:
                    option_data = rh.options.find_options_by_expiration(
                        symbol, expirationDate=exp_date, optionType="call"
                    )
                    for opt in (option_data or []):
                        calls.append(self._format_option_contract(opt))
                except Exception as exc:
                    logger.warning("Robinhood: error fetching calls for %s %s: %s", symbol, exp_date, exc)

                try:
                    option_data = rh.options.find_options_by_expiration(
                        symbol, expirationDate=exp_date, optionType="put"
                    )
                    for opt in (option_data or []):
                        puts.append(self._format_option_contract(opt))
                except Exception as exc:
                    logger.warning("Robinhood: error fetching puts for %s %s: %s", symbol, exp_date, exc)

                chain[exp_date] = {"calls": calls, "puts": puts}

        except Exception as exc:
            logger.error("Robinhood: get_option_chain failed for %s - %s", symbol, exc)
        return chain

    # ------------------------------------------------------------------
    # Crypto Orders
    # ------------------------------------------------------------------

    def place_crypto_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> dict:
        """Place a crypto order on Robinhood."""
        try:
            import robin_stocks.robinhood as rh

            if order_type == "market":
                if side.lower() == "buy":
                    result = rh.orders.order_buy_crypto_by_quantity(symbol, qty)
                else:
                    result = rh.orders.order_sell_crypto_by_quantity(symbol, qty)
            elif order_type == "limit" and limit_price is not None:
                if side.lower() == "buy":
                    result = rh.orders.order_buy_crypto_limit(symbol, qty, limit_price)
                else:
                    result = rh.orders.order_sell_crypto_limit(symbol, qty, limit_price)
            else:
                return self._fail(f"Invalid crypto order_type '{order_type}'", symbol, side, qty)

            if result and "id" in result:
                order_id = result["id"]
                status = result.get("state", "queued")
                filled_price = float(result.get("average_price", 0) or 0)
                self._log_trade(order_id, symbol, side, qty, order_type, filled_price, status)
                return self._ok(order_id, symbol, side, qty, order_type, status, filled_price)

            error_msg = result.get("detail", str(result)) if isinstance(result, dict) else str(result)
            return self._fail(f"Crypto order rejected: {error_msg}", symbol, side, qty)

        except Exception as exc:
            return self._fail(f"place_crypto_order error: {exc}", symbol, side, qty)

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> bool:
        try:
            import robin_stocks.robinhood as rh
            result = rh.orders.cancel_stock_order(order_id)
            if result and result.get("id"):
                logger.info("Robinhood: cancelled order %s", order_id)
                return True
            # Try cancelling as option order
            result = rh.orders.cancel_option_order(order_id)
            if result:
                logger.info("Robinhood: cancelled option order %s", order_id)
                return True
            return False
        except Exception as exc:
            logger.error("Robinhood: cancel_order %s failed - %s", order_id, exc)
            return False

    def get_orders(self, status: str = "open") -> list[dict]:
        """Fetch recent orders from Robinhood."""
        orders: list[dict] = []
        try:
            import robin_stocks.robinhood as rh

            if status == "open":
                raw_orders = rh.orders.get_all_open_stock_orders()
            else:
                raw_orders = rh.orders.get_all_stock_orders()

            for o in (raw_orders or []):
                state = o.get("state", "unknown")
                if status == "closed" and state in ("queued", "confirmed", "partially_filled"):
                    continue

                orders.append({
                    "id": o.get("id", ""),
                    "symbol": self._resolve_instrument_symbol(o.get("instrument", "")),
                    "side": o.get("side", ""),
                    "qty": float(o.get("quantity", 0)),
                    "type": o.get("type", ""),
                    "status": state,
                    "filled_price": float(o.get("average_price", 0) or 0),
                    "submitted_at": o.get("created_at", ""),
                    "filled_at": o.get("updated_at", ""),
                    "broker": self.broker_name,
                })
        except Exception as exc:
            logger.error("Robinhood: get_orders failed - %s", exc)
        return orders

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_occ_symbol(occ: str):
        """Parse an OCC option symbol into (underlying, expDate, type, strike).

        Example: AAPL250321C00170000
          -> ("AAPL", "2025-03-21", "call", 170.0)
        Returns None if parsing fails.
        """
        try:
            # Find the position of the option type character (C or P)
            type_idx = None
            for i in range(len(occ) - 1, 5, -1):
                if occ[i] in ("C", "P"):
                    # Check that digits follow and precede
                    if occ[i + 1:].isdigit() and occ[i - 6:i].isdigit():
                        type_idx = i
                        break
            if type_idx is None:
                return None

            underlying = occ[:type_idx - 6].rstrip()
            date_str = occ[type_idx - 6:type_idx]  # YYMMDD
            opt_type = "call" if occ[type_idx] == "C" else "put"
            strike = int(occ[type_idx + 1:]) / 1000

            exp_date = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"
            return underlying, exp_date, opt_type, strike
        except Exception:
            return None

    @staticmethod
    def _format_option_contract(opt: dict) -> dict:
        """Normalise a Robinhood option contract dict."""
        greeks = opt.get("greeks", {}) or {}
        return {
            "strike": float(opt.get("strike_price", 0)),
            "bid": float(opt.get("bid_price", 0)),
            "ask": float(opt.get("ask_price", 0)),
            "last": float(opt.get("last_trade_price", 0) or 0),
            "volume": int(opt.get("volume", 0) or 0),
            "open_interest": int(opt.get("open_interest", 0) or 0),
            "implied_volatility": float(opt.get("implied_volatility", 0) or 0),
            "delta": float(greeks.get("delta", 0) or 0),
            "gamma": float(greeks.get("gamma", 0) or 0),
            "theta": float(greeks.get("theta", 0) or 0),
            "vega": float(greeks.get("vega", 0) or 0),
            "rho": float(greeks.get("rho", 0) or 0),
        }

    def _resolve_instrument_symbol(self, instrument_url: str) -> str:
        """Resolve an instrument URL to a ticker symbol."""
        if not instrument_url:
            return "UNKNOWN"
        try:
            import robin_stocks.robinhood as rh
            data = rh.stocks.get_instrument_by_url(instrument_url)
            return data.get("symbol", "UNKNOWN") if data else "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def _log_trade(self, order_id: str, symbol: str, side: str,
                   qty: float, order_type: str, filled_price: float,
                   status: str) -> None:
        """Persist trade to SQLite for tracking."""
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
            logger.debug("Robinhood: trade logging failed - %s", exc)
