"""
AI Trading Agent — Conversational interface to the trading bot.

Uses the Claude API to understand natural language requests and route them
to the bot's tools (scanner, sentiment, backtest, knowledge base, etc).

The agent and the bot work together:
  - You talk to the agent in plain English
  - The agent calls bot tools to get real data
  - The agent reasons about the data and gives you actionable answers

Usage:
    from bot.agent.trading_agent import TradingAgent
    agent = TradingAgent()
    response = agent.chat("What's the market looking like today?")
    print(response)

    # Or run interactive mode:
    agent.run_interactive()
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional trading assistant working alongside an AI trading bot. You have access to real market data, scanners, backtesting, sentiment analysis, knowledge base, and portfolio management through your tools.

Your job:
1. Answer trading questions using REAL DATA from your tools — never guess prices or make up numbers
2. When asked about a stock, use analyze_symbol for a full picture or get_price for just the price
3. When asked about market conditions, check the regime and run scans
4. When asked about strategies, search the knowledge base and backtest them
5. Be direct and actionable — traders don't want fluff, they want levels, entries, stops, and targets
6. Always consider risk management — mention position sizing, stops, and risk/reward
7. If the user shares a YouTube video or trading content, ingest it into the knowledge base

Your personality:
- Direct, no BS — get to the point
- Data-driven — use your tools, don't speculate
- Risk-conscious — always mention the downside
- Practical — give specific levels and actions, not vague advice

Important context:
- The user trades: Robinhood (options), Fidelity (swing), Interactive Brokers (day trading), TradingView (charts)
- Always frame advice in terms of these brokers when relevant
- Options trades go through Robinhood, day trades through IB, swing trades through Fidelity

Current date: {date}
"""


