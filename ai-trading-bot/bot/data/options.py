"""
Options data provider using Alpaca Markets API.

Supports:
- Options chain lookup (calls/puts for a symbol)
- Real-time options quotes
- Greeks (delta, gamma, theta, vega, IV)
- Options contract search by strike/expiry
"""

import os
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import (
    OptionChainRequest,
    OptionLatestQuoteRequest,
    OptionSnapshotRequest,
    OptionBarsRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


@dataclass
class OptionContract:
    """Represents a single options contract."""
    symbol: str            # e.g. "AAPL250321C00170000"
    underlying: str        # e.g. "AAPL"
    expiration: str        # e.g. "2025-03-21"
    strike: float          # e.g. 170.00
    option_type: str       # "call" or "put"
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    @property
    def mid_price(self) -> float:
        return round((self.bid + self.ask) / 2, 4) if self.bid and self.ask else self.last

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 4) if self.bid and self.ask else 0.0

    @property
    def days_to_expiry(self) -> int:
        exp = datetime.strptime(self.expiration, "%Y-%m-%d")
        return max(0, (exp - datetime.now()).days)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "expiration": self.expiration,
            "strike": self.strike,
            "type": self.option_type,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid_price,
            "last": self.last,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "iv": self.implied_volatility,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "spread": self.spread,
            "dte": self.days_to_expiry,
        }


@dataclass
class OptionsChain:
    """Full options chain for a symbol."""
    underlying: str
    underlying_price: float
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)
    expirations: list[str] = field(default_factory=list)

    def get_calls_by_expiry(self, expiry: str) -> list[OptionContract]:
        return [c for c in self.calls if c.expiration == expiry]

    def get_puts_by_expiry(self, expiry: str) -> list[OptionContract]:
        return [p for p in self.puts if p.expiration == expiry]

    def get_atm_strike(self) -> float:
        """Get the at-the-money strike closest to current price."""
        all_strikes = sorted(set(c.strike for c in self.calls + self.puts))
        if not all_strikes:
            return self.underlying_price
        return min(all_strikes, key=lambda s: abs(s - self.underlying_price))

    def get_near_money(self, num_strikes: int = 5) -> dict:
        """Get contracts near the money (most liquid)."""
        atm = self.get_atm_strike()
        all_strikes = sorted(set(c.strike for c in self.calls + self.puts))
        near = sorted(all_strikes, key=lambda s: abs(s - atm))[:num_strikes * 2 + 1]

        return {
            "calls": [c for c in self.calls if c.strike in near],
            "puts": [p for p in self.puts if p.strike in near],
        }

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying,
            "underlying_price": self.underlying_price,
            "expirations": self.expirations,
            "calls": [c.to_dict() for c in self.calls],
            "puts": [p.to_dict() for p in self.puts],
        }


def _get_options_client() -> OptionHistoricalDataClient:
    """Create Alpaca options data client."""
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
    return OptionHistoricalDataClient(api_key, secret_key)


