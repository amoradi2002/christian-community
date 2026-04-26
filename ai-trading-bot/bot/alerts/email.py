import smtplib
from email.mime.text import MIMEText
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal
from bot.config.settings import CONFIG


class EmailChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        cfg = CONFIG.get("alerts", {}).get("email", {})
        sender = cfg.get("sender", "")
        password = cfg.get("password", "")
        recipients = cfg.get("recipients", [])
        host = cfg.get("smtp_host", "smtp.gmail.com")
        port = cfg.get("smtp_port", 587)

        if not sender or not password or not recipients:
            return False

        reasons = "\n".join(f"  - {r}" for r in signal.reasons)
        body = (
            f"Trading Alert: {signal.action} {signal.symbol}\n\n"
            f"Price: ${signal.price:.2f}\n"
            f"Confidence: {signal.confidence:.1%}\n"
            f"Strategy: {signal.strategy_name}\n\n"
            f"Reasons:\n{reasons}"
        )

        msg = MIMEText(body)
        msg["Subject"] = f"[Trading Bot] {signal.action} {signal.symbol} @ ${signal.price:.2f}"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        try:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, recipients, msg.as_string())
            return True
        except Exception as e:
            print(f"Email alert failed: {e}")
            return False
