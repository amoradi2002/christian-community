"""
Email Digest - Weekly and daily trading summaries via Gmail SMTP.

Sends professionally formatted HTML emails with:
- Weekly digest (Sunday 6PM ET): journal review, strategy performance,
  P&L summary, sector rotation, best/worst trades, upcoming events.
- Daily summary (4:30PM ET): today's signals, trades taken, P&L,
  tomorrow's watchlist.

Requires env vars: SMTP_SENDER, SMTP_PASSWORD, SMTP_RECIPIENT (optional,
defaults to sender).
"""

import os
import smtplib
import threading
import time
import tempfile
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from bot.config.settings import CONFIG

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Color palette for HTML emails
_COLORS = {
    "green": "#22c55e",
    "red": "#ef4444",
    "yellow": "#eab308",
    "blue": "#3b82f6",
    "purple": "#a855f7",
    "gray": "#6b7280",
    "bg": "#1e1e2e",
    "card_bg": "#2a2a3e",
    "text": "#e2e8f0",
    "text_muted": "#94a3b8",
    "border": "#3f3f5e",
    "header_bg": "#0f172a",
}


# ---------------------------------------------------------------------------
# EmailDigest
# ---------------------------------------------------------------------------

class EmailDigest:
    """Compile and send weekly/daily trading digest emails."""

    def __init__(self):
        email_cfg = CONFIG.get("alerts", {}).get("email", {})
        self.sender = email_cfg.get("sender", "") or os.getenv("SMTP_SENDER", "")
        self.password = email_cfg.get("password", "") or os.getenv("SMTP_PASSWORD", "")
        self.recipient = os.getenv("SMTP_RECIPIENT", "") or self.sender
        self.smtp_host = email_cfg.get("smtp_host", SMTP_HOST)
        self.smtp_port = email_cfg.get("smtp_port", SMTP_PORT)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_weekly_digest(self):
        """Compile and send the weekly trading digest email with PDF attachment.

        Includes: journal review, strategy performance, P&L summary,
        sector rotation, best/worst trades, upcoming events.
        """
        data = self._gather_weekly_data()
        subject = f"Weekly Trading Digest \u2014 {data['week_label']}"
        html = self._build_weekly_html(data)
        pdf = self._generate_pdf(data, report_type="weekly")
        filename = f"weekly_digest_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return self._send_email(subject, html, pdf_bytes=pdf, pdf_filename=filename)

    def send_daily_summary(self):
        """Send the end-of-day summary email with PDF attachment.

        Includes: today's signals, trades taken, P&L, tomorrow's watchlist.
        """
        data = self._gather_daily_data()
        today_str = datetime.now().strftime("%A %b %d, %Y")
        subject = f"Daily Trading Summary \u2014 {today_str}"
        html = self._build_daily_html(data)
        pdf = self._generate_pdf(data, report_type="daily")
        filename = f"daily_summary_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return self._send_email(subject, html, pdf_bytes=pdf, pdf_filename=filename)

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------

    def _gather_weekly_data(self) -> dict:
        """Pull data from various modules for the weekly digest."""
        data: dict = {
            "week_label": "",
            "journal_review": {},
            "strategy_stats": {},
            "best_strategies": [],
            "worst_strategies": [],
            "pnl_summary": {},
            "sector_report": None,
            "watchlist": [],
        }

        now = datetime.now()
        week_start = (now - timedelta(days=now.weekday())).strftime("%b %d")
        week_end = now.strftime("%b %d, %Y")
        data["week_label"] = f"{week_start} \u2013 {week_end}"

        # Journal review
        try:
            from bot.engine.trade_journal import weekly_review
            data["journal_review"] = weekly_review(weeks_ago=0)
        except Exception as exc:
            data["journal_review"] = {"error": str(exc)}

        # Strategy stats
        try:
            from bot.engine.strategy_tracker import get_strategy_stats, get_best_strategies, get_worst_strategies
            data["strategy_stats"] = get_strategy_stats()
            data["best_strategies"] = get_best_strategies(5)
            data["worst_strategies"] = get_worst_strategies(5)
        except Exception as exc:
            data["strategy_stats"] = {"error": str(exc)}

        # P&L summary (last 7 days)
        try:
            from bot.engine.daily_pnl import DailyPnLTracker
            tracker = DailyPnLTracker()
            data["pnl_summary"] = tracker.get_today_pnl()
        except Exception as exc:
            data["pnl_summary"] = {"error": str(exc)}

        # Watchlist
        data["watchlist"] = CONFIG.get("bot", {}).get("watchlist", [])

        return data

    def _gather_daily_data(self) -> dict:
        """Pull data from various modules for the daily summary."""
        data: dict = {
            "date_label": datetime.now().strftime("%A %b %d, %Y"),
            "pnl": {},
            "open_positions": [],
            "watchlist": [],
        }

        # Today's P&L
        try:
            from bot.engine.daily_pnl import DailyPnLTracker
            tracker = DailyPnLTracker()
            data["pnl"] = tracker.get_today_pnl()
        except Exception as exc:
            data["pnl"] = {"error": str(exc)}

        # Open positions
        try:
            from bot.engine.paper_trader import PaperTrader
            trader = PaperTrader()
            data["open_positions"] = trader.get_open_positions()
        except Exception as exc:
            data["open_positions"] = []

        # Watchlist
        data["watchlist"] = CONFIG.get("bot", {}).get("watchlist", [])

        return data

    # ------------------------------------------------------------------
    # HTML builders
    # ------------------------------------------------------------------

    def _build_weekly_html(self, data: dict) -> str:
        """Build a full HTML email body for the weekly digest."""
        review = data.get("journal_review", {})
        stats = data.get("strategy_stats", {})
        best = data.get("best_strategies", [])
        worst = data.get("worst_strategies", [])
        pnl = data.get("pnl_summary", {})
        watchlist = data.get("watchlist", [])
        week_label = data.get("week_label", "")

        total_pnl = review.get("total_pnl", pnl.get("total_pnl", 0))
        pnl_color = _COLORS["green"] if total_pnl >= 0 else _COLORS["red"]

        sections = []

        # --- Header ---
        sections.append(self._html_section_header("Weekly Trading Digest", week_label))

        # --- P&L Summary Card ---
        win_rate = review.get("win_rate", 0)
        total_trades = review.get("total_trades", 0)
        avg_r_winner = review.get("avg_r_winner", 0)
        avg_r_loser = review.get("avg_r_loser", 0)
        process_score = review.get("avg_process_score", 0)

        pnl_rows = [
            ("Net P&L", f"${total_pnl:+,.2f}", pnl_color),
            ("Total Trades", str(total_trades), _COLORS["text"]),
            ("Win Rate", f"{win_rate:.1f}%", _COLORS["green"] if win_rate >= 50 else _COLORS["red"]),
            ("Avg R (Winners)", f"{avg_r_winner:+.2f}R", _COLORS["green"]),
            ("Avg R (Losers)", f"{avg_r_loser:+.2f}R", _COLORS["red"]),
            ("Process Score", f"{process_score:.1f}/5", _COLORS["blue"]),
        ]
        sections.append(self._html_kv_card("Performance Summary", pnl_rows))

        # --- Best / Worst Trades ---
        best_trade = review.get("best_trade")
        worst_trade = review.get("worst_trade")
        if best_trade or worst_trade:
            trade_rows = []
            if best_trade:
                trade_rows.append((
                    f"Best: {best_trade.get('symbol', '?')}",
                    f"${best_trade.get('pnl_dollars', 0):+,.2f} ({best_trade.get('setup', '')})",
                    _COLORS["green"],
                ))
            if worst_trade:
                trade_rows.append((
                    f"Worst: {worst_trade.get('symbol', '?')}",
                    f"${worst_trade.get('pnl_dollars', 0):+,.2f} ({worst_trade.get('setup', '')})",
                    _COLORS["red"],
                ))
            sections.append(self._html_kv_card("Notable Trades", trade_rows))

        # --- Strategy Performance Table ---
        if best or worst:
            strat_html = self._html_strategy_table(best, worst)
            sections.append(self._html_card("Strategy Performance", strat_html))

        # --- Rules Broken ---
        rules = review.get("rules_broken", [])
        if rules:
            items = "".join(f'<li style="color:{_COLORS["yellow"]};margin:4px 0;">{r}</li>' for r in rules)
            sections.append(self._html_card("Rules Broken", f"<ul style='margin:0;padding-left:20px;'>{items}</ul>"))

        # --- Watchlist ---
        if watchlist:
            wl_text = ", ".join(f"<code>{s}</code>" for s in watchlist)
            sections.append(self._html_card("Watchlist", f"<p style='margin:0;'>{wl_text}</p>"))

        return self._html_wrapper("Weekly Trading Digest", "\n".join(sections))

    def _build_daily_html(self, data: dict) -> str:
        """Build a full HTML email body for the daily summary."""
        pnl = data.get("pnl", {})
        positions = data.get("open_positions", [])
        watchlist = data.get("watchlist", [])
        date_label = data.get("date_label", "")

        total_pnl = pnl.get("total_pnl", 0)
        pnl_color = _COLORS["green"] if total_pnl >= 0 else _COLORS["red"]

        sections = []

        # --- Header ---
        sections.append(self._html_section_header("Daily Trading Summary", date_label))

        # --- P&L Card ---
        trade_count = pnl.get("trade_count", 0)
        winners = pnl.get("winners", 0)
        losers = pnl.get("losers", 0)
        locked = pnl.get("is_locked_out", False)

        pnl_rows = [
            ("Net P&L", f"${total_pnl:+,.2f}", pnl_color),
            ("Trades", f"{trade_count} ({winners}W / {losers}L)", _COLORS["text"]),
        ]
        if locked:
            pnl_rows.append(("Status", "LOCKED OUT", _COLORS["red"]))

        sections.append(self._html_kv_card("Today's P&L", pnl_rows))

        # --- Per-symbol breakdown ---
        by_symbol = pnl.get("pnl_by_symbol", {})
        if by_symbol:
            rows_html = ""
            for sym, amt in sorted(by_symbol.items(), key=lambda x: x[1], reverse=True):
                color = _COLORS["green"] if amt >= 0 else _COLORS["red"]
                rows_html += f"""
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};">
                        <code>{sym}</code>
                    </td>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};
                               color:{color};text-align:right;font-weight:bold;">
                        ${amt:+,.2f}
                    </td>
                </tr>"""
            table = f"""
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:{_COLORS['header_bg']};">
                        <th style="padding:8px 12px;text-align:left;color:{_COLORS['text_muted']};
                                   font-size:12px;text-transform:uppercase;">Symbol</th>
                        <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                                   font-size:12px;text-transform:uppercase;">P&L</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>"""
            sections.append(self._html_card("P&L by Symbol", table))

        # --- Open Positions ---
        if positions:
            pos_rows = ""
            for pos in positions:
                sym = pos.get("symbol", "?")
                qty = pos.get("quantity", 0)
                entry = pos.get("entry_price", 0)
                sl = pos.get("stop_loss", 0)
                tp = pos.get("target_price", 0)
                sl_display = f"${sl:.2f}" if sl else "\u2014"
                tp_display = f"${tp:.2f}" if tp else "\u2014"
                pos_rows += f"""
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};">
                        <strong>{sym}</strong>
                    </td>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};text-align:center;">
                        {qty}
                    </td>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};text-align:right;">
                        ${entry:.2f}
                    </td>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};text-align:right;
                               color:{_COLORS['red']};">
                        {sl_display}
                    </td>
                    <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};text-align:right;
                               color:{_COLORS['green']};">
                        {tp_display}
                    </td>
                </tr>"""
            pos_table = f"""
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:{_COLORS['header_bg']};">
                        <th style="padding:8px 12px;text-align:left;color:{_COLORS['text_muted']};
                                   font-size:12px;">SYMBOL</th>
                        <th style="padding:8px 12px;text-align:center;color:{_COLORS['text_muted']};
                                   font-size:12px;">QTY</th>
                        <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                                   font-size:12px;">ENTRY</th>
                        <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                                   font-size:12px;">STOP</th>
                        <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                                   font-size:12px;">TARGET</th>
                    </tr>
                </thead>
                <tbody>{pos_rows}</tbody>
            </table>"""
            sections.append(self._html_card("Open Positions", pos_table))

        # --- Watchlist ---
        if watchlist:
            wl_text = ", ".join(f"<code>{s}</code>" for s in watchlist)
            sections.append(self._html_card("Tomorrow's Watchlist", f"<p style='margin:0;'>{wl_text}</p>"))

        return self._html_wrapper("Daily Trading Summary", "\n".join(sections))

    # ------------------------------------------------------------------
    # HTML primitives
    # ------------------------------------------------------------------

    def _html_wrapper(self, title: str, body_content: str) -> str:
        """Wrap section content in a full HTML document with dark-theme styling."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{_COLORS['bg']};font-family:
    -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
    color:{_COLORS['text']};line-height:1.6;">
    <div style="max-width:640px;margin:0 auto;padding:20px;">
        {body_content}
        <div style="text-align:center;padding:24px 0 12px;color:{_COLORS['text_muted']};font-size:12px;">
            AI Trading Bot &mdash; Not financial advice. You make your own decisions.
        </div>
    </div>
</body>
</html>"""

    def _html_section_header(self, title: str, subtitle: str) -> str:
        """Render a top header banner."""
        return f"""
        <div style="background:linear-gradient(135deg,{_COLORS['header_bg']},{_COLORS['card_bg']});
                    border-radius:12px;padding:24px;margin-bottom:20px;text-align:center;
                    border:1px solid {_COLORS['border']};">
            <h1 style="margin:0 0 4px;font-size:22px;color:{_COLORS['text']};">
                {title}
            </h1>
            <p style="margin:0;color:{_COLORS['text_muted']};font-size:14px;">{subtitle}</p>
        </div>"""

    def _html_card(self, title: str, inner_html: str) -> str:
        """Render a card with a title and arbitrary inner HTML."""
        return f"""
        <div style="background:{_COLORS['card_bg']};border-radius:10px;padding:16px 20px;
                    margin-bottom:16px;border:1px solid {_COLORS['border']};">
            <h2 style="margin:0 0 12px;font-size:16px;color:{_COLORS['blue']};">{title}</h2>
            {inner_html}
        </div>"""

    def _html_kv_card(self, title: str, rows: list[tuple[str, str, str]]) -> str:
        """Render a card with key-value rows.

        Each row is (label, value, value_color).
        """
        row_html = ""
        for label, value, color in rows:
            row_html += f"""
            <tr>
                <td style="padding:6px 0;color:{_COLORS['text_muted']};font-size:14px;">{label}</td>
                <td style="padding:6px 0;text-align:right;font-weight:bold;font-size:14px;
                           color:{color};">{value}</td>
            </tr>"""

        return self._html_card(title, f"""
            <table style="width:100%;border-collapse:collapse;">{row_html}</table>""")

    def _html_strategy_table(self, best: list[dict], worst: list[dict]) -> str:
        """Build an HTML table showing best and worst strategies."""
        rows = ""

        for strat in best:
            name = strat.get("strategy_name", strat.get("name", "?"))
            win_rate = strat.get("win_rate", 0)
            pnl = strat.get("total_pnl", strat.get("pnl_dollars", 0))
            trades = strat.get("total_trades", strat.get("trades", 0))
            color = _COLORS["green"]
            rows += self._html_strategy_row(name, win_rate, pnl, trades, color)

        for strat in worst:
            name = strat.get("strategy_name", strat.get("name", "?"))
            win_rate = strat.get("win_rate", 0)
            pnl = strat.get("total_pnl", strat.get("pnl_dollars", 0))
            trades = strat.get("total_trades", strat.get("trades", 0))
            color = _COLORS["red"]
            rows += self._html_strategy_row(name, win_rate, pnl, trades, color)

        return f"""
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:{_COLORS['header_bg']};">
                    <th style="padding:8px 12px;text-align:left;color:{_COLORS['text_muted']};
                               font-size:12px;text-transform:uppercase;">Strategy</th>
                    <th style="padding:8px 12px;text-align:center;color:{_COLORS['text_muted']};
                               font-size:12px;text-transform:uppercase;">Win Rate</th>
                    <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                               font-size:12px;text-transform:uppercase;">P&L</th>
                    <th style="padding:8px 12px;text-align:right;color:{_COLORS['text_muted']};
                               font-size:12px;text-transform:uppercase;">Trades</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>"""

    def _html_strategy_row(self, name: str, win_rate: float, pnl: float,
                           trades: int, color: str) -> str:
        """Render a single strategy row in the performance table."""
        pnl_color = _COLORS["green"] if pnl >= 0 else _COLORS["red"]
        wr_color = _COLORS["green"] if win_rate >= 50 else _COLORS["red"]
        return f"""
        <tr>
            <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};
                       font-weight:bold;">{name}</td>
            <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};
                       text-align:center;color:{wr_color};">{win_rate:.1f}%</td>
            <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};
                       text-align:right;color:{pnl_color};font-weight:bold;">${pnl:+,.2f}</td>
            <td style="padding:6px 12px;border-bottom:1px solid {_COLORS['border']};
                       text-align:right;color:{_COLORS['text_muted']};">{trades}</td>
        </tr>"""

    # ------------------------------------------------------------------
    # PDF generation
    # ------------------------------------------------------------------

    def _generate_pdf(self, data: dict, report_type: str = "daily") -> bytes:
        """Generate a clean, organized PDF report.

        Returns PDF bytes or None if generation fails.
        Uses only stdlib (no external PDF lib) by building a minimal PDF.
        """
        try:
            lines = []
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            if report_type == "weekly":
                lines.append("=" * 60)
                lines.append(f"  WEEKLY TRADING DIGEST")
                lines.append(f"  {data.get('week_label', '')}")
                lines.append(f"  Generated: {now_str}")
                lines.append("=" * 60)
                lines.append("")

                review = data.get("journal_review", {})
                lines.append("PERFORMANCE SUMMARY")
                lines.append("-" * 40)
                lines.append(f"  Net P&L:         ${review.get('total_pnl', 0):+,.2f}")
                lines.append(f"  Total Trades:    {review.get('total_trades', 0)}")
                lines.append(f"  Win Rate:        {review.get('win_rate', 0):.1f}%")
                lines.append(f"  Winners:         {review.get('winners', 0)}")
                lines.append(f"  Losers:          {review.get('losers', 0)}")
                lines.append(f"  Avg R (Winners): {review.get('avg_r_winner', 0):+.2f}R")
                lines.append(f"  Avg R (Losers):  {review.get('avg_r_loser', 0):+.2f}R")
                lines.append(f"  Process Score:   {review.get('avg_process_score', 0):.1f}/5")
                lines.append("")

                best = review.get("best_trade")
                worst = review.get("worst_trade")
                if best or worst:
                    lines.append("NOTABLE TRADES")
                    lines.append("-" * 40)
                    if best:
                        lines.append(f"  Best:  {best.get('symbol', '?')} ${best.get('pnl_dollars', 0):+,.2f} ({best.get('setup', '')})")
                    if worst:
                        lines.append(f"  Worst: {worst.get('symbol', '?')} ${worst.get('pnl_dollars', 0):+,.2f} ({worst.get('setup', '')})")
                    lines.append("")

                stats = data.get("strategy_stats", {})
                if stats and not isinstance(stats, dict) or (isinstance(stats, dict) and "error" not in stats):
                    lines.append("STRATEGY PERFORMANCE")
                    lines.append("-" * 60)
                    lines.append(f"  {'Strategy':<25s} {'Signals':>8s} {'WR':>6s} {'Avg R':>7s} {'P&L':>10s}")
                    lines.append(f"  {'-'*25} {'-'*8} {'-'*6} {'-'*7} {'-'*10}")
                    if isinstance(stats, dict):
                        for name, s in sorted(stats.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True):
                            lines.append(f"  {name:<25s} {s.get('total_signals', 0):>8d} {s.get('win_rate', 0):>5.0f}% {s.get('avg_r', 0):>+6.2f} ${s.get('total_pnl', 0):>+9.2f}")
                    lines.append("")

                rules = review.get("rules_broken", [])
                if rules:
                    lines.append("RULES BROKEN")
                    lines.append("-" * 40)
                    for r in rules:
                        lines.append(f"  ! {r}")
                    lines.append("")

                by_style = review.get("by_style", {})
                if by_style:
                    lines.append("TRADES BY STYLE")
                    lines.append("-" * 40)
                    lines.append(f"  Day:     {by_style.get('day', 0)}")
                    lines.append(f"  Swing:   {by_style.get('swing', 0)}")
                    lines.append(f"  Options: {by_style.get('options', 0)}")
                    lines.append("")

            else:  # daily
                lines.append("=" * 60)
                lines.append(f"  DAILY TRADING SUMMARY")
                lines.append(f"  {data.get('date_label', '')}")
                lines.append(f"  Generated: {now_str}")
                lines.append("=" * 60)
                lines.append("")

                pnl = data.get("pnl", {})
                lines.append("TODAY'S P&L")
                lines.append("-" * 40)
                lines.append(f"  Net P&L:  ${pnl.get('total_pnl', 0):+,.2f}")
                lines.append(f"  Trades:   {pnl.get('trade_count', 0)} ({pnl.get('winners', 0)}W / {pnl.get('losers', 0)}L)")
                if pnl.get("is_locked_out"):
                    lines.append(f"  STATUS:   LOCKED OUT (daily loss limit hit)")
                lines.append("")

                by_symbol = pnl.get("pnl_by_symbol", {})
                if by_symbol:
                    lines.append("P&L BY SYMBOL")
                    lines.append("-" * 40)
                    for sym, amt in sorted(by_symbol.items(), key=lambda x: x[1], reverse=True):
                        lines.append(f"  {sym:<8s} ${amt:+,.2f}")
                    lines.append("")

                positions = data.get("open_positions", [])
                if positions:
                    lines.append("OPEN POSITIONS")
                    lines.append("-" * 60)
                    lines.append(f"  {'Symbol':<8s} {'Qty':>5s} {'Entry':>10s} {'Stop':>10s} {'Target':>10s}")
                    lines.append(f"  {'-'*8} {'-'*5} {'-'*10} {'-'*10} {'-'*10}")
                    for p in positions:
                        sl = f"${p.get('stop_loss', 0):.2f}" if p.get('stop_loss') else "---"
                        tp = f"${p.get('target_price', 0):.2f}" if p.get('target_price') else "---"
                        lines.append(f"  {p.get('symbol', '?'):<8s} {p.get('quantity', 0):>5d} ${p.get('entry_price', 0):>9.2f} {sl:>10s} {tp:>10s}")
                    lines.append("")

            # Watchlist
            watchlist = data.get("watchlist", [])
            if watchlist:
                lines.append("WATCHLIST")
                lines.append("-" * 40)
                lines.append(f"  {', '.join(watchlist)}")
                lines.append("")

            lines.append("=" * 60)
            lines.append("  AI Trading Bot - Not financial advice")
            lines.append("=" * 60)

            text_content = "\n".join(lines)

            # Build a minimal PDF from the text
            return self._text_to_pdf(text_content)

        except Exception as exc:
            print(f"PDF generation error: {exc}")
            return None

    def _text_to_pdf(self, text: str) -> bytes:
        """Convert plain text to a basic PDF using only stdlib.

        Creates a valid PDF 1.4 document with monospace font.
        """
        # Escape special PDF characters
        def _esc(s):
            return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        page_width = 612   # US Letter
        page_height = 792
        margin = 50
        font_size = 9
        line_height = 12
        usable_height = page_height - 2 * margin
        lines_per_page = int(usable_height / line_height)

        all_lines = text.split("\n")

        # Split into pages
        pages_text = []
        for i in range(0, len(all_lines), lines_per_page):
            pages_text.append(all_lines[i:i + lines_per_page])

        objects = []
        obj_offsets = []

        def add_obj(content):
            objects.append(content)
            return len(objects)

        # Object 1: Catalog
        add_obj("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")

        # Object 2: Pages (placeholder, updated later)
        pages_obj_idx = add_obj("")  # will be replaced

        # Object 3: Font
        add_obj("3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj")

        # Build page objects
        page_refs = []
        for page_lines in pages_text:
            # Build text stream
            stream_lines = [
                f"BT",
                f"/F1 {font_size} Tf",
                f"{margin} {page_height - margin} Td",
                f"{line_height} TL",
            ]
            for line in page_lines:
                stream_lines.append(f"({_esc(line)}) Tj T*")
            stream_lines.append("ET")
            stream = "\n".join(stream_lines)

            # Content stream object
            stream_obj = add_obj(
                f"{len(objects)} 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj"
            )
            # Fix the object number in the content
            objects[-1] = f"{stream_obj} 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj"

            # Page object
            page_obj = add_obj("")
            objects[-1] = (
                f"{page_obj} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {page_width} {page_height}] "
                f"/Contents {stream_obj} 0 R "
                f"/Resources << /Font << /F1 3 0 R >> >> >>\n"
                f"endobj"
            )
            page_refs.append(f"{page_obj} 0 R")

        # Update Pages object
        kids = " ".join(page_refs)
        objects[pages_obj_idx - 1] = (
            f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(pages_text)} >>\nendobj"
        )

        # Build PDF bytes
        pdf_parts = ["%PDF-1.4\n"]
        for i, obj in enumerate(objects):
            obj_offsets.append(len("".join(pdf_parts)))
            pdf_parts.append(obj + "\n")

        # Cross-reference table
        xref_offset = len("".join(pdf_parts))
        pdf_parts.append("xref\n")
        pdf_parts.append(f"0 {len(objects) + 1}\n")
        pdf_parts.append("0000000000 65535 f \n")
        for offset in obj_offsets:
            pdf_parts.append(f"{offset:010d} 00000 n \n")

        # Trailer
        pdf_parts.append("trailer\n")
        pdf_parts.append(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n")
        pdf_parts.append("startxref\n")
        pdf_parts.append(f"{xref_offset}\n")
        pdf_parts.append("%%EOF\n")

        return "".join(pdf_parts).encode("latin-1")

    # ------------------------------------------------------------------
    # Email sending
    # ------------------------------------------------------------------

    def _send_email(self, subject: str, html_body: str,
                    pdf_bytes: bytes = None, pdf_filename: str = None) -> bool:
        """Send an HTML email via SMTP (Gmail) with optional PDF attachment."""
        if not self.sender or not self.password:
            print("Email digest: SMTP credentials not configured.")
            return False

        recipient = self.recipient or self.sender

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"AI Trading Bot <{self.sender}>"
        msg["To"] = recipient

        # HTML + plain text alternative part
        alt_part = MIMEMultipart("alternative")
        plain = (
            f"{subject}\n\n"
            "This email is best viewed in an HTML-capable email client.\n"
            "A PDF report is attached for your records.\n\n"
            "AI Trading Bot \u2014 Not financial advice."
        )
        alt_part.attach(MIMEText(plain, "plain"))
        alt_part.attach(MIMEText(html_body, "html"))
        msg.attach(alt_part)

        # Attach PDF if generated
        if pdf_bytes and pdf_filename:
            pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            pdf_attachment.add_header(
                "Content-Disposition", "attachment", filename=pdf_filename
            )
            msg.attach(pdf_attachment)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, [recipient], msg.as_string())
            print(f"Email digest sent: {subject} (PDF: {pdf_filename or 'none'})")
            return True
        except Exception as exc:
            print(f"Email digest failed: {exc}")
            return False


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _is_target_time(target_hour: int, target_minute: int, tolerance_seconds: int = 60) -> bool:
    """Check if the current time is within tolerance of target HH:MM."""
    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    return abs((now - target).total_seconds()) < tolerance_seconds


