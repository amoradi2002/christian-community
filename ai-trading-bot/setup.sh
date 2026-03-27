#!/bin/bash
# ============================================================
# AI Trading Bot — One-Command Setup
# Run this when your Mac Mini arrives:
#   cd ai-trading-bot && bash setup.sh
# ============================================================

set -e

echo ""
echo "========================================="
echo "  AI Trading Bot — Setup"
echo "========================================="
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Install it first:"
    echo "  brew install python3"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"

# 2. Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "✓ Virtual environment activated"

# 3. Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# 4. Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "========================================="
    echo "  API Keys Setup"
    echo "========================================="
    echo ""
    echo "Let's set up your API keys."
    echo "(Press Enter to skip any you don't have yet)"
    echo ""

    # Alpaca (FREE — real-time prices + paper trading)
    echo "1. ALPACA (FREE — real-time prices + paper trading)"
    echo "   Sign up: https://app.alpaca.markets/signup"
    echo "   Then go to: Paper Trading > API Keys"
    read -p "   API Key: " ALPACA_KEY
    read -p "   Secret Key: " ALPACA_SECRET

    echo ""

    # Finnhub (FREE — earnings calendar)
    echo "2. FINNHUB (FREE — earnings calendar)"
    echo "   Sign up: https://finnhub.io/register"
    read -p "   API Key: " FINNHUB_KEY

    echo ""

    # Unusual Whales (PAID $150/mo — options flow, dark pool)
    echo "3. UNUSUAL WHALES (\$150/mo — options flow, dark pool)"
    echo "   Get token: https://unusualwhales.com/settings/api-dashboard"
    read -p "   API Token (Enter to skip): " UW_TOKEN

    echo ""

    # Discord
    echo "4. DISCORD ALERTS"
    echo "   Server Settings > Integrations > Webhooks > New Webhook"
    read -p "   Webhook URL (Enter to skip): " DISCORD_URL

    echo ""

    # Telegram
    echo "5. TELEGRAM BOT (interact from your phone)"
    echo "   Message @BotFather on Telegram > /newbot"
    read -p "   Bot Token (Enter to skip): " TG_TOKEN
    if [ -n "$TG_TOKEN" ]; then
        read -p "   Chat ID: " TG_CHAT
    fi

    echo ""

    # Email
    echo "6. EMAIL DIGEST (weekly/daily summaries)"
    read -p "   Gmail address (Enter to skip): " EMAIL
    if [ -n "$EMAIL" ]; then
        echo "   Need App Password: Google Account > Security > App Passwords"
        read -p "   App Password: " EMAIL_PASS
    fi

    # Write .env
    cat > .env << EOF
# Alpaca Markets (FREE — real-time data + paper trading)
ALPACA_API_KEY=${ALPACA_KEY}
ALPACA_SECRET_KEY=${ALPACA_SECRET}
ALPACA_PAPER=true

# Finnhub (FREE — earnings calendar)
FINNHUB_API_KEY=${FINNHUB_KEY}

# Unusual Whales (PAID — options flow, dark pool, congress trades)
UNUSUAL_WHALES_TOKEN=${UW_TOKEN}

# Discord Alerts
DISCORD_WEBHOOK_URL=${DISCORD_URL}

# Telegram Bot
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
TELEGRAM_CHAT_ID=${TG_CHAT}

# Email Digest
SMTP_SENDER=${EMAIL}
SMTP_PASSWORD=${EMAIL_PASS}
SMTP_RECIPIENT=${EMAIL}
EOF

    echo "✓ API keys saved to .env"
else
    echo "✓ .env file exists (edit manually to update keys)"
fi

# 5. Initialize database
echo ""
echo "Initializing database..."
python3 -c "
from bot.db.database import init_db
from bot.engine.trade_journal import init_journal_table
from bot.engine.strategy_tracker import init_strategy_tracker_table
from bot.learning.knowledge_base import init_knowledge_tables
init_db()
init_journal_table()
init_strategy_tracker_table()
init_knowledge_tables()
print('✓ Database initialized')
"

# 6. Set up trading profile
echo ""
read -p "Set up your trading profile now? (y/n): " SETUP_PROFILE
if [ "$SETUP_PROFILE" = "y" ]; then
    python3 -m bot.main profile
fi

# 7. Test connections
echo ""
echo "Testing connections..."
python3 -c "
import os
checks = []

# Alpaca
key = os.getenv('ALPACA_API_KEY', '')
if key and key != 'None':
    try:
        from bot.data.alpaca_provider import fetch_alpaca_realtime
        price = fetch_alpaca_realtime('SPY')
        if price:
            checks.append(('Alpaca (real-time prices)', True, f'SPY = \${price.get(\"last_price\", 0):.2f}'))
        else:
            checks.append(('Alpaca', False, 'No data returned'))
    except Exception as e:
        checks.append(('Alpaca', False, str(e)[:50]))
else:
    checks.append(('Alpaca', False, 'No API key — using Yahoo (15min delay)'))

# Finnhub
fh_key = os.getenv('FINNHUB_API_KEY', '')
if fh_key and fh_key != 'None':
    checks.append(('Finnhub (earnings)', True, 'Key configured'))
else:
    checks.append(('Finnhub', False, 'No key — earnings via Yahoo fallback'))

# Unusual Whales
uw = os.getenv('UNUSUAL_WHALES_TOKEN', '')
if uw and uw != 'None':
    checks.append(('Unusual Whales (options flow)', True, 'Token configured'))
else:
    checks.append(('Unusual Whales', False, 'Skipped — no token'))

# Discord
dc = os.getenv('DISCORD_WEBHOOK_URL', '')
if dc and dc != 'None' and 'discord.com' in dc:
    checks.append(('Discord alerts', True, 'Webhook configured'))
else:
    checks.append(('Discord', False, 'No webhook'))

# Telegram
tg = os.getenv('TELEGRAM_BOT_TOKEN', '')
if tg and tg != 'None':
    checks.append(('Telegram bot', True, 'Token configured'))
else:
    checks.append(('Telegram', False, 'No token'))

for name, ok, detail in checks:
    icon = '✓' if ok else '✗'
    print(f'  {icon} {name}: {detail}')
"

# 8. Done!
echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "  Start the bot:"
echo "    source venv/bin/activate"
echo "    python -m bot.main              # Full bot (scan + dashboard + Telegram)"
echo "    python -m bot.main live          # Interactive CLI mode"
echo "    python -m bot.main dashboard     # Web dashboard only"
echo ""
echo "  Quick commands:"
echo "    python -m bot.main scan          # Run a scan now"
echo "    python -m bot.main premarket     # Pre-market scanner"
echo "    python -m bot.main sentiment AAPL  # News sentiment"
echo ""
echo "  Or just text your Telegram bot — it handles everything."
echo ""
