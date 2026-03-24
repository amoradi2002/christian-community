"""
AI Trading Bot - Main Entry Point

Usage:
    python -m bot.main              # Start bot (scan + dashboard)
    python -m bot.main scan         # Run a single scan
    python -m bot.main train        # Train the AI model
    python -m bot.main dashboard    # Start dashboard only
"""

import sys
import threading
import schedule
import time

from bot.db.database import init_db
from bot.config.settings import CONFIG


def run_scan():
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    return analyzer.run_scan()


def run_train():
    from bot.ai.trainer import train_model
    print("Training AI model...")
    result = train_model()
    if result:
        print("Training complete!")
    else:
        print("Training failed - check data availability.")


def run_dashboard():
    from bot.dashboard.app import create_app
    app = create_app()
    dash_cfg = CONFIG.get("dashboard", {})
    app.run(
        host=dash_cfg.get("host", "0.0.0.0"),
        port=dash_cfg.get("port", 5000),
        debug=dash_cfg.get("debug", False),
    )


def run_scheduler():
    """Run periodic scans in a background thread."""
    interval = CONFIG.get("bot", {}).get("scan_interval_minutes", 15)
    schedule.every(interval).minutes.do(run_scan)

    print(f"Scheduler started - scanning every {interval} minutes")
    while True:
        schedule.run_pending()
        time.sleep(1)


def main():
    # Initialize database
    init_db()
    print("AI Trading Bot initialized.")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "scan":
            run_scan()
        elif command == "train":
            run_train()
        elif command == "dashboard":
            run_dashboard()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m bot.main [scan|train|dashboard]")
    else:
        # Full mode: scan + scheduler + dashboard
        print("Starting full bot (scan + scheduler + dashboard)...")

        # Run initial scan
        run_scan()

        # Start scheduler in background
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        # Start dashboard (blocking)
        run_dashboard()


if __name__ == "__main__":
    main()
