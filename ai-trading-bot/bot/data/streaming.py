"""
Real-time WebSocket price streaming from Alpaca Markets.

Provides continuous price updates via WebSocket connection to Alpaca's
IEX (free tier) or SIP (paid tier) data feed. Handles authentication,
subscriptions, auto-reconnect with exponential backoff, and thread-safe
price caching.

Usage:
    from bot.data.streaming import get_stream

    stream = get_stream()
    stream.subscribe(["AAPL", "TSLA"], callback=my_handler)
    stream.start()
    # ...
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
        self._subscribed_symbols = set()
        self._authenticated = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._base_reconnect_delay = 1.0  # seconds
        self._max_reconnect_delay = 60.0  # seconds

    def subscribe(self, symbols: list, callback=None):
        """Subscribe to real-time price updates for symbols.

        Args:
            symbols: List of ticker symbols (e.g. ["AAPL", "TSLA"]).
            callback: Optional function called on each update.
                      Signature: callback(symbol, price, data)
        """
        if not symbols:
            return

        upper_symbols = [s.upper() for s in symbols]

        with self._lock:
            for sym in upper_symbols:
                if callback is not None:
                    self.callbacks[sym].append(callback)
                self._subscribed_symbols.add(sym)

        # If already connected and authenticated, send subscription message
        if self.ws and self._authenticated:
            self._send_subscribe(upper_symbols)

    def unsubscribe(self, symbols: list):
        """Unsubscribe from symbols."""
        if not symbols:
            return

        upper_symbols = [s.upper() for s in symbols]

        with self._lock:
            for sym in upper_symbols:
                self._subscribed_symbols.discard(sym)
                self.callbacks.pop(sym, None)
                self.latest_prices.pop(sym, None)
                self.latest_quotes.pop(sym, None)

        # Send unsubscribe message if connected
        if self.ws and self._authenticated:
            try:
                msg = json.dumps({
                    "action": "unsubscribe",
                    "trades": upper_symbols,
                    "quotes": upper_symbols,
                })
                self.ws.send(msg)
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
        self._reconnect_attempts = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[PriceStream] Started WebSocket price streaming.")

    def stop(self):
        """Stop WebSocket connection."""
        self.running = False
        self._authenticated = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
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

            # If we get here, connection dropped
            if self.running:
                self._reconnect()
            else:
                break

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Alpaca sends messages as a list of events
        if not isinstance(data, list):
            data = [data]

        for msg in data:
            msg_type = msg.get("T", "")

            # Authentication response
            if msg_type == "success":
                action = msg.get("msg", "")
                if action == "connected":
                    # Connection established, now authenticate
                    pass
                elif action == "authenticated":
                    self._authenticated = True
                    self._reconnect_attempts = 0
                    print("[PriceStream] Authenticated successfully.")
                    # Subscribe to any pending symbols
                    with self._lock:
                        symbols = list(self._subscribed_symbols)
                    if symbols:
                        self._send_subscribe(symbols)

            elif msg_type == "error":
                code = msg.get("code", 0)
                error_msg = msg.get("msg", "Unknown error")
                print(f"[PriceStream] Error ({code}): {error_msg}")
                if code == 402:  # Auth failure
                    print("[PriceStream] Authentication failed. Check API keys.")
                    self.running = False

            # Trade update
            elif msg_type == "t":
                symbol = msg.get("S", "")
                price = msg.get("p", 0.0)
                size = msg.get("s", 0)
                timestamp = msg.get("t", "")

                if symbol and price:
                    with self._lock:
                        self.latest_prices[symbol] = price
                        quote = self.latest_quotes.get(symbol, {})
                        quote["last"] = price
                        quote["last_size"] = size
                        quote["last_timestamp"] = timestamp
                        self.latest_quotes[symbol] = quote

                    # Fire callbacks
                    with self._lock:
                        cbs = list(self.callbacks.get(symbol, []))
                    for cb in cbs:
                        try:
                            cb(symbol, price, {
                                "type": "trade",
                                "price": price,
                                "size": size,
                                "timestamp": timestamp,
                            })
                        except Exception as e:
                            print(f"[PriceStream] Callback error for {symbol}: {e}")

            # Quote update
            elif msg_type == "q":
                symbol = msg.get("S", "")
                bid = msg.get("bp", 0.0)
                ask = msg.get("ap", 0.0)
                bid_size = msg.get("bs", 0)
                ask_size = msg.get("as", 0)

                if symbol and (bid or ask):
                    midpoint = round((bid + ask) / 2, 4) if bid and ask else (bid or ask)
                    with self._lock:
                        self.latest_prices[symbol] = midpoint
                        self.latest_quotes[symbol] = {
                            "bid": bid,
                            "ask": ask,
                            "bid_size": bid_size,
                            "ask_size": ask_size,
                            "spread": round(ask - bid, 4) if bid and ask else 0.0,
                            "last": self.latest_quotes.get(symbol, {}).get("last", midpoint),
                            "last_size": self.latest_quotes.get(symbol, {}).get("last_size", 0),
                            "last_timestamp": self.latest_quotes.get(symbol, {}).get("last_timestamp", ""),
                        }

                    # Fire callbacks
                    with self._lock:
                        cbs = list(self.callbacks.get(symbol, []))
                    for cb in cbs:
                        try:
                            cb(symbol, midpoint, {
                                "type": "quote",
                                "bid": bid,
                                "ask": ask,
                                "bid_size": bid_size,
                                "ask_size": ask_size,
                            })
                        except Exception as e:
                            print(f"[PriceStream] Callback error for {symbol}: {e}")

            # Bar/minute aggregation update
            elif msg_type == "b":
                symbol = msg.get("S", "")
                close_price = msg.get("c", 0.0)
                volume = msg.get("v", 0)

                if symbol and close_price:
                    with self._lock:
                        self.latest_prices[symbol] = close_price
                        quote = self.latest_quotes.get(symbol, {})
                        quote["volume"] = volume
                        self.latest_quotes[symbol] = quote

    def _on_open(self, ws):
        """Authenticate on connection open."""
        auth_msg = json.dumps({
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key,
        })
        ws.send(auth_msg)

    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"[PriceStream] WebSocket error: {error}")

    def _on_close(self, ws, close_status, close_msg):
        """Handle connection close."""
        self._authenticated = False
        if self.running:
            print(f"[PriceStream] Connection closed (status={close_status}, "
                  f"msg={close_msg}). Will reconnect...")

    def _reconnect(self):
        """Auto-reconnect with exponential backoff."""
        if not self.running:
            return

        self._reconnect_attempts += 1

        if self._reconnect_attempts > self._max_reconnect_attempts:
            print(f"[PriceStream] Max reconnect attempts ({self._max_reconnect_attempts}) "
                  "reached. Stopping.")
            self.running = False
            return

        # Exponential backoff: 1s, 2s, 4s, 8s, ... up to max
        delay = min(
            self._base_reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            self._max_reconnect_delay,
        )
        print(f"[PriceStream] Reconnecting in {delay:.1f}s "
              f"(attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
        time.sleep(delay)

    def _send_subscribe(self, symbols: list):
        """Send subscription message for symbols."""
        if not self.ws or not self._authenticated:
            return
        try:
            msg = json.dumps({
                "action": "subscribe",
                "trades": symbols,
                "quotes": symbols,
            })
            self.ws.send(msg)
            print(f"[PriceStream] Subscribed to: {', '.join(symbols)}")
        except Exception as e:
            print(f"[PriceStream] Subscribe send failed: {e}")


# Singleton instance
_stream = None
_stream_lock = threading.Lock()


def get_stream() -> PriceStream:
    """Get the singleton PriceStream instance."""
    global _stream
    with _stream_lock:
        if _stream is None:
            _stream = PriceStream()
    return _stream
