"""
Real-time WebSocket price streaming from Alpaca Markets.

Provides continuous price updates via WebSocket connection to Alpaca's
IEX (free tier) or SIP (paid tier) data feed. Thread-safe with automatic
reconnection and exponential backoff.

Usage:
    from bot.data.streaming import get_stream

    stream = get_stream()
    stream.subscribe(["AAPL", "TSLA"], callback=my_handler)
    stream.start()

    # Later...
    price = stream.get_price("AAPL")
    stream.stop()
"""

import os
import json
import threading
import time
from collections import defaultdict

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False


class PriceStream:
    """Real-time WebSocket price streaming from Alpaca."""

    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
        self.ws_url = "wss://stream.data.alpaca.markets/v2/iex"  # free tier
        self.ws = None
        self.running = False
        self.callbacks = defaultdict(list)  # symbol -> [callback functions]
        self.latest_prices = {}  # symbol -> latest price
        self.latest_quotes = {}  # symbol -> {bid, ask, last, volume}
        self._lock = threading.Lock()
        self._thread = None
        self._subscribed_trades = set()
        self._subscribed_quotes = set()
        self._authenticated = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._base_reconnect_delay = 1  # seconds
        self._should_reconnect = True

    def subscribe(self, symbols: list, callback=None):
        """Subscribe to real-time price updates for symbols.

        Args:
            symbols: List of ticker symbols (e.g. ["AAPL", "TSLA"])
            callback: Optional function called on each update.
                      Signature: callback(symbol, price, data)
        """
        if not symbols:
            return

        upper_symbols = [s.upper() for s in symbols]

        with self._lock:
            for sym in upper_symbols:
                if callback and callback not in self.callbacks[sym]:
                    self.callbacks[sym].append(callback)
                self._subscribed_trades.add(sym)
                self._subscribed_quotes.add(sym)

        # If already connected, send subscription message
        if self.ws and self._authenticated:
            self._send_subscription(upper_symbols)

    def unsubscribe(self, symbols: list):
        """Unsubscribe from symbols."""
        if not symbols:
            return

        upper_symbols = [s.upper() for s in symbols]

        with self._lock:
            for sym in upper_symbols:
                self.callbacks.pop(sym, None)
                self._subscribed_trades.discard(sym)
                self._subscribed_quotes.discard(sym)

        # If connected, send unsubscribe message
        if self.ws and self._authenticated:
            try:
                unsub_msg = {
                    "action": "unsubscribe",
                    "trades": upper_symbols,
                    "quotes": upper_symbols,
                }
                self.ws.send(json.dumps(unsub_msg))
            except Exception:
                pass

    def get_price(self, symbol: str) -> float:
        """Get latest cached price for a symbol. Returns 0.0 if unavailable."""
        with self._lock:
            return self.latest_prices.get(symbol.upper(), 0.0)

    def get_quote(self, symbol: str) -> dict:
        """Get latest cached quote for a symbol."""
        with self._lock:
            return self.latest_quotes.get(symbol.upper(), {})

    def get_all_prices(self) -> dict:
        """Get all cached prices as {symbol: price}."""
        with self._lock:
            return dict(self.latest_prices)

    def start(self):
        """Start WebSocket connection in background thread."""
        if not HAS_WEBSOCKET:
            print("[PriceStream] websocket-client not installed. "
                  "Install with: pip install websocket-client")
            return

        if not self.api_key or not self.secret_key:
            print("[PriceStream] No Alpaca API keys found. "
                  "Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env to enable streaming.")
            return

        if self.running:
            print("[PriceStream] Already running.")
            return

        self.running = True
        self._should_reconnect = True
        self._reconnect_attempts = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[PriceStream] Started WebSocket streaming.")

    def stop(self):
        """Stop WebSocket connection."""
        self._should_reconnect = False
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = None
        self._authenticated = False
        print("[PriceStream] Stopped.")

    def _run(self):
        """Main WebSocket run loop (runs in background thread)."""
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                print(f"[PriceStream] WebSocket error: {e}")

            if not self.running or not self._should_reconnect:
                break

            # Reconnect with backoff
            self._reconnect()

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        if not isinstance(data, list):
            data = [data]

        for msg in data:
            msg_type = msg.get("T", "")

            # Connection/auth messages
            if msg_type == "success":
                action = msg.get("msg", "")
                if action == "connected":
                    # Send authentication
                    self._send_auth()
                elif action == "authenticated":
                    self._authenticated = True
                    self._reconnect_attempts = 0
                    print("[PriceStream] Authenticated successfully.")
                    # Re-subscribe to all symbols
                    with self._lock:
                        symbols = list(self._subscribed_trades)
                    if symbols:
                        self._send_subscription(symbols)

            elif msg_type == "error":
                error_code = msg.get("code", "")
                error_msg = msg.get("msg", "")
                print(f"[PriceStream] Server error [{error_code}]: {error_msg}")
                if error_code == 402:  # auth failure
                    print("[PriceStream] Authentication failed. Check API keys.")
                    self._should_reconnect = False

            # Trade updates
            elif msg_type == "t":
                symbol = msg.get("S", "")
                price = msg.get("p", 0.0)
                size = msg.get("s", 0)
                timestamp = msg.get("t", "")

                if symbol and price:
                    with self._lock:
                        self.latest_prices[symbol] = price
                        if symbol in self.latest_quotes:
                            self.latest_quotes[symbol]["last"] = price
                        else:
                            self.latest_quotes[symbol] = {
                                "bid": 0.0,
                                "ask": 0.0,
                                "last": price,
                                "volume": size,
                            }

                    # Fire callbacks
                    callbacks = self.callbacks.get(symbol, [])
                    trade_data = {
                        "type": "trade",
                        "symbol": symbol,
                        "price": price,
                        "size": size,
                        "timestamp": timestamp,
                    }
                    for cb in callbacks:
                        try:
                            cb(symbol, price, trade_data)
                        except Exception as e:
                            print(f"[PriceStream] Callback error for {symbol}: {e}")

            # Quote updates
            elif msg_type == "q":
                symbol = msg.get("S", "")
                bid = msg.get("bp", 0.0)
                ask = msg.get("ap", 0.0)
                bid_size = msg.get("bs", 0)
                ask_size = msg.get("as", 0)

                if symbol:
                    midpoint = round((bid + ask) / 2, 4) if bid and ask else 0.0
                    with self._lock:
                        if midpoint > 0:
                            self.latest_prices[symbol] = midpoint
                        self.latest_quotes[symbol] = {
                            "bid": bid,
                            "ask": ask,
                            "bid_size": bid_size,
                            "ask_size": ask_size,
                            "last": self.latest_quotes.get(symbol, {}).get("last", midpoint),
                            "spread": round(ask - bid, 4) if bid and ask else 0.0,
                        }

                    # Fire callbacks for quote updates
                    callbacks = self.callbacks.get(symbol, [])
                    quote_data = {
                        "type": "quote",
                        "symbol": symbol,
                        "price": midpoint,
                        "bid": bid,
                        "ask": ask,
                        "bid_size": bid_size,
                        "ask_size": ask_size,
                    }
                    for cb in callbacks:
                        try:
                            cb(symbol, midpoint, quote_data)
                        except Exception as e:
                            print(f"[PriceStream] Callback error for {symbol}: {e}")

            # Subscription confirmation
            elif msg_type == "subscription":
                trades = msg.get("trades", [])
                quotes = msg.get("quotes", [])
                if trades or quotes:
                    print(f"[PriceStream] Subscribed - trades: {trades}, quotes: {quotes}")

    def _on_open(self, ws):
        """Handle WebSocket connection opened (auth happens via on_message)."""
        print("[PriceStream] WebSocket connected.")

    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"[PriceStream] WebSocket error: {error}")

    def _on_close(self, ws, close_status, close_msg):
        """Handle WebSocket connection close."""
        self._authenticated = False
        status_str = f" (status={close_status})" if close_status else ""
        msg_str = f" {close_msg}" if close_msg else ""
        print(f"[PriceStream] WebSocket closed{status_str}{msg_str}")

    def _send_auth(self):
        """Send authentication message."""
        if not self.ws:
            return
        try:
            auth_msg = {
                "action": "auth",
                "key": self.api_key,
                "secret": self.secret_key,
            }
            self.ws.send(json.dumps(auth_msg))
        except Exception as e:
            print(f"[PriceStream] Auth send failed: {e}")

    def _send_subscription(self, symbols: list):
        """Send subscription message for symbols."""
        if not self.ws or not symbols:
            return
        try:
            sub_msg = {
                "action": "subscribe",
                "trades": symbols,
                "quotes": symbols,
            }
            self.ws.send(json.dumps(sub_msg))
        except Exception as e:
            print(f"[PriceStream] Subscription send failed: {e}")

    def _reconnect(self):
        """Auto-reconnect with exponential backoff."""
        if not self._should_reconnect:
            return

        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            print(f"[PriceStream] Max reconnect attempts ({self._max_reconnect_attempts}) "
                  f"reached. Stopping.")
            self.running = False
            return

        delay = min(
            self._base_reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            60,  # cap at 60 seconds
        )
        print(f"[PriceStream] Reconnecting in {delay}s "
              f"(attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_stream = None
_stream_lock = threading.Lock()


def get_stream() -> PriceStream:
    """Get or create the singleton PriceStream instance."""
    global _stream
    with _stream_lock:
        if _stream is None:
            _stream = PriceStream()
    return _stream