class TradingAgent:
    """Conversational AI agent that interfaces with the trading bot."""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        self.conversation_history = []
        self.max_history = 50  # Keep last 50 messages
        self.client = None

        # Import tools
        from bot.agent.tools import TOOLS, execute_tool
        self.tools = TOOLS
        self.execute_tool = execute_tool

        if self.api_key:
            self._init_client()

    def _init_client(self):
        """Initialize the Anthropic client."""
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("Anthropic client initialized (model: %s)", self.model)
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
            self.client = None
        except Exception as e:
            logger.error("Failed to init Anthropic client: %s", e)
            self.client = None

    def chat(self, user_message: str) -> str:
        """Send a message and get a response. The agent can call tools."""
        if not self.client:
            if not self.api_key:
                return ("No ANTHROPIC_API_KEY set. Add it to your .env file:\n"
                        "  ANTHROPIC_API_KEY=sk-ant-...\n"
                        "Get a key at https://console.anthropic.com/settings/keys")
            self._init_client()
            if not self.client:
                return "Failed to initialize AI client. Check your API key."

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        # Trim history if too long
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        system = SYSTEM_PROMPT.format(date=datetime.now().strftime("%Y-%m-%d %H:%M ET"))

        try:
            response = self._call_api(system)
            return response
        except Exception as e:
            logger.error("Agent chat error: %s", e, exc_info=True)
            return f"Error: {e}"

    def _call_api(self, system: str) -> str:
        """Call Claude API with tool use loop."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=self.tools,
            messages=self.conversation_history,
        )

        # Handle tool use loop — agent might call multiple tools
        max_iterations = 10
        iteration = 0

        while response.stop_reason == "tool_use" and iteration < max_iterations:
            iteration += 1

            # Collect all tool calls from the response
            assistant_content = response.content
            tool_results = []

            for block in assistant_content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    logger.info("Agent calling tool: %s(%s)", tool_name, json.dumps(tool_input, default=str)[:200])
                    result = self.execute_tool(tool_name, tool_input)
                    logger.info("Tool result: %s", result[:500])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    })

            # Add assistant message and tool results to history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_content,
            })
            self.conversation_history.append({
                "role": "user",
                "content": tool_results,
            })

            # Call API again with tool results
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=self.tools,
                messages=self.conversation_history,
            )

        # Extract final text response
        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        # Add final response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content,
        })

        return final_text

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def run_interactive(self):
        """Run the agent in interactive terminal mode."""
        print("\n" + "=" * 60)
        print("  AI Trading Agent")
        print("  Talk to me about the market. I have full access to the bot.")
        print("=" * 60)
        print("\nCommands:")
        print("  /clear  — Clear conversation history")
        print("  /tools  — List available tools")
        print("  /quit   — Exit")
        print()

        if not self.api_key:
            print("WARNING: No ANTHROPIC_API_KEY set.")
            print("Add to .env: ANTHROPIC_API_KEY=sk-ant-...")
            print("Get a key at: https://console.anthropic.com/settings/keys\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input == "/quit":
                print("Goodbye!")
                break
            elif user_input == "/clear":
                self.clear_history()
                print("History cleared.\n")
                continue
            elif user_input == "/tools":
                print("\nAvailable tools:")
                for t in self.tools:
                    print(f"  {t['name']:25s} — {t['description'][:80]}")
                print()
                continue

            print("\nThinking...", end="", flush=True)
            response = self.chat(user_input)
            print("\r" + " " * 20 + "\r", end="")  # Clear "Thinking..."
            print(f"\nAgent: {response}\n")


class LocalAgent:
    """Lightweight agent that works WITHOUT an API key.

    Uses the bot's tools directly with rule-based routing instead of Claude.
    Good for when you don't have an Anthropic key yet but want to interact
    with the bot conversationally.
    """

    def __init__(self):
        from bot.agent.tools import execute_tool
        self.execute_tool = execute_tool

    def chat(self, message: str) -> str:
        """Route messages to tools based on keyword matching."""
        msg = message.lower().strip()

        # Price check
        if any(w in msg for w in ["price", "how much", "what's", "quote", "trading at"]):
            symbol = self._extract_symbol(msg)
            if symbol:
                result = json.loads(self.execute_tool("get_price", {"symbol": symbol}))
                if "error" in result:
                    return result["error"]
                return (f"{result['symbol']}: ${result['price']} ({result['change_pct']:+.2f}%)\n"
                        f"  Open: ${result['open']} | High: ${result['high']} | Low: ${result['low']}\n"
                        f"  Volume: {result['volume']:,}")

        # Scan
        if any(w in msg for w in ["scan", "signals", "opportunities", "what to trade"]):
            style = "day" if "day" in msg else "swing" if "swing" in msg else "all"
            result = json.loads(self.execute_tool("scan_market", {"style": style}))
            if not result.get("signals"):
                return result.get("message", "No signals found.")
            lines = [f"Found {result['count']} signals:"]
            for s in result["signals"][:5]:
                lines.append(f"  {s['action']:4s} {s['symbol']:6s} @ ${s['entry'] or '?':>8} | "
                           f"{s['strategy']} | Conf: {s['confidence']:.0%}")
            return "\n".join(lines)

        # Sentiment
        if any(w in msg for w in ["sentiment", "news", "headlines"]):
            symbol = self._extract_symbol(msg)
            if symbol:
                result = json.loads(self.execute_tool("check_sentiment", {"symbol": symbol}))
                lines = [f"{result['symbol']} Sentiment: {result['overall'].upper()} (score: {result['score']:+.3f})"]
                if result.get("recommendation"):
                    lines.append(f"  Recommendation: {result['recommendation']}")
                for h in result.get("top_headlines", [])[:5]:
                    icon = "+" if h["score"] > 0 else "-" if h["score"] < 0 else " "
                    lines.append(f"  [{icon}] {h['headline'][:80]}")
                return "\n".join(lines)

        # Regime
        if any(w in msg for w in ["regime", "market condition", "bull", "bear"]):
            result = json.loads(self.execute_tool("check_regime", {}))
            return (f"Market Regime: {result['regime'].upper()}\n"
                    f"  Confidence: {result['confidence']:.0%}\n"
                    f"  Trend Strength: {result['trend_strength']:.2f}\n"
                    f"  Volatility: {result['volatility_percentile']:.0f}th percentile\n"
                    f"  Risk Multiplier: {result['risk_multiplier']:.2f}x\n"
                    f"  {result['description']}\n"
                    f"  Best strategies: {', '.join(result['recommended_strategies'])}")

        # Backtest
        if any(w in msg for w in ["backtest", "test strategy", "historical"]):
            symbol = self._extract_symbol(msg) or "SPY"
            result = json.loads(self.execute_tool("run_backtest", {"symbol": symbol}))
            if "error" in result or "message" in result:
                return result.get("error", result.get("message", ""))
            lines = [f"Backtest results for {symbol}:"]
            for r in result["results"]:
                lines.append(f"  {r['strategy']:30s} | {r['total_trades']:3d} trades | "
                           f"Win: {r['win_rate']}% | Return: {r['total_return_pct']:+.1f}% | "
                           f"Sharpe: {r['sharpe_ratio']:.2f}")
            return "\n".join(lines)

        # Knowledge
        if any(w in msg for w in ["knowledge", "what do you know", "rules", "learned"]):
            if "summary" in msg or "how much" in msg:
                result = json.loads(self.execute_tool("knowledge_summary", {}))
                return (f"Knowledge Base:\n"
                        f"  Entries: {result['total_entries']}\n"
                        f"  Rules: {result['total_rules']} ({result['validated_rules']} validated)\n"
                        f"  Strategies: {result['unique_strategies']}\n"
                        f"  Indicators: {result['unique_indicators']}")
            query = msg.replace("knowledge", "").replace("rules", "").strip() or "trading"
            result = json.loads(self.execute_tool("search_knowledge", {"query": query}))
            if not result.get("results"):
                return result.get("message", "No results.")
            lines = ["Knowledge base results:"]
            for r in result["results"]:
                lines.append(f"  [{r['source']}] {r['title']} (conf: {r['confidence']:.2f})")
                for rule in r.get("rules", [])[:2]:
                    lines.append(f"    - {rule[:100]}")
            return "\n".join(lines)

        # Portfolio
        if any(w in msg for w in ["portfolio", "positions", "holdings", "p&l"]):
            result = json.loads(self.execute_tool("get_portfolio", {}))
            lines = [f"Portfolio: {result['position_count']} positions | "
                     f"{result['total_trades']} trades | Win: {result['win_rate']}% | "
                     f"P&L: ${result['total_pnl']:.2f}"]
            for p in result["positions"]:
                lines.append(f"  {p['symbol']:6s} x{p['quantity']} @ ${p['entry_price']} ({p['strategy']})")
            return "\n".join(lines)

        # Intelligence
        if any(w in msg for w in ["intel", "whales", "dark pool", "insider", "flow"]):
            result = json.loads(self.execute_tool("run_intelligence", {}))
            if not result.get("alerts"):
                return result.get("message", "No alerts.")
            lines = [f"Intelligence: {result['count']} alerts"]
            for a in result["alerts"][:8]:
                wl = " *" if a.get("watchlist") else ""
                lines.append(f"  [{a['type']}]{wl} {a['message'][:100]}")
            return "\n".join(lines)

        # Analyze specific symbol
        if any(w in msg for w in ["analyze", "analysis", "look at", "check out", "tell me about"]):
            symbol = self._extract_symbol(msg)
            if symbol:
                result = json.loads(self.execute_tool("analyze_symbol", {"symbol": symbol}))
                lines = [f"Full Analysis: {symbol}"]
                if "price" in result and "error" not in result["price"]:
                    p = result["price"]
                    lines.append(f"  Price: ${p['price']} ({p['change_pct']:+.2f}%)")
                if "sentiment" in result:
                    s = result["sentiment"]
                    lines.append(f"  Sentiment: {s['overall'].upper()} ({s['score']:+.3f})")
                if "indicators" in result:
                    ind = result["indicators"]
                    if ind.get("rsi_14"):
                        lines.append(f"  RSI(14): {ind['rsi_14']}")
                    if ind.get("macd_histogram"):
                        lines.append(f"  MACD Histogram: {ind['macd_histogram']}")
                if result.get("known_rules"):
                    lines.append(f"  Known Rules:")
                    for r in result["known_rules"][:3]:
                        lines.append(f"    - {r[:80]}")
                return "\n".join(lines)

        # Sectors
        if any(w in msg for w in ["sector", "rotation", "money flow"]):
            result = json.loads(self.execute_tool("get_sector_rotation", {}))
            if "error" in result:
                return result["error"]
            lines = [f"Sector Rotation ({result['regime'].upper()}) | SPY: {result['spy_change']:+.2f}%"]
            lines.append("  Leaders:")
            for s in result["top_sectors"][:3]:
                lines.append(f"    {s['symbol']:5s} ({s['name']}) {s['change']:+.2f}% ({s['vs_spy']:+.2f}% vs SPY)")
            lines.append("  Laggards:")
            for s in result["bottom_sectors"][:3]:
                lines.append(f"    {s['symbol']:5s} ({s['name']}) {s['change']:+.2f}% ({s['vs_spy']:+.2f}% vs SPY)")
            return "\n".join(lines)

        # Premarket
        if any(w in msg for w in ["premarket", "pre-market", "gap"]):
            result = json.loads(self.execute_tool("get_premarket", {}))
            return f"Pre-market: {result['mover_count']} movers, {len(result.get('earnings_today', []))} earnings today"

        # YouTube/content ingestion
        if "youtube.com" in msg or "youtu.be" in msg:
            import re
            urls = re.findall(r'https?://[^\s]+', msg)
            if urls:
                result = json.loads(self.execute_tool("ingest_content", {"content": urls[0]}))
                if result.get("status") == "success":
                    return (f"Ingested! Rules extracted: {result.get('rules_extracted', 0)} | "
                            f"Strategies: {result.get('strategies_found', 0)} | "
                            f"Indicators: {result.get('indicators_found', 0)}")
                return f"Ingestion: {result.get('message', result.get('status', 'error'))}"

        # Help
        if any(w in msg for w in ["help", "what can you do", "commands"]):
            return ("I can help you with:\n"
                    "  'price AAPL'              — Get current price\n"
                    "  'scan' / 'day scan'       — Find trade signals\n"
                    "  'sentiment TSLA'          — News sentiment analysis\n"
                    "  'regime'                  — Market condition check\n"
                    "  'analyze NVDA'            — Full symbol analysis\n"
                    "  'backtest SPY'            — Test strategies historically\n"
                    "  'portfolio'               — Show positions & P&L\n"
                    "  'knowledge summary'       — What the bot has learned\n"
                    "  'sectors'                 — Sector rotation analysis\n"
                    "  'intel'                   — Whale flow & dark pool\n"
                    "  'premarket'               — Gap scanner\n"
                    "  [paste YouTube URL]       — Learn from video\n"
                    "  'help'                    — This message")

        return ("I didn't understand that. Try:\n"
                "  'price AAPL', 'scan', 'sentiment TSLA', 'regime',\n"
                "  'analyze NVDA', 'backtest SPY', 'portfolio', 'sectors'\n"
                "  Or type 'help' for all commands.")

    def _extract_symbol(self, text: str) -> str:
        """Extract a stock ticker from text."""
        import re
        # Look for $SYMBOL or common patterns
        match = re.search(r'\$([A-Z]{1,5})\b', text.upper())
        if match:
            return match.group(1)

        # Common tickers
        common = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
                   "SPY", "QQQ", "IWM", "AMD", "NFLX", "DIS", "BA", "JPM",
                   "V", "MA", "WMT", "HD", "COST", "CRM", "PYPL", "SQ",
                   "COIN", "PLTR", "SOFI", "RIVN", "NIO", "LCID"]
        words = text.upper().split()
        for word in words:
            cleaned = re.sub(r'[^A-Z]', '', word)
            if cleaned in common:
                return cleaned

        # Last resort: any 2-5 uppercase letter word
        for word in words:
            cleaned = re.sub(r'[^A-Z]', '', word)
            if 2 <= len(cleaned) <= 5 and cleaned.isalpha():
                # Skip common English words
                skip = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
                        "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET",
                        "HAS", "HIM", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW",
                        "OLD", "SEE", "WAY", "WHO", "DID", "LET", "SAY", "SHE",
                        "TOO", "USE", "WHAT", "WHY", "TELL", "LOOK", "SCAN",
                        "NEWS", "FROM", "THAT", "THIS", "WITH", "HAVE", "BEEN",
                        "MUCH", "ABOUT", "PRICE", "CHECK", "TRADE", "STOCK"}
                if cleaned not in skip:
                    return cleaned

        return ""

    def run_interactive(self):
        """Run local agent in interactive mode."""
        print("\n" + "=" * 60)
        print("  AI Trading Agent (Local Mode)")
        print("  No API key needed — direct tool access")
        print("=" * 60)
        print("\nType 'help' for commands, '/quit' to exit\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input == "/quit":
                print("Goodbye!")
                break

            response = self.chat(user_input)
            print(f"\nBot: {response}\n")


def create_agent() -> TradingAgent | LocalAgent:
    """Create the best available agent (Claude API if key exists, local otherwise)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        return TradingAgent(api_key=api_key)
    else:
        return LocalAgent()
