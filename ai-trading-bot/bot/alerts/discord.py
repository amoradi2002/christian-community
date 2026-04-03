import requests
from datetime import datetime
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG

# Colors by trade type for instant visual recognition
STYLE_COLORS = {
    "options": 0xFFD700,   # Gold — options calls
    "day": 0x00BFFF,      # Electric blue — day trades
    "swing": 0x9B59B6,    # Purple — swing trades
}
ACTION_COLORS = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00}

STYLE_LABELS = {
    "day": ":zap: DAY TRADE",
    "swing": ":chart_with_upwards_trend: SWING TRADE",
    "options": ":moneybag: OPTIONS CALL",
}
BROKER_LABELS = {
    "robinhood": "Execute on Robinhood",
    "interactive_brokers": "Execute on Interactive Brokers",
    "fidelity": "Execute on Fidelity",
    "alpaca": "Execute on Alpaca",
}


class DiscordChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        """Send a single trade call to Discord — labeled by type with full details."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        # Options get their own special format
        if signal.option_type or signal.style == "options":
            return self._send_options_call(signal, webhook_url)

        # Stock trade (day or swing)
        style = signal.style or "other"
        color = STYLE_COLORS.get(style, ACTION_COLORS.get(signal.action, 0xFFFFFF))
        style_label = STYLE_LABELS.get(style, ":bar_chart: TRADE ALERT")
        broker = BROKER_LABELS.get(signal.broker, "")

        fields = [
            {"name": "Action", "value": f"**{signal.action}**", "inline": True},
            {"name": "Entry", "value": f"${signal.price:.2f}", "inline": True},
            {"name": "Confidence", "value": f"{signal.confidence:.0%}", "inline": True},
        ]

        if signal.stop_loss:
            fields.append({"name": ":octagonal_sign: Stop Loss", "value": f"${signal.stop_loss:.2f}", "inline": True})
        if signal.target or signal.target_price:
            target = signal.target or signal.target_price
            fields.append({"name": ":dart: Target", "value": f"${target:.2f}", "inline": True})
        if signal.risk_reward:
            fields.append({"name": "R:R", "value": f"**{signal.risk_reward:.1f}:1**", "inline": True})
        if signal.setup:
            fields.append({"name": "Setup", "value": signal.setup, "inline": True})
        if signal.candle_pattern:
            fields.append({"name": "Pattern", "value": signal.candle_pattern, "inline": True})
        if signal.catalyst_tier:
            fields.append({"name": "Catalyst", "value": signal.catalyst_tier, "inline": True})

        reasons = "\n".join(f"- {r}" for r in signal.reasons)
        description = f"**Strategy:** {signal.strategy_name}"
        if reasons:
            description += f"\n\n**Why:**\n{reasons}"

        footer = "AI Trading Bot | Not financial advice"
        if broker:
            footer = f"{broker} | {footer}"

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": f"{style_label} — {signal.symbol}",
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": footer},
                "fields": fields,
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord alert failed: {e}")
            return False

    def _send_options_call(self, signal: Signal, webhook_url: str) -> bool:
        """Send an options-specific call to Discord with strike, expiry, premium."""
        opt_type = (signal.option_type or "call").upper()
        action_word = "BUY" if signal.action == "BUY" else "SELL"

        fields = [
            {"name": ":page_facing_up: Contract", "value": f"**{opt_type}**", "inline": True},
            {"name": ":dart: Strike", "value": f"${signal.strike:.2f}" if signal.strike else "ATM", "inline": True},
            {"name": ":calendar: Expiry", "value": signal.expiry or "TBD", "inline": True},
        ]

        if signal.premium:
            fields.append({"name": ":dollar: Premium", "value": f"${signal.premium:.2f}/contract", "inline": True})
        if signal.contracts:
            total = signal.premium * signal.contracts * 100 if signal.premium else 0
            fields.append({"name": "Contracts", "value": f"{signal.contracts} (${total:,.0f})", "inline": True})
        if signal.iv:
            fields.append({"name": "IV", "value": f"{signal.iv:.1f}%", "inline": True})
        if signal.delta:
            fields.append({"name": "Delta", "value": f"{signal.delta:.2f}", "inline": True})

        fields.append({"name": ":chart_with_upwards_trend: Stock Price", "value": f"${signal.price:.2f}", "inline": True})
        fields.append({"name": "Confidence", "value": f"**{signal.confidence:.0%}**", "inline": True})

        if signal.stop_loss:
            fields.append({"name": ":octagonal_sign: Stock Stop", "value": f"${signal.stop_loss:.2f}", "inline": True})
        if signal.target or signal.target_price:
            target = signal.target or signal.target_price
            fields.append({"name": ":dart: Stock Target", "value": f"${target:.2f}", "inline": True})
        if signal.risk_reward:
            fields.append({"name": "R:R", "value": f"**{signal.risk_reward:.1f}:1**", "inline": True})

        if signal.spread_type:
            legs = "\n".join(f"- {leg}" for leg in signal.spread_legs) if signal.spread_legs else signal.spread_type
            fields.append({"name": ":link: Spread", "value": f"**{signal.spread_type}**\n{legs}", "inline": False})

        reasons = "\n".join(f"- {r}" for r in signal.reasons)
        description = f"**Strategy:** {signal.strategy_name}"
        if signal.setup:
            description += f" | **Setup:** {signal.setup}"
        if reasons:
            description += f"\n\n**Why:**\n{reasons}"

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": f":moneybag: OPTIONS {action_word} — {signal.symbol} {opt_type} ${signal.strike:.0f}" if signal.strike else f":moneybag: OPTIONS {action_word} — {signal.symbol} {opt_type}",
                "description": description,
                "color": 0xFFD700,  # Gold for options
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Execute on Robinhood | AI Trading Bot | Not financial advice"},
                "fields": fields,
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord options alert failed: {e}")
            return False

    def send_summary(self, signals: list[Signal]) -> bool:
        """Send a summary of all signals from a scan — grouped by type."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url or not signals:
            return False

        buys = [s for s in signals if s.action == "BUY"]
        sells = [s for s in signals if s.action == "SELL"]

        # Group by style
        options_signals = [s for s in signals if s.style == "options" or s.option_type]
        day_signals = [s for s in signals if s.style == "day" and not s.option_type]
        swing_signals = [s for s in signals if s.style == "swing" and not s.option_type]
        other_signals = [s for s in signals if s.style not in ("day", "swing", "options") and not s.option_type]

        lines = []

        if options_signals:
            lines.append("**:moneybag: OPTIONS CALLS (Robinhood):**")
            for s in options_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                opt = (s.option_type or "call").upper()
                strike = f" ${s.strike:.0f}" if s.strike else ""
                exp = f" {s.expiry}" if s.expiry else ""
                prem = f" @ ${s.premium:.2f}" if s.premium else ""
                lines.append(f"  {icon} **{s.symbol}** {opt}{strike}{exp}{prem} ({s.confidence:.0%})")
            lines.append("")

        if day_signals:
            lines.append("**:zap: DAY TRADES (Interactive Brokers):**")
            for s in day_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                setup_info = f" [{s.setup}]" if s.setup else ""
                rr_info = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                stop = f" Stop: ${s.stop_loss:.2f}" if s.stop_loss else ""
                tgt = f" Target: ${s.target or s.target_price:.2f}" if (s.target or s.target_price) else ""
                lines.append(f"  {icon} **{s.symbol}** {s.action} @ ${s.price:.2f}{setup_info}{rr_info}{stop}{tgt}")
            lines.append("")

        if swing_signals:
            lines.append("**:chart_with_upwards_trend: SWING TRADES (Fidelity):**")
            for s in swing_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                setup_info = f" [{s.setup}]" if s.setup else ""
                rr_info = f" R:R {s.risk_reward:.1f}:1" if s.risk_reward else ""
                stop = f" Stop: ${s.stop_loss:.2f}" if s.stop_loss else ""
                tgt = f" Target: ${s.target or s.target_price:.2f}" if (s.target or s.target_price) else ""
                lines.append(f"  {icon} **{s.symbol}** {s.action} @ ${s.price:.2f}{setup_info}{rr_info}{stop}{tgt}")
            lines.append("")

        if other_signals:
            lines.append("**:bar_chart: OTHER:**")
            for s in other_signals:
                icon = ":green_circle:" if s.action == "BUY" else ":red_circle:"
                lines.append(f"  {icon} **{s.symbol}** @ ${s.price:.2f} ({s.confidence:.0%}) — {s.strategy_name}")
            lines.append("")

        lines.append(f"**Total:** {len(buys)} BUY | {len(sells)} SELL")
        lines.append(f"Options: {len(options_signals)} | Day: {len(day_signals)} | Swing: {len(swing_signals)}")

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": f":loudspeaker: TRADE CALLS — {len(signals)} Signal(s)",
                "description": "\n".join(lines),
                "color": 0x58a6ff,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Not financial advice | You make your own decisions"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord summary failed: {e}")
            return False

    def send_sector_report(self, report: dict) -> bool:
        """Send sector rotation report to Discord."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        regime_icons = {"risk-on": ":rocket:", "risk-off": ":shield:", "mixed": ":scales:"}
        icon = regime_icons.get(report.get("market_regime", ""), ":bar_chart:")

        lines = [f"**Market Regime:** {icon} {report.get('market_regime', 'unknown').title()}"]
        lines.append("")

        top = report.get("top_sectors", [])
        bottom = report.get("bottom_sectors", [])

        if top:
            lines.append("**Leading Sectors:**")
            for s in report.get("sectors", [])[:3]:
                lines.append(f"  :arrow_up: {s['symbol']} ({s['name']}) {s['relative_to_spy']:+.1f}% vs SPY")
        if bottom:
            lines.append("**Lagging Sectors:**")
            for s in report.get("sectors", [])[-3:]:
                lines.append(f"  :arrow_down: {s['symbol']} ({s['name']}) {s['relative_to_spy']:+.1f}% vs SPY")

        lines.append("")
        lines.append(f"**Recommendation:** {report.get('recommendation', '')}")

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": "Sector Rotation Report",
                "description": "\n".join(lines),
                "color": 0x9b59b6,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Weekly sector analysis"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord sector report failed: {e}")
            return False

    def send_journal_review(self, review: dict) -> bool:
        """Send weekly trade journal review to Discord."""
        cfg = CONFIG.get("alerts", {}).get("discord", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return False

        lines = [f"**Week:** {review.get('week', '')}"]
        lines.append(f"**Total Trades:** {review.get('total_trades', 0)}")
        lines.append(f"**Win Rate:** {review.get('win_rate', 0):.1f}%")
        lines.append(f"**Total P&L:** ${review.get('total_pnl', 0):.2f}")
        lines.append(f"**Avg R Winner:** {review.get('avg_r_winner', 0):+.2f}R")
        lines.append(f"**Avg R Loser:** {review.get('avg_r_loser', 0):+.2f}R")
        lines.append(f"**Process Score:** {review.get('avg_process_score', 0):.1f}/5")

        best = review.get("best_trade")
        worst = review.get("worst_trade")
        if best:
            lines.append(f"\n**Best Trade:** {best['symbol']} ${best['pnl_dollars']:+.2f} ({best.get('setup', '')})")
        if worst:
            lines.append(f"**Worst Trade:** {worst['symbol']} ${worst['pnl_dollars']:+.2f} ({worst.get('setup', '')})")

        rules = review.get("rules_broken", [])
        if rules:
            lines.append("\n**Rules Broken:**")
            for r in rules:
                lines.append(f"  :warning: {r}")

        color = 0x00FF00 if review.get("total_pnl", 0) >= 0 else 0xFF0000

        payload = {
            "username": "AI Trading Bot",
            "embeds": [{
                "title": "Weekly Trade Journal Review",
                "description": "\n".join(lines),
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI Trading Bot | Review your process, not just results"},
            }]
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Discord journal review failed: {e}")
            return False