def get_options_chain(
    symbol: str,
    expiry_min: str | None = None,
    expiry_max: str | None = None,
    option_type: str | None = None,
) -> OptionsChain:
    """
    Fetch the options chain for a symbol.

    Args:
        symbol: Underlying ticker (e.g. "AAPL")
        expiry_min: Earliest expiration to include (YYYY-MM-DD)
        expiry_max: Latest expiration to include (YYYY-MM-DD)
        option_type: Filter by "call" or "put" (None = both)
    """
    client = _get_options_client()

    # Get underlying price for ATM reference
    from bot.data.alpaca_provider import fetch_alpaca_realtime
    underlying_data = fetch_alpaca_realtime(symbol)
    underlying_price = underlying_data["price"] if underlying_data else 0

    # Build chain request
    kwargs = {"underlying_symbols": [symbol]}

    if expiry_min:
        kwargs["expiration_date_gte"] = expiry_min
    else:
        kwargs["expiration_date_gte"] = datetime.now().strftime("%Y-%m-%d")

    if expiry_max:
        kwargs["expiration_date_lte"] = expiry_max
    else:
        # Default: next 45 days of expirations
        kwargs["expiration_date_lte"] = (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")

    if option_type:
        kwargs["type"] = option_type

    try:
        request = OptionChainRequest(**kwargs)
        snapshots = client.get_option_chain(request)
    except Exception as e:
        print(f"Options chain fetch failed for {symbol}: {e}")
        return OptionsChain(underlying=symbol, underlying_price=underlying_price)

    calls = []
    puts = []
    expirations = set()

    for contract_symbol, snap in snapshots.items():
        # Parse contract symbol: e.g. "AAPL250321C00170000"
        contract = _parse_option_snapshot(contract_symbol, symbol, snap)
        if contract:
            expirations.add(contract.expiration)
            if contract.option_type == "call":
                calls.append(contract)
            else:
                puts.append(contract)

    # Sort by expiration then strike
    calls.sort(key=lambda c: (c.expiration, c.strike))
    puts.sort(key=lambda p: (p.expiration, p.strike))

    return OptionsChain(
        underlying=symbol,
        underlying_price=underlying_price,
        calls=calls,
        puts=puts,
        expirations=sorted(expirations),
    )


def get_option_quote(contract_symbol: str) -> OptionContract | None:
    """Get real-time quote for a specific options contract."""
    try:
        client = _get_options_client()
        request = OptionLatestQuoteRequest(symbol_or_symbols=contract_symbol)
        quotes = client.get_option_latest_quote(request)
        quote = quotes.get(contract_symbol)
        if not quote:
            return None

        # Parse the contract symbol for metadata
        parsed = _parse_contract_symbol(contract_symbol)

        return OptionContract(
            symbol=contract_symbol,
            underlying=parsed.get("underlying", ""),
            expiration=parsed.get("expiration", ""),
            strike=parsed.get("strike", 0),
            option_type=parsed.get("type", "call"),
            bid=round(quote.bid_price, 4),
            ask=round(quote.ask_price, 4),
        )
    except Exception as e:
        print(f"Option quote failed for {contract_symbol}: {e}")
        return None


def _parse_option_snapshot(contract_symbol: str, underlying: str, snap) -> OptionContract | None:
    """Parse an Alpaca option snapshot into an OptionContract."""
    try:
        parsed = _parse_contract_symbol(contract_symbol)

        contract = OptionContract(
            symbol=contract_symbol,
            underlying=underlying,
            expiration=parsed.get("expiration", ""),
            strike=parsed.get("strike", 0),
            option_type=parsed.get("type", "call"),
        )

        # Fill in quote data from snapshot
        if snap.latest_quote:
            contract.bid = round(snap.latest_quote.bid_price, 4)
            contract.ask = round(snap.latest_quote.ask_price, 4)

        if snap.latest_trade:
            contract.last = round(snap.latest_trade.price, 4)

        # Greeks if available
        if hasattr(snap, "greeks") and snap.greeks:
            contract.implied_volatility = round(snap.greeks.implied_volatility or 0, 4)
            contract.delta = round(snap.greeks.delta or 0, 4)
            contract.gamma = round(snap.greeks.gamma or 0, 4)
            contract.theta = round(snap.greeks.theta or 0, 4)
            contract.vega = round(snap.greeks.vega or 0, 4)

        return contract
    except Exception as e:
        print(f"Error parsing option {contract_symbol}: {e}")
        return None


def _parse_contract_symbol(symbol: str) -> dict:
    """
    Parse OCC option symbol format.
    Example: AAPL250321C00170000
    -> underlying=AAPL, expiry=2025-03-21, type=call, strike=170.00
    """
    # Find where the date part starts (6 digits before C/P)
    for i in range(len(symbol)):
        if symbol[i:i+6].isdigit() and i + 6 < len(symbol) and symbol[i+6] in ("C", "P"):
            underlying = symbol[:i]
            date_str = symbol[i:i+6]
            opt_type = "call" if symbol[i+6] == "C" else "put"
            strike_str = symbol[i+7:]
            strike = int(strike_str) / 1000.0

            year = 2000 + int(date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            expiry = f"{year}-{month:02d}-{day:02d}"

            return {
                "underlying": underlying,
                "expiration": expiry,
                "type": opt_type,
                "strike": strike,
            }

    return {"underlying": symbol, "expiration": "", "type": "call", "strike": 0}
