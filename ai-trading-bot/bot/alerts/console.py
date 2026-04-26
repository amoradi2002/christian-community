from rich.console import Console
from rich.panel import Panel
from bot.alerts.base import AlertChannel
from bot.engine.signal import Signal

console = Console()

COLORS = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}


class ConsoleChannel(AlertChannel):
    def send(self, signal: Signal) -> bool:
        color = COLORS.get(signal.action, "white")
        reasons = "\n".join(f"  - {r}" for r in signal.reasons)

        panel = Panel(
            f"[bold {color}]{signal.action}[/] {signal.symbol} @ ${signal.price:.2f}\n"
            f"Confidence: {signal.confidence:.1%}\n"
            f"Strategy: {signal.strategy_name}\n"
            f"Reasons:\n{reasons}",
            title=f"[bold {color}]TRADING ALERT[/]",
            border_style=color,
        )
        console.print(panel)
        return True