def _schedule_loop():
    """Background loop that checks the clock and fires emails at the right times.

    Schedule (Eastern Time):
        - Daily summary:  4:30 PM ET (16:30) weekdays
        - Weekly digest:  6:00 PM ET (18:00) Sunday
    """
    digest = EmailDigest()
    daily_sent_today = False
    weekly_sent_this_week = False
    last_day = datetime.now().date()

    while True:
        now = datetime.now()

        # Reset flags at midnight
        if now.date() != last_day:
            daily_sent_today = False
            last_day = now.date()
            # Reset weekly flag on Monday
            if now.weekday() == 0:
                weekly_sent_this_week = False

        # Daily summary at 4:30 PM on weekdays (Mon-Fri)
        if now.weekday() < 5 and not daily_sent_today:
            if _is_target_time(16, 30):
                try:
                    digest.send_daily_summary()
                    daily_sent_today = True
                except Exception as exc:
                    print(f"Daily email error: {exc}")

        # Weekly digest at 6:00 PM on Sunday
        if now.weekday() == 6 and not weekly_sent_this_week:
            if _is_target_time(18, 0):
                try:
                    digest.send_weekly_digest()
                    weekly_sent_this_week = True
                except Exception as exc:
                    print(f"Weekly email error: {exc}")

        # Check every 30 seconds
        time.sleep(30)


def schedule_email_digest():
    """Schedule weekly digest for Sunday 6PM and daily summary for 4:30PM ET.

    Runs the scheduler in a background daemon thread.
    """
    thread = threading.Thread(target=_schedule_loop, daemon=True, name="email-digest-scheduler")
    thread.start()
    print("Email digest scheduler started (daily 4:30PM, weekly Sunday 6PM).")
    return thread
