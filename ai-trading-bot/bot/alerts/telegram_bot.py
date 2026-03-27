"""
Telegram Bot - Interactive command bot for the AI Trading Bot.

Supports receiving commands via Telegram and responding with analysis,
scans, portfolio info, and more. Uses the Telegram Bot API directly
with ``requests`` to avoid extra dependencies.

Commands:
    /analyze AAPL   - Full analysis on a symbol
    /rsi AAPL       - RSI check with options guidance
    /scan           - Run full scan
    /day            - Day trade scan
    /swing          - Swing trade scan
    /watchlist      - Show current watchlist
    /add AAPL       - Add symbol to watchlist
    /remove AAPL    - Remove symbol from watchlist
    /portfolio      - Show open paper positions
    /pnl            - Today's P&L
    /sectors        - Sector rotation report
    /risk AAPL 150 145 - Calculate position size
    /status         - Bot status
    /help           - List all commands
"""

import os
import threading
import time
import traceback
from datetime import datetime

import requests

from bot.config.settings import CONFIG
from bot.engine.signal import Signal

# ---------------------------------------------------------------------------
# Emoji / formatting helpers
# ---------------------------------------------------------------------------

_ACTION_ICON = {"BUY": "\u2705", "SELL": "\u274c", "HOLD": "\u26a0\ufe0f"}
_STYLE_LABEL = {"day": "Day Trade", "swing": "Swing Trade", "options": "Options"}


