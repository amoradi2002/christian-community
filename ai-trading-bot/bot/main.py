"""
AI Trading Bot - Main Entry Point

Usage:
    python -m bot.main              # Start bot (scan + dashboard)
    python -m bot.main scan         # Run a single scan (all strategies)
    python -m bot.main day          # Run day trade scan (intraday strategies)
    python -m bot.main swing        # Run swing trade scan (daily strategies)
    python -m bot.main intel        # Run intelligence scan (whales, earnings, insiders)
    python -m bot.main sectors      # Run sector rotation analysis
    python -m bot.main journal      # View weekly trade journal review
    python -m bot.main train        # Train the AI model
    python -m bot.main dashboard    # Start dashboard only
    python -m bot.main learn <url>  # Learn strategies from a YouTube video
    python -m bot.main live          # Interactive mode - analyze tickers, manage watchlist, log trades
    python -m bot.main profile      # Set up your trading profile (budget, risk, goals)
    python -m bot.main setup        # Interactive setup for Discord/Telegram/Email
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


def run_day_scan():
    """Run day-trade-specific scan with intraday data."""
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    interval = CONFIG.get("data", {}).get("intraday_interval", "5m")
    return analyzer.run_day_scan(interval=interval)


def run_swing_scan():
    """Run swing-trade-specific scan with daily data."""
    from bot.engine.analyzer import Analyzer
    analyzer = Analyzer()
    return analyzer.run_swing_scan()


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


def run_learn(url):
    from bot.learning.youtube import process_video
    print(f"Processing YouTube video: {url}")
    result = process_video(url)

    if result["status"] == "success":
        print(f"\nVideo: {result['title']}")
        print(f"Channel: {result['channel']}")
        print(f"Transcript length: {result['transcript_length']} chars")
        print(f"Strategies found: {result['strategies_found']}")
        print(f"New strategies saved: {result['strategies_saved']}")
        for s in result["strategies"]:
            print(f"\n  Strategy: {s['name']} ({s['signal']})")
            for c in s["conditions"]:
                ref = c.get("ref", c.get("value", ""))
                print(f"    {c['indicator']} {c['operator']} {ref}")
        print("\nStrategies saved as DISABLED. Go to /strategies to review and enable them.")
    elif result["status"] == "no_transcript":
        print(f"\nNo transcript available. Try a video with captions.")
    elif result["status"] == "already_processed":
        print(f"\n{result['message']}")
    else:
        print(f"\nError: {result.get('message', 'Unknown error')}")


def run_profile():
    """Interactive profile setup - set your budget, risk tolerance, and trading style."""
    from bot.engine.risk_manager import load_profile, update_profile, RISK_PRESETS, RiskManager

    print("\n=== Trading Profile Setup ===")
    print("Let's set up your personal trading profile.\n")

    current = load_profile()

    # Starting capital
    print(f"Current capital: ${current.current_capital:.2f}")
    capital_input = input("How much are you starting with? (dollar amount, Enter to keep current): $").strip()
    if capital_input:
        try:
            capital = float(capital_input.replace(",", ""))
            update_profile(starting_capital=capital, current_capital=capital, peak_capital=capital)
            print(f"  Set to ${capital:.2f}")
        except ValueError:
            print("  Invalid amount, keeping current.")

    # Risk level
    print(f"\nRisk levels:")
    print("  1. Conservative - Risk 1% per trade, 3% daily max, max 3 positions")
    print("     Best for: Small accounts, learning, preserving capital")
    print("  2. Moderate     - Risk 2% per trade, 3% daily max, max 5 positions")
    print("     Best for: Most traders, steady growth")
    print("  3. Aggressive   - Risk 3% per trade, 5% daily max, max 8 positions")
    print("     Best for: Experienced traders, larger accounts")

    risk_choice = input(f"\nYour risk level (1/2/3, current: {current.risk_level}): ").strip()
    risk_map = {"1": "conservative", "2": "moderate", "3": "aggressive"}
    if risk_choice in risk_map:
        level = risk_map[risk_choice]
        update_profile(risk_level=level)
        preset = RISK_PRESETS[level]
        print(f"  Set to {level}: {preset['risk_per_trade_pct']}% per trade, "
              f"{preset['daily_loss_limit_pct']}% daily max, "
              f"max {preset['max_open_positions']} positions, "
              f"min R:R {preset['min_risk_reward']}:1")

    # Custom risk per trade
    custom = input("\nWant to customize risk per trade %? (Enter to skip, or type 1-10): ").strip()
    if custom:
        try:
            pct = float(custom)
            if 0.5 <= pct <= 10:
                update_profile(risk_per_trade_pct=pct)
                print(f"  Risk per trade set to {pct}%")
            else:
                print("  Must be between 0.5% and 10%")
        except ValueError:
            pass

    # Daily loss limit
    daily = input(f"\nMax daily loss before stopping? (%, current: {current.daily_loss_limit_pct}%, Enter to keep): ").strip()
    if daily:
        try:
            update_profile(daily_loss_limit_pct=float(daily))
            print(f"  Daily loss limit set to {daily}%")
        except ValueError:
            pass

    # Max positions
    max_pos = input(f"\nMax simultaneous positions? (current: {current.max_open_positions}, Enter to keep): ").strip()
    if max_pos:
        try:
            update_profile(max_open_positions=int(max_pos))
        except ValueError:
            pass

    # Trading style preference
    print("\nPreferred trading styles:")
    print("  1. Day trading only")
    print("  2. Swing trading only")
    print("  3. Both day and swing")
    print("  4. Options focused")
    print("  5. All styles")
    style_choice = input("Your preference (1-5, Enter to skip): ").strip()
    style_map = {
        "1": ["day"], "2": ["swing"], "3": ["day", "swing"],
        "4": ["options"], "5": ["day", "swing", "options"],
    }
    if style_choice in style_map:
        update_profile(preferred_strategies=style_map[style_choice])
        print(f"  Set to: {', '.join(style_map[style_choice])}")

    # Show summary
    rm = RiskManager()
    profile = rm.profile
    status = rm.get_status()

    print("\n=== Your Trading Profile ===")
    print(f"  Capital:          ${profile.current_capital:,.2f}")
    print(f"  Risk Level:       {profile.risk_level.capitalize()}")
    print(f"  Risk Per Trade:   {profile.risk_per_trade_pct}% (${profile.risk_per_trade_dollars():.2f})")
    print(f"  Daily Loss Max:   {profile.daily_loss_limit_pct}%")
    print(f"  Max Day Trades:   {profile.max_day_trades}")
    print(f"  Max Swing Trades: {profile.max_swing_trades}")
    print(f"  Max Per Stock:    {profile.max_portfolio_pct}% of portfolio")
    print(f"  Min R:R Ratio:    {profile.min_risk_reward}:1")
    print(f"  Options Max:      {profile.options_max_pct}% per trade")

    if profile.total_trades > 0:
        print(f"\n  --- Performance ---")
        print(f"  Total Trades:     {profile.total_trades}")
        print(f"  Win Rate:         {profile.win_rate:.1%}")
        print(f"  Total P&L:        ${profile.total_pnl:,.2f}")
        print(f"  Growth:           {profile.growth_pct:,.1f}%")
        print(f"  Risk Multiplier:  {profile.risk_multiplier}x")

    print(f"\nProfile saved! The bot will size all trades based on these settings.")
    print(f"Run 'python -m bot.main' to start trading with your profile.\n")


def run_sectors():
    """Run sector rotation analysis."""
    from bot.engine.sector_rotation import SECTOR_ETFS, analyze_sector_rotation

    print("\nRunning sector rotation analysis...")

    # Fetch sector ETF data
    sector_data = {}
    all_symbols = list(SECTOR_ETFS.keys()) + ["SPY"]

    provider = CONFIG.get("data", {}).get("provider", "yfinance")

    for symbol in all_symbols:
        try:
            if provider == "alpaca":
                from bot.data.alpaca_provider import fetch_alpaca_bars
                candles = fetch_alpaca_bars(symbol, interval="1d", days=5)
            else:
                from bot.data.fetcher import fetch_market_data
                candles = fetch_market_data(symbol, period="5d", interval="1d")

            if len(candles) >= 2:
                change = ((candles[-1].close - candles[-2].close) / candles[-2].close) * 100
                vol_ratio = candles[-1].volume / candles[-2].volume if candles[-2].volume > 0 else 1.0
                sector_data[symbol] = {"change_pct": round(change, 2), "volume_ratio": round(vol_ratio, 2)}
        except Exception as e:
            print(f"  [{symbol}] Error: {e}")

    if not sector_data:
        print("Could not fetch sector data.")
        return

    report = analyze_sector_rotation(sector_data)

    print(f"\n=== Sector Rotation Report ===")
    print(f"Market Regime: {report.market_regime.upper()}")
    print(f"SPY: {report.spy_change_pct:+.2f}%\n")

    print("Leading Sectors:")
    for s in report.top_sectors:
        print(f"  {s.symbol:5s} ({s.name:25s}) {s.change_pct:+.2f}%  ({s.relative_to_spy:+.2f}% vs SPY)")

    print("\nLagging Sectors:")
    for s in report.bottom_sectors:
        print(f"  {s.symbol:5s} ({s.name:25s}) {s.change_pct:+.2f}%  ({s.relative_to_spy:+.2f}% vs SPY)")

    print(f"\nRecommendation: {report.recommendation}")

    # Send to Discord
    try:
        from bot.alerts.discord import DiscordChannel
        discord = DiscordChannel()
        discord.send_sector_report(report.to_dict())
    except Exception:
        pass

    return report


def run_journal():
    """Show weekly trade journal review."""
    from bot.engine.trade_journal import weekly_review

    print("\n=== Weekly Trade Journal Review ===\n")
    review = weekly_review(weeks_ago=0)

    if review.get("total_trades", 0) == 0:
        print(review.get("message", "No trades this week."))
        print("Log trades via the dashboard or API at /api/journal/log")
        return

    print(f"Week: {review['week']}")
    print(f"Total Trades: {review['total_trades']} ({review['winners']}W / {review['losers']}L)")
    print(f"Win Rate: {review['win_rate']:.1f}%")
    print(f"Total P&L: ${review['total_pnl']:.2f}")
    print(f"Avg R Winner: {review['avg_r_winner']:+.2f}R")
    print(f"Avg R Loser: {review['avg_r_loser']:+.2f}R")
    print(f"Avg Process Score: {review['avg_process_score']:.1f}/5")

    best = review.get("best_trade")
    worst = review.get("worst_trade")
    if best:
        print(f"\nBest Trade: {best['symbol']} ${best['pnl_dollars']:+.2f} ({best.get('setup', '')})")
    if worst:
        print(f"Worst Trade: {worst['symbol']} ${worst['pnl_dollars']:+.2f} ({worst.get('setup', '')})")

    rules = review.get("rules_broken", [])
    if rules:
        print("\nRules Broken:")
        for r in rules:
            print(f"  ! {r}")

    by_style = review.get("by_style", {})
    print(f"\nBy Style: {by_style.get('day', 0)} day | {by_style.get('swing', 0)} swing | {by_style.get('options', 0)} options")

    # Send to Discord
    try:
        from bot.alerts.discord import DiscordChannel
        discord = DiscordChannel()
        discord.send_journal_review(review)
    except Exception:
        pass

    return review


def run_setup():
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"

    print("\n=== AI Trading Bot Setup ===\n")

    print("1. ALPACA MARKETS (Real-time data + Trading)")
    print("   Sign up free at https://app.alpaca.markets/signup")
    alpaca_key = input("   API Key (or Enter to skip): ").strip()
    alpaca_secret = ""
    if alpaca_key:
        alpaca_secret = input("   Secret Key: ").strip()

    print("\n2. FINNHUB (FREE - Earnings calendar + estimates)")
    print("   Sign up free at https://finnhub.io/register")
    finnhub_key = input("   API Key (or Enter to skip): ").strip()

    print("\n3. UNUSUAL WHALES (Options flow + Dark pool, $150/mo)")
    print("   Get your API token at https://unusualwhales.com/settings/api-dashboard")
    uw_token = input("   API Token (or Enter to skip): ").strip()

    print("\n4. DISCORD ALERTS")
    print("   To get your Discord webhook URL:")
    print("   - Open Discord > Server Settings > Integrations > Webhooks")
    print("   - Click 'New Webhook', pick a channel, copy the URL")
    discord_url = input("   Paste your Discord webhook URL (or press Enter to skip): ").strip()

    print("\n5. TELEGRAM ALERTS")
    print("   To get your Telegram bot:")
    print("   - Message @BotFather on Telegram, create a bot, get the token")
    print("   - Message your bot, then get your chat_id from the API")
    tg_token = input("   Paste your Telegram bot token (or press Enter to skip): ").strip()
    tg_chat = ""
    if tg_token:
        tg_chat = input("   Paste your Telegram chat ID: ").strip()

    print("\n6. EMAIL ALERTS")
    email_sender = input("   Your Gmail address (or press Enter to skip): ").strip()
    email_pass = ""
    if email_sender:
        print("   You need an App Password (Google Account > Security > App Passwords)")
        email_pass = input("   Your Gmail App Password: ").strip()

    # Write .env file
    lines = []
    if alpaca_key:
        lines.append(f"ALPACA_API_KEY={alpaca_key}")
    if alpaca_secret:
        lines.append(f"ALPACA_SECRET_KEY={alpaca_secret}")
        lines.append("ALPACA_PAPER=true")
    if finnhub_key:
        lines.append(f"FINNHUB_API_KEY={finnhub_key}")
    if uw_token:
        lines.append(f"UNUSUAL_WHALES_TOKEN={uw_token}")
    if discord_url:
        lines.append(f"DISCORD_WEBHOOK_URL={discord_url}")
    if tg_token:
        lines.append(f"TELEGRAM_BOT_TOKEN={tg_token}")
    if tg_chat:
        lines.append(f"TELEGRAM_CHAT_ID={tg_chat}")
    if email_sender:
        lines.append(f"SMTP_SENDER={email_sender}")
    if email_pass:
        lines.append(f"SMTP_PASSWORD={email_pass}")

    if lines:
        with open(env_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nSaved to {env_path}")
        print("Restart the bot to apply changes.")
    else:
        print("\nNo credentials entered. You can set them up later in the .env file.")

    # Test Discord if configured
    if discord_url:
        test = input("\nSend a test message to Discord? (y/n): ").strip().lower()
        if test == "y":
            import requests
            payload = {
                "username": "AI Trading Bot",
                "embeds": [{
                    "title": "Bot Connected!",
                    "description": "Your AI Trading Bot is now connected to this Discord channel. You'll receive alerts here.",
                    "color": 0x00FF00,
                }]
            }
            try:
                resp = requests.post(discord_url, json=payload, timeout=10)
                if resp.status_code in (200, 204):
                    print("Test message sent! Check your Discord channel.")
                else:
                    print(f"Failed with status {resp.status_code}. Check your webhook URL.")
            except Exception as e:
                print(f"Error: {e}")

    print("\nSetup complete! Run 'python -m bot.main' to start the bot.")


def run_intel():
    """Run the intelligence scanner (Unusual Whales, Earnings, Finviz)."""
    from bot.engine.intelligence_scanner import run_intelligence_scan
    alerts = run_intelligence_scan()

    if alerts:
        print(f"\n--- Intelligence Alerts ({len(alerts)}) ---")
        for a in alerts:
            marker = " *" if a.get("in_watchlist") else ""
            print(f"  [{a['type']}]{marker} {a['message']}")
    else:
        print("No intelligence alerts at this time.")

    return alerts


def run_scheduler():
    """Run periodic scans in a background thread."""
    interval = CONFIG.get("bot", {}).get("scan_interval_minutes", 15)
    schedule.every(interval).minutes.do(run_scan)

    # Run intelligence scan every hour
    schedule.every(60).minutes.do(run_intel)

    # Run sector analysis every 4 hours
    schedule.every(4).hours.do(run_sectors)

    print(f"Scheduler started - strategy scan every {interval}m, intel every 60m, sectors every 4h")
    while True:
        schedule.run_pending()
        time.sleep(1)


def main():
    # Initialize database
    init_db()

    # Initialize trade journal table
    try:
        from bot.engine.trade_journal import init_journal_table
        init_journal_table()
    except Exception:
        pass

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "scan":
            print("AI Trading Bot - Running full scan...")
            run_scan()
        elif command == "day":
            print("AI Trading Bot - Running day trade scan...")
            run_day_scan()
        elif command == "swing":
            print("AI Trading Bot - Running swing trade scan...")
            run_swing_scan()
        elif command == "intel":
            print("AI Trading Bot - Running intelligence scan...")
            run_intel()
        elif command == "sectors":
            run_sectors()
        elif command == "journal":
            run_journal()
        elif command == "train":
            run_train()
        elif command == "dashboard":
            print("AI Trading Bot - Starting dashboard...")
            run_dashboard()
        elif command == "learn":
            if len(sys.argv) < 3:
                print("Usage: python -m bot.main learn <youtube-url>")
                sys.exit(1)
            run_learn(sys.argv[2])
        elif command == "live":
            from bot.interactive import run_interactive
            run_interactive()
        elif command == "profile":
            run_profile()
        elif command == "setup":
            run_setup()
        else:
            print(f"Unknown command: {command}")
            print("Commands:")
            print("  scan      - Run full scan (all strategies)")
            print("  day       - Run day trade scan (intraday)")
            print("  swing     - Run swing trade scan (daily)")
            print("  intel     - Run intelligence scan")
            print("  sectors   - Run sector rotation analysis")
            print("  journal   - Weekly trade journal review")
            print("  live      - Interactive mode (real-time analysis)")
            print("  train     - Train AI model")
            print("  dashboard - Start web dashboard")
            print("  learn     - Learn from YouTube <url>")
            print("  profile   - Set up trading profile")
            print("  setup     - Configure API keys")
    else:
        # Full mode: scan + scheduler + dashboard
        print("AI Trading Bot initialized.")
        print("Starting full bot (scan + scheduler + dashboard)...")

        # Run initial scans
        run_scan()
        run_intel()

        # Start scheduler in background
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        # Start dashboard (blocking)
        run_dashboard()


if __name__ == "__main__":
    main()
