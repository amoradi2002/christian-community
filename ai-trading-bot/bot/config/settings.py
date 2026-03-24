import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_config(config_path=None):
    if config_path is None:
        config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Overlay environment variables for secrets
    alerts = config.get("alerts", {})

    email_cfg = alerts.get("email", {})
    email_cfg["sender"] = os.getenv("SMTP_SENDER", email_cfg.get("sender", ""))
    email_cfg["password"] = os.getenv("SMTP_PASSWORD", email_cfg.get("password", ""))

    discord_cfg = alerts.get("discord", {})
    discord_cfg["webhook_url"] = os.getenv(
        "DISCORD_WEBHOOK_URL", discord_cfg.get("webhook_url", "")
    )

    telegram_cfg = alerts.get("telegram", {})
    telegram_cfg["bot_token"] = os.getenv(
        "TELEGRAM_BOT_TOKEN", telegram_cfg.get("bot_token", "")
    )
    telegram_cfg["chat_id"] = os.getenv(
        "TELEGRAM_CHAT_ID", telegram_cfg.get("chat_id", "")
    )

    # Ensure database path is absolute
    db_path = config.get("database", {}).get("path", "data/trading_bot.db")
    if not os.path.isabs(db_path):
        config["database"]["path"] = str(BASE_DIR / db_path)

    return config


CONFIG = load_config()