def _escape_md(text: str) -> str:
    """Escape characters that conflict with Telegram Markdown v1."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------------------------------------------------------------------------
# TelegramBot
# ---------------------------------------------------------------------------

class TelegramBot:
    """Interactive Telegram bot that receives commands and sends alerts."""

    def __init__(self):
        cfg = CONFIG.get("alerts", {}).get("telegram", {})
        self.token = cfg.get("bot_token", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = cfg.get("chat_id", "") or os.getenv("TELEGRAM_CHAT_ID", "")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.running = False
        self.last_update_id = 0
        self.commands: dict[str, callable] = {}
        self._started_at: datetime | None = None
        self._commands_processed = 0
        self._poll_thread: threading.Thread | None = None
        self._register_commands()

    # ------------------------------------------------------------------
    # Command registration
    # ------------------------------------------------------------------

    def _register_commands(self):
        """Map slash-command strings to handler methods."""
        self.commands = {
            "analyze": self._handle_analyze,
            "rsi": self._handle_rsi,
            "scan": self._handle_scan,
            "day": self._handle_day_scan,
            "swing": self._handle_swing_scan,
            "watchlist": self._handle_watchlist,
            "add": self._handle_add,
            "remove": self._handle_remove,
            "portfolio": self._handle_portfolio,
            "pnl": self._handle_pnl,
            "sectors": self._handle_sectors,
            "risk": self._handle_risk,
            "sentiment": self._handle_sentiment,
            "calendar": self._handle_calendar,
            "learn": self._handle_learn,
            "knowledge": self._handle_knowledge,
            "strats": self._handle_strats,
            "status": self._handle_status,
            "help": self._handle_help,
        }

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_message(self, text: str, parse_mode: str = "Markdown", chat_id: str | None = None) -> bool:
        """Send a message to the configured chat (or a specific chat_id).

        Long messages are automatically split into chunks that respect
        Telegram's 4096-character limit.
        """
        target = chat_id or self.chat_id
        if not self.token or not target:
            return False

        url = f"{self.base_url}/sendMessage"

        # Split long messages
        max_len = 4000  # leave some margin for safety
        chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]

        success = True
        for chunk in chunks:
            payload = {
                "chat_id": target,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            try:
                resp = requests.post(url, json=payload, timeout=15)
                if not resp.ok:
                    print(f"Telegram send failed ({resp.status_code}): {resp.text[:200]}")
                    success = False
            except Exception as exc:
                print(f"Telegram send error: {exc}")
                success = False

        return success

    def send_alert(self, signal: Signal) -> bool:
        """Format and send a trading signal alert."""
        icon = _ACTION_ICON.get(signal.action, "\u26aa")
        style = _STYLE_LABEL.get(signal.style, "")
        reasons = "\n".join(f"  \u2022 {r}" for r in signal.reasons)

        lines = [
            f"{icon} *{signal.action} \u2014 {signal.symbol}* @ ${signal.price:.2f}",
            "",
            f"Confidence: {signal.confidence:.0%}",
            f"Strategy: {signal.strategy_name}",
        ]

        if style:
            lines.append(f"Style: {style}")
        if signal.setup:
            lines.append(f"Setup: {signal.setup}")
        if signal.catalyst_tier:
            lines.append(f"Catalyst Tier: {signal.catalyst_tier}")
        if signal.stop_loss:
            lines.append(f"Stop Loss: ${signal.stop_loss:.2f}")
        if signal.target:
            lines.append(f"Target: ${signal.target:.2f}")
        if signal.risk_reward:
            lines.append(f"R:R: {signal.risk_reward:.1f}:1")
        if signal.candle_pattern:
            lines.append(f"Candle: {signal.candle_pattern}")

        if reasons:
            lines.append("")
            lines.append(f"Reasons:\n{reasons}")

        lines.append("")
        lines.append("_AI Trading Bot | Not financial advice_")

        return self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def start_polling(self):
        """Start polling for incoming commands in a background thread."""
        if self.running:
            return
        if not self.token:
            print("Telegram bot token not configured \u2014 polling not started.")
            return

        self.running = True
        self._started_at = datetime.now()
        self._poll_thread = threading.Thread(target=self._poll_updates, daemon=True, name="telegram-poll")
        self._poll_thread.start()
        print("Telegram bot polling started.")

    def stop_polling(self):
        """Signal the polling loop to stop."""
        self.running = False

    def _poll_updates(self):
        """Long-poll the Telegram getUpdates endpoint and dispatch to handlers."""
        url = f"{self.base_url}/getUpdates"

        while self.running:
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 30,
                "allowed_updates": '["message"]',
            }
            try:
                resp = requests.get(url, params=params, timeout=35)
                if not resp.ok:
                    print(f"Telegram poll error ({resp.status_code}): {resp.text[:200]}")
                    time.sleep(5)
                    continue

                data = resp.json()
                for update in data.get("result", []):
                    self.last_update_id = update["update_id"]
                    self._dispatch(update)

            except requests.exceptions.Timeout:
                continue
            except Exception as exc:
                print(f"Telegram poll exception: {exc}")
                time.sleep(5)

    def _dispatch(self, update: dict):
        """Parse an incoming update and route to the appropriate handler."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not text or not text.startswith("/"):
            return

        # Strip bot username suffix (e.g. /scan@MyBotName)
        parts = text.split()
        command_raw = parts[0].lstrip("/").split("@")[0].lower()
        args = parts[1:]

        handler = self.commands.get(command_raw)
        if handler is None:
            self.send_message(f"Unknown command: /{command_raw}\nType /help for available commands.", chat_id=chat_id)
            return

        try:
            self._commands_processed += 1
            handler(*args, _chat_id=chat_id)
        except Exception as exc:
            tb = traceback.format_exc()
            print(f"Telegram handler error for /{command_raw}: {tb}")
            self.send_message(f"\u26a0\ufe0f Error running /{command_raw}: {exc}", chat_id=chat_id)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _handle_analyze(self, *args, _chat_id: str = ""):
        """Run full analysis on a symbol and send the results."""
        if not args:
            self.send_message("\u2753 Usage: `/analyze AAPL`", chat_id=_chat_id)
            return

        symbol = args[0].upper()
        self.send_message(f"\U0001f50d Analyzing *{symbol}*...", chat_id=_chat_id)

        try:
            from bot.engine.analyzer import Analyzer
            analyzer = Analyzer()
            signals = analyzer.analyze_symbol(symbol)
        except Exception as exc:
            self.send_message(f"\u274c Analysis failed for {symbol}: {exc}", chat_id=_chat_id)
            return

        if not signals:
            self.send_message(f"No actionable signals for *{symbol}* right now.", chat_id=_chat_id)
            return

        for sig in signals:
            self.send_alert(sig)

    def _handle_rsi(self, *args, _chat_id: str = ""):
        """Check RSI and provide options guidance."""
        if not args:
            self.send_message("\u2753 Usage: `/rsi AAPL`", chat_id=_chat_id)
            return

        symbol = args[0].upper()

        try:
            from bot.engine.analyzer import _fetch_candles
            from bot.data.indicators import compute_indicators

            candles = _fetch_candles(symbol, interval="1d", days=60)
            if not candles or len(candles) < 14:
                self.send_message(f"\u274c Not enough data for RSI on *{symbol}*.", chat_id=_chat_id)
                return

            ind = compute_indicators(candles)
            rsi = getattr(ind, "rsi", None) or getattr(ind, "rsi_14", None)
            if rsi is None:
                self.send_message(f"\u274c Could not compute RSI for *{symbol}*.", chat_id=_chat_id)
                return

            price = candles[-1].get("close", candles[-1].get("Close", 0))

            # Determine zone
            if rsi < 30:
                zone = "\U0001f7e2 Oversold"
                options_hint = "Consider CALLS (bullish reversal potential). Look for RSI divergence + candle confirmation."
            elif rsi < 40:
                zone = "\U0001f7e1 Near oversold"
                options_hint = "Watch for reversal. Calls if support holds; wait for confirmation."
            elif rsi > 70:
                zone = "\U0001f534 Overbought"
                options_hint = "Consider PUTS or take profits. Watch for bearish divergence."
            elif rsi > 60:
                zone = "\U0001f7e1 Near overbought"
                options_hint = "Momentum still bullish but watch for exhaustion."
            else:
                zone = "\u26aa Neutral"
                options_hint = "No strong RSI signal. Wait for extremes or use other setups."

            text = (
                f"\U0001f4ca *RSI Report \u2014 {symbol}*\n\n"
                f"Price: ${price:.2f}\n"
                f"RSI(14): *{rsi:.1f}*\n"
                f"Zone: {zone}\n\n"
                f"\U0001f4a1 *Options Guidance:*\n{options_hint}"
            )
            self.send_message(text, chat_id=_chat_id)

        except Exception as exc:
            self.send_message(f"\u274c RSI check failed for {symbol}: {exc}", chat_id=_chat_id)

    def _handle_scan(self, *args, _chat_id: str = ""):
        """Run a full watchlist scan and send results."""
        self.send_message("\U0001f50e Running full scan...", chat_id=_chat_id)

        try:
            from bot.engine.analyzer import Analyzer
            analyzer = Analyzer()
            watchlist = CONFIG.get("bot", {}).get("watchlist", [])

            if not watchlist:
                self.send_message("Watchlist is empty. Add symbols with /add AAPL", chat_id=_chat_id)
                return

            all_signals = []
            for symbol in watchlist:
                try:
                    sigs = analyzer.analyze_symbol(symbol)
                    all_signals.extend(sigs)
                except Exception:
                    pass

            if not all_signals:
                self.send_message("Scan complete \u2014 no actionable signals found.", chat_id=_chat_id)
                return

            self._send_scan_summary(all_signals, "Full Scan", _chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Scan failed: {exc}", chat_id=_chat_id)

    def _handle_day_scan(self, *args, _chat_id: str = ""):
        """Run day-trade specific scan."""
        self.send_message("\u26a1 Running day trade scan...", chat_id=_chat_id)

        try:
            from bot.engine.analyzer import Analyzer
            analyzer = Analyzer()
            watchlist = CONFIG.get("bot", {}).get("watchlist", [])

            if not watchlist:
                self.send_message("Watchlist is empty. Add symbols with /add AAPL", chat_id=_chat_id)
                return

            day_signals = []
            for symbol in watchlist:
                try:
                    sigs = analyzer.analyze_symbol(symbol, interval="5m")
                    day_signals.extend(s for s in sigs if s.style == "day")
                except Exception:
                    pass

            if not day_signals:
                self.send_message("Day scan complete \u2014 no day trade signals found.", chat_id=_chat_id)
                return

            self._send_scan_summary(day_signals, "Day Trade Scan", _chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Day scan failed: {exc}", chat_id=_chat_id)

    def _handle_swing_scan(self, *args, _chat_id: str = ""):
        """Run swing-trade specific scan."""
        self.send_message("\U0001f4c8 Running swing trade scan...", chat_id=_chat_id)

        try:
            from bot.engine.analyzer import Analyzer
            analyzer = Analyzer()
            watchlist = CONFIG.get("bot", {}).get("watchlist", [])

            if not watchlist:
                self.send_message("Watchlist is empty. Add symbols with /add AAPL", chat_id=_chat_id)
                return

            swing_signals = []
            for symbol in watchlist:
                try:
                    sigs = analyzer.analyze_symbol(symbol, interval="1d")
                    swing_signals.extend(s for s in sigs if s.style == "swing")
                except Exception:
                    pass

            if not swing_signals:
                self.send_message("Swing scan complete \u2014 no swing trade signals found.", chat_id=_chat_id)
                return

            self._send_scan_summary(swing_signals, "Swing Trade Scan", _chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Swing scan failed: {exc}", chat_id=_chat_id)

    def _handle_watchlist(self, *args, _chat_id: str = ""):
        """Show the current watchlist."""
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        if not watchlist:
            self.send_message("Watchlist is empty. Add symbols with `/add AAPL`", chat_id=_chat_id)
            return

        lines = ["\U0001f4cb *Watchlist*", ""]
        for i, sym in enumerate(watchlist, 1):
            lines.append(f"  {i}. `{sym}`")
        lines.append(f"\n_{len(watchlist)} symbol(s) total_")

        self.send_message("\n".join(lines), chat_id=_chat_id)

    def _handle_add(self, *args, _chat_id: str = ""):
        """Add a symbol to the watchlist."""
        if not args:
            self.send_message("\u2753 Usage: `/add AAPL`", chat_id=_chat_id)
            return

        symbol = args[0].upper()
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])

        if symbol in watchlist:
            self.send_message(f"*{symbol}* is already on the watchlist.", chat_id=_chat_id)
            return

        watchlist.append(symbol)
        self.send_message(f"\u2705 Added *{symbol}* to watchlist ({len(watchlist)} total).", chat_id=_chat_id)

    def _handle_remove(self, *args, _chat_id: str = ""):
        """Remove a symbol from the watchlist."""
        if not args:
            self.send_message("\u2753 Usage: `/remove AAPL`", chat_id=_chat_id)
            return

        symbol = args[0].upper()
        watchlist = CONFIG.get("bot", {}).get("watchlist", [])

        if symbol not in watchlist:
            self.send_message(f"*{symbol}* is not on the watchlist.", chat_id=_chat_id)
            return

        watchlist.remove(symbol)
        self.send_message(f"\u274c Removed *{symbol}* from watchlist ({len(watchlist)} remaining).", chat_id=_chat_id)

    def _handle_portfolio(self, *args, _chat_id: str = ""):
        """Show open paper trading positions."""
        try:
            from bot.engine.paper_trader import PaperTrader
            trader = PaperTrader()
            positions = trader.get_open_positions()
        except Exception as exc:
            self.send_message(f"\u274c Could not load portfolio: {exc}", chat_id=_chat_id)
            return

        if not positions:
            self.send_message("\U0001f4bc No open positions.", chat_id=_chat_id)
            return

        lines = ["\U0001f4bc *Open Positions*", ""]
        total_value = 0.0
        for pos in positions:
            sym = pos.get("symbol", "?")
            qty = pos.get("quantity", 0)
            entry = pos.get("entry_price", 0)
            sl = pos.get("stop_loss", 0)
            tp = pos.get("target_price", 0)
            value = qty * entry
            total_value += value

            line = f"\u2022 *{sym}* \u2014 {qty} shares @ ${entry:.2f}"
            if sl:
                line += f" | SL ${sl:.2f}"
            if tp:
                line += f" | TP ${tp:.2f}"
            lines.append(line)

        lines.append(f"\n_Total exposure: ${total_value:,.2f}_")
        self.send_message("\n".join(lines), chat_id=_chat_id)

    def _handle_pnl(self, *args, _chat_id: str = ""):
        """Show today's P&L summary."""
        try:
            from bot.engine.daily_pnl import DailyPnLTracker
            tracker = DailyPnLTracker()
            pnl = tracker.get_today_pnl()
        except Exception as exc:
            self.send_message(f"\u274c Could not load P&L: {exc}", chat_id=_chat_id)
            return

        total = pnl.get("total_pnl", 0)
        trades = pnl.get("trade_count", 0)
        winners = pnl.get("winners", 0)
        losers = pnl.get("losers", 0)
        locked = pnl.get("is_locked_out", False)

        pnl_icon = "\U0001f7e2" if total >= 0 else "\U0001f534"
        lock_msg = "\n\u26d4 *DAILY LOSS LIMIT HIT \u2014 LOCKED OUT*" if locked else ""

        lines = [
            f"{pnl_icon} *Today's P&L*",
            "",
            f"Net P&L: *${total:+,.2f}*",
            f"Trades: {trades} ({winners}W / {losers}L)",
        ]

        # Per-symbol breakdown
        by_symbol = pnl.get("pnl_by_symbol", {})
        if by_symbol:
            lines.append("")
            lines.append("*By Symbol:*")
            for sym, amt in sorted(by_symbol.items(), key=lambda x: x[1], reverse=True):
                icon = "\U0001f7e2" if amt >= 0 else "\U0001f534"
                lines.append(f"  {icon} {sym}: ${amt:+,.2f}")

        if lock_msg:
            lines.append(lock_msg)

        self.send_message("\n".join(lines), chat_id=_chat_id)

    def _handle_sectors(self, *args, _chat_id: str = ""):
        """Show sector rotation report."""
        try:
            from bot.engine.sector_rotation import analyze_sector_rotation, SECTOR_ETFS
            from bot.engine.analyzer import _fetch_candles

            # Build sector data
            sector_data = {}
            for etf in list(SECTOR_ETFS.keys()) + ["SPY"]:
                try:
                    candles = _fetch_candles(etf, interval="1d", days=30)
                    if candles and len(candles) >= 2:
                        latest = candles[-1]
                        prev = candles[-2]
                        close = latest.get("close", latest.get("Close", 0))
                        prev_close = prev.get("close", prev.get("Close", 0))
                        change = ((close - prev_close) / prev_close * 100) if prev_close else 0
                        sector_data[etf] = {"close": close, "change_pct": change}
                except Exception:
                    pass

            if not sector_data:
                self.send_message("\u274c Could not fetch sector data.", chat_id=_chat_id)
                return

            report = analyze_sector_rotation(sector_data)

            # Format report
            regime_icon = {
                "risk-on": "\U0001f680",
                "risk-off": "\U0001f6e1\ufe0f",
                "mixed": "\u2696\ufe0f",
            }.get(report.market_regime, "\U0001f4ca")

            lines = [
                f"\U0001f4ca *Sector Rotation Report*",
                "",
                f"Market Regime: {regime_icon} *{report.market_regime.title()}*",
                f"SPY: {report.spy_change_pct:+.2f}%",
                "",
            ]

            if report.top_sectors:
                lines.append("*Leading Sectors:*")
                for s in report.sectors[:3]:
                    lines.append(f"  \u2b06\ufe0f {s.symbol} ({s.name}) {s.relative_to_spy:+.1f}% vs SPY")
                lines.append("")

            if report.bottom_sectors:
                lines.append("*Lagging Sectors:*")
                for s in report.sectors[-3:]:
                    lines.append(f"  \u2b07\ufe0f {s.symbol} ({s.name}) {s.relative_to_spy:+.1f}% vs SPY")
                lines.append("")

            if report.recommendation:
                lines.append(f"\U0001f4a1 {report.recommendation}")

            self.send_message("\n".join(lines), chat_id=_chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Sector report failed: {exc}", chat_id=_chat_id)

    def _handle_risk(self, *args, _chat_id: str = ""):
        """Calculate position size for a trade.

        Usage: /risk AAPL 150 145
            symbol, entry price, stop loss price
        """
        if len(args) < 3:
            self.send_message(
                "\u2753 Usage: `/risk AAPL 150 145`\n"
                "(symbol, entry price, stop loss price)",
                chat_id=_chat_id,
            )
            return

        symbol = args[0].upper()
        try:
            entry_price = float(args[1])
            stop_price = float(args[2])
        except ValueError:
            self.send_message("\u274c Prices must be numbers. Example: `/risk AAPL 150 145`", chat_id=_chat_id)
            return

        if stop_price >= entry_price:
            self.send_message("\u274c Stop loss must be below entry price.", chat_id=_chat_id)
            return

        try:
            from bot.engine.risk_manager import RiskManager
            rm = RiskManager()

            stop_pct = ((entry_price - stop_price) / entry_price) * 100
            result = rm.calculate_position_size(symbol, entry_price, stop_loss_pct=stop_pct)
        except Exception as exc:
            self.send_message(f"\u274c Position sizing failed: {exc}", chat_id=_chat_id)
            return

        can_trade = result.get("can_trade", False)
        status_icon = "\u2705" if can_trade else "\u26d4"

        lines = [
            f"\U0001f4b0 *Position Size \u2014 {symbol}*",
            "",
            f"Entry: ${entry_price:.2f}",
            f"Stop Loss: ${stop_price:.2f} ({stop_pct:.1f}%)",
            "",
            f"Shares: *{result.get('shares', 0)}*",
            f"Position Value: ${result.get('position_value', 0):,.2f}",
            f"Risk Amount: ${result.get('risk_amount', 0):,.2f}",
            f"Take Profit: ${result.get('take_profit_price', 0):.2f}",
            "",
            f"Status: {status_icon} {'Allowed' if can_trade else 'BLOCKED'}",
        ]

        reason = result.get("reason", "")
        if reason:
            lines.append(f"Reason: _{reason}_")

        self.send_message("\n".join(lines), chat_id=_chat_id)

    def _handle_sentiment(self, *args, _chat_id: str = ""):
        """News sentiment for a symbol."""
        if not args:
            self.send_message("\u2753 Usage: `/sentiment AAPL`", chat_id=_chat_id)
            return

        symbol = args[0].upper()
        self.send_message(f"\U0001f4f0 Checking sentiment for *{symbol}*...", chat_id=_chat_id)

        try:
            from bot.engine.news_sentiment import fetch_news_sentiment
            result = fetch_news_sentiment(symbol)

            label = result.get("overall_label", "N/A")
            score = result.get("overall_score", 0)
            icon = "\U0001f7e2" if score > 0.2 else "\U0001f534" if score < -0.2 else "\U0001f7e1"

            lines = [f"{icon} *{symbol} News Sentiment: {label}* (score: {score:+.2f})", ""]
            for h in result.get("headlines", [])[:6]:
                h_icon = "+" if h["score"] > 0 else "-" if h["score"] < 0 else " "
                lines.append(f"  [{h_icon}] {h['headline'][:70]}")

            rec = result.get("recommendation")
            if rec:
                lines.append(f"\n\U0001f4a1 {rec}")

            self.send_message("\n".join(lines), chat_id=_chat_id)
        except Exception as exc:
            self.send_message(f"\u274c Sentiment check failed: {exc}", chat_id=_chat_id)

    def _handle_calendar(self, *args, _chat_id: str = ""):
        """Show upcoming economic events."""
        try:
            from bot.engine.economic_calendar import get_upcoming_events, get_trading_caution

            caution = get_trading_caution()
            events = get_upcoming_events(days_ahead=7)

            lines = ["\U0001f4c5 *Economic Calendar*", ""]
            if caution:
                lines.append(f"\u26a0\ufe0f *{caution}*\n")

            if events:
                for e in events[:10]:
                    imp = "\U0001f534" if e.importance == "high" else "\U0001f7e1" if e.importance == "medium" else "\u26aa"
                    lines.append(f"  {imp} {e.date} {e.time} \u2014 {e.event}")
                    if e.trading_note:
                        lines.append(f"     _{e.trading_note}_")
            else:
                lines.append("No major events this week.")

            self.send_message("\n".join(lines), chat_id=_chat_id)
        except Exception as exc:
            self.send_message(f"\u274c Calendar failed: {exc}", chat_id=_chat_id)

    def _handle_learn(self, *args, _chat_id: str = ""):
        """Ingest a YouTube URL or text into the knowledge base.

        Usage:
            /learn https://youtube.com/watch?v=...
            /learn My mentor said always use 2:1 R:R minimum and never risk more than 1% per trade
        """
        if not args:
            self.send_message(
                "\U0001f4da *Feed the bot knowledge!*\n\n"
                "YouTube: `/learn https://youtube.com/watch?v=...`\n"
                "Notes: `/learn My mentor said always use 2:1 R:R minimum`\n\n"
                "The bot extracts strategies, indicators, patterns, and rules from anything you feed it.",
                chat_id=_chat_id,
            )
            return

        content = " ".join(args)

        try:
            from bot.learning.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()

            if "youtube.com" in content or "youtu.be" in content:
                self.send_message("\U0001f3ac Ingesting YouTube video...", chat_id=_chat_id)
                result = kb.ingest_youtube(content)
            else:
                self.send_message("\U0001f4dd Ingesting knowledge...", chat_id=_chat_id)
                result = kb.ingest_text(
                    title="Telegram input",
                    content=content,
                    source_type="mentorship",
                    confidence=0.85,
                )

            if result.get("status") == "success":
                lines = [
                    "\u2705 *Knowledge ingested!*",
                    "",
                    f"Strategies found: {result.get('strategies_found', 0)}",
                    f"Indicators found: {result.get('indicators_found', 0)}",
                    f"Rules extracted: {result.get('rules_extracted', 0)}",
                    "",
                    "_The bot is now smarter. Keep feeding it!_",
                ]
                self.send_message("\n".join(lines), chat_id=_chat_id)
            else:
                self.send_message(f"\u274c {result.get('message', 'Ingestion failed')}", chat_id=_chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Learn failed: {exc}", chat_id=_chat_id)

    def _handle_knowledge(self, *args, _chat_id: str = ""):
        """Show knowledge base summary or search it."""
        try:
            from bot.learning.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()

            if args:
                # Search
                query = " ".join(args)
                results = kb.search_knowledge(query, limit=5)
                if results:
                    lines = [f"\U0001f50d *Knowledge: '{query}'*", ""]
                    for r in results:
                        lines.append(f"\u2022 [{r['source_type']}] {r['title']}")
                        for rule in r.get('key_rules', [])[:2]:
                            lines.append(f"  _{rule[:80]}_")
                    self.send_message("\n".join(lines), chat_id=_chat_id)
                else:
                    self.send_message(f"No knowledge found for '{query}'", chat_id=_chat_id)
                return

            summary = kb.get_evolution_summary()
            lines = [
                "\U0001f9e0 *Knowledge Base*",
                "",
                f"Entries: {summary['total_entries']}",
                f"Rules: {summary['total_rules']}",
                f"Strategies: {summary['unique_strategies']}",
                f"Indicators: {summary['unique_indicators']}",
                "",
                f"Sources: {summary['sources_breakdown']}",
                "",
                "_Feed me with /learn <url or notes>_",
            ]
            self.send_message("\n".join(lines), chat_id=_chat_id)

        except Exception as exc:
            self.send_message(f"\u274c Knowledge base error: {exc}", chat_id=_chat_id)

    def _handle_strats(self, *args, _chat_id: str = ""):
        """Show strategy performance stats."""
        try:
            from bot.engine.strategy_tracker import get_strategy_stats
            stats = get_strategy_stats()

            if not stats:
                self.send_message("\U0001f4ca No strategy data yet. Stats build as signals fire.", chat_id=_chat_id)
                return

            lines = ["\U0001f4ca *Strategy Performance*", ""]
            for name, s in sorted(stats.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True):
                wr = s.get("win_rate", 0)
                lines.append(f"  {name}: {s['total_signals']} signals | WR {wr:.0%} | ${s.get('total_pnl', 0):+.2f}")

            self.send_message("\n".join(lines), chat_id=_chat_id)
        except Exception as exc:
            self.send_message(f"\u274c Stats failed: {exc}", chat_id=_chat_id)

    def _handle_status(self, *args, _chat_id: str = ""):
        """Show bot status and uptime."""
        uptime = "unknown"
        if self._started_at:
            delta = datetime.now() - self._started_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m {seconds}s"

        watchlist = CONFIG.get("bot", {}).get("watchlist", [])
        threshold = CONFIG.get("bot", {}).get("confidence_threshold", 0.65)
        provider = CONFIG.get("data", {}).get("provider", "yfinance")

        lines = [
            "\U0001f916 *Bot Status*",
            "",
            f"Uptime: {uptime}",
            f"Commands processed: {self._commands_processed}",
            f"Data provider: {provider}",
            f"Confidence threshold: {threshold:.0%}",
            f"Watchlist: {len(watchlist)} symbol(s)",
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        self.send_message("\n".join(lines), chat_id=_chat_id)

    def _handle_help(self, *args, _chat_id: str = ""):
        """List all available commands."""
        text = (
            "\U0001f4d6 *AI Trading Bot \u2014 Commands*\n\n"
            "*Analysis:*\n"
            "  /analyze AAPL \u2014 Full analysis\n"
            "  /rsi AAPL \u2014 RSI + options guidance\n\n"
            "*Scanning:*\n"
            "  /scan \u2014 Full watchlist scan\n"
            "  /day \u2014 Day trade scan\n"
            "  /swing \u2014 Swing trade scan\n\n"
            "*Watchlist:*\n"
            "  /watchlist \u2014 Show watchlist\n"
            "  /add AAPL \u2014 Add to watchlist\n"
            "  /remove AAPL \u2014 Remove from watchlist\n\n"
            "*Portfolio:*\n"
            "  /portfolio \u2014 Open positions\n"
            "  /pnl \u2014 Today's P&L\n\n"
            "*Research:*\n"
            "  /sectors \u2014 Sector rotation\n"
            "  /sentiment AAPL \u2014 News sentiment\n"
            "  /calendar \u2014 Economic calendar\n"
            "  /risk AAPL 150 145 \u2014 Position size calc\n\n"
            "*Learning:*\n"
            "  /learn <url or notes> \u2014 Feed the bot content\n"
            "  /knowledge <query> \u2014 Search what the bot knows\n"
            "  /strats \u2014 Strategy performance stats\n\n"
            "*System:*\n"
            "  /status \u2014 Bot status\n"
            "  /help \u2014 This message\n\n"
            "_Not financial advice. You make your own decisions._"
        )
        self.send_message(text, chat_id=_chat_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_scan_summary(self, signals: list[Signal], title: str, chat_id: str):
        """Format and send a scan summary message."""
        buys = [s for s in signals if s.action == "BUY"]
        sells = [s for s in signals if s.action == "SELL"]

        lines = [f"\U0001f4e1 *{title} \u2014 {len(signals)} Signal(s)*", ""]

        day_signals = [s for s in signals if s.style == "day"]
        swing_signals = [s for s in signals if s.style == "swing"]
        other_signals = [s for s in signals if s.style not in ("day", "swing")]

        if day_signals:
            lines.append("*\u26a1 Day Trade:*")
            for s in day_signals:
                icon = "\u2705" if s.action == "BUY" else "\u274c"
                setup = f" [{s.setup}]" if s.setup else ""
                rr = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}){setup}{rr}")
            lines.append("")

        if swing_signals:
            lines.append("*\U0001f4c8 Swing Trade:*")
            for s in swing_signals:
                icon = "\u2705" if s.action == "BUY" else "\u274c"
                setup = f" [{s.setup}]" if s.setup else ""
                rr = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}){setup}{rr}")
            lines.append("")

        if other_signals:
            lines.append("*\U0001f4ca Other:*")
            for s in other_signals:
                icon = "\u2705" if s.action == "BUY" else "\u274c"
                lines.append(f"  {icon} {s.symbol} @ ${s.price:.2f} ({s.confidence:.0%}) \u2014 {s.strategy_name}")
            lines.append("")

        lines.append(f"*Total:* {len(buys)} BUY | {len(sells)} SELL")

        self.send_message("\n".join(lines), chat_id=chat_id)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_bot_instance: TelegramBot | None = None


def get_telegram_bot() -> TelegramBot:
    """Return the singleton TelegramBot instance."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TelegramBot()
    return _bot_instance


def start_telegram_bot():
    """Start the Telegram bot in a background thread. Called from main.py."""
    bot = get_telegram_bot()
    bot.start_polling()
    return bot
