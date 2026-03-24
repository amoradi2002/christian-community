"""
Alpaca Trading Module - Execute stock and options orders.

Supports:
- Market/Limit/Stop orders for stocks
- Options order execution (buy/sell calls/puts)
- Position management
- Paper trading (default) and live trading

IMPORTANT: Paper trading is the default. Set ALPACA_PAPER=false in .env for live trading.
"""

import os
from dataclasses import dataclass
from datetime import datetime

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLimitOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    OrderType,
    OrderStatus,
    QueryOrderStatus,
)

from bot.db.database import get_connection


@dataclass
class TradeResult:
    """Result of a trade execution."""
    success: bool
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    qty: float = 0
    order_type: str = ""
    filled_price: float = 0
    status: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "filled_price": self.filled_price,
            "status": self.status,
            "error": self.error,
        }


def _get_trading_client() -> TradingClient:
    """Create Alpaca trading client. Uses paper trading by default."""
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    paper = os.getenv("ALPACA_PAPER", "true").lower() != "false"
    return TradingClient(api_key, secret_key, paper=paper)


def get_account_info() -> dict:
    """Get Alpaca account details (balance, buying power, etc)."""
    try:
        client = _get_trading_client()
        account = client.get_account()
        return {
            "account_id": account.id,
            "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "equity": float(account.equity),
            "long_market_value": float(account.long_market_value),
            "short_market_value": float(account.short_market_value),
            "day_trades_remaining": 3 if account.pattern_day_trader else None,
            "paper": os.getenv("ALPACA_PAPER", "true").lower() != "false",
        }
    except Exception as e:
        return {"error": str(e)}


def get_positions() -> list[dict]:
    """Get all open positions."""
    try:
        client = _get_trading_client()
        positions = client.get_all_positions()
        return [
            {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "side": pos.side.value if hasattr(pos.side, 'value') else str(pos.side),
                "avg_entry": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(pos.unrealized_pl),
                "unrealized_pnl_pct": float(pos.unrealized_plpc) * 100,
            }
            for pos in positions
        ]
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []


# --- Stock Orders ---

def place_stock_order(
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_in_force: str = "day",
) -> TradeResult:
    """
    Place a stock order.

    Args:
        symbol: Stock ticker
        qty: Number of shares (supports fractional)
        side: "buy" or "sell"
        order_type: "market", "limit", or "stop_limit"
        limit_price: Required for limit/stop_limit orders
        stop_price: Required for stop_limit orders
        time_in_force: "day", "gtc", "ioc", "fok"
    """
    try:
        client = _get_trading_client()
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        tif_map = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }
        tif = tif_map.get(time_in_force.lower(), TimeInForce.DAY)

        if order_type == "market":
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
            )
        elif order_type == "limit" and limit_price:
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=limit_price,
            )
        elif order_type == "stop_limit" and limit_price and stop_price:
            request = StopLimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=limit_price,
                stop_price=stop_price,
            )
        else:
            return TradeResult(success=False, error=f"Invalid order type '{order_type}' or missing prices")

        order = client.submit_order(request)

        result = TradeResult(
            success=True,
            order_id=str(order.id),
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            filled_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
            status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        )

        # Log trade to database
        _log_trade(result)
        return result

    except Exception as e:
        return TradeResult(success=False, symbol=symbol, side=side, qty=qty, error=str(e))


# --- Options Orders ---

def place_option_order(
    contract_symbol: str,
    qty: int,
    side: str,
    order_type: str = "limit",
    limit_price: float | None = None,
    time_in_force: str = "day",
) -> TradeResult:
    """
    Place an options order.

    Args:
        contract_symbol: OCC symbol (e.g. "AAPL250321C00170000")
        qty: Number of contracts
        side: "buy" or "sell"
        order_type: "market" or "limit" (limit recommended for options)
        limit_price: Limit price per contract
        time_in_force: "day" or "gtc"
    """
    try:
        client = _get_trading_client()
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force.lower() == "day" else TimeInForce.GTC

        if order_type == "limit" and limit_price:
            request = LimitOrderRequest(
                symbol=contract_symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=limit_price,
            )
        elif order_type == "market":
            request = MarketOrderRequest(
                symbol=contract_symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
            )
        else:
            return TradeResult(
                success=False,
                error="Options orders should use 'limit' with a limit_price (wide spreads can cause bad fills)",
            )

        order = client.submit_order(request)

        result = TradeResult(
            success=True,
            order_id=str(order.id),
            symbol=contract_symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            filled_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
            status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        )

        _log_trade(result)
        return result

    except Exception as e:
        return TradeResult(
            success=False, symbol=contract_symbol, side=side, qty=qty, error=str(e)
        )


def get_orders(status: str = "open", limit: int = 50) -> list[dict]:
    """Get recent orders."""
    try:
        client = _get_trading_client()
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }
        request = GetOrdersRequest(
            status=status_map.get(status, QueryOrderStatus.OPEN),
            limit=limit,
        )
        orders = client.get_orders(request)
        return [
            {
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, 'value') else str(o.side),
                "qty": float(o.qty) if o.qty else 0,
                "type": o.type.value if hasattr(o.type, 'value') else str(o.type),
                "status": o.status.value if hasattr(o.status, 'value') else str(o.status),
                "filled_price": float(o.filled_avg_price) if o.filled_avg_price else 0,
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else "",
                "filled_at": o.filled_at.isoformat() if o.filled_at else "",
            }
            for o in orders
        ]
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return []


def cancel_order(order_id: str) -> bool:
    """Cancel an open order."""
    try:
        client = _get_trading_client()
        client.cancel_order_by_id(order_id)
        return True
    except Exception as e:
        print(f"Error canceling order {order_id}: {e}")
        return False


def _log_trade(result: TradeResult):
    """Log trade to SQLite for tracking."""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO trades
               (order_id, symbol, side, qty, order_type, filled_price, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.order_id, result.symbol, result.side, result.qty,
             result.order_type, result.filled_price, result.status,
             datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Trade logging is best-effort
