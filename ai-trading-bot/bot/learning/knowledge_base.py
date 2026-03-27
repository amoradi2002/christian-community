"""
Evolving Knowledge Base

Ingests trading knowledge from multiple sources (YouTube, mentorships, articles,
backtest results) and builds a searchable knowledge base that improves over time.

Usage:
    from bot.learning.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    kb.ingest_youtube("https://youtube.com/watch?v=...")
    kb.ingest_text("My mentor's rules", content, source_type="mentorship")
    results = kb.search_knowledge("RSI oversold bounce")
"""

import re
import json
import sqlite3
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from bot.db.database import get_connection


@dataclass
class KnowledgeEntry:
    id: int = 0
    source_type: str = ""       # youtube, mentorship, article, manual, backtest_result
    source_url: str = ""
    title: str = ""
    content: str = ""
    strategies_extracted: list = field(default_factory=list)
    indicators_mentioned: list = field(default_factory=list)
    patterns_mentioned: list = field(default_factory=list)
    key_rules: list = field(default_factory=list)
    confidence: float = 0.8
    tags: list = field(default_factory=list)
    created_at: str = ""
    times_referenced: int = 0


# --- Indicator and pattern keyword lists ---

INDICATOR_KEYWORDS = [
    "rsi", "macd", "bollinger band", "moving average", "sma", "ema",
    "vwap", "atr", "volume", "relative volume", "rvol", "obv",
    "stochastic", "fibonacci", "ichimoku", "adx", "cci", "williams %r",
    "parabolic sar", "pivot point", "support", "resistance",
    "50 sma", "200 sma", "8 ema", "20 ema", "50 ema", "9 ema", "21 ema",
    "rsi 14", "rsi 7", "macd histogram", "macd crossover",
    "bollinger squeeze", "bb upper", "bb lower", "bb middle",
]

PATTERN_KEYWORDS = [
    "hammer", "doji", "engulfing", "shooting star", "spinning top",
    "morning star", "evening star", "harami", "tweezer", "marubozu",
    "bull flag", "bear flag", "double top", "double bottom",
    "head and shoulders", "inverse head and shoulders",
    "cup and handle", "wedge", "triangle", "pennant", "channel",
    "gravestone doji", "dragonfly doji", "hanging man", "inverted hammer",
    "three white soldiers", "three black crows", "abandoned baby",
    "gap up", "gap down", "island reversal",
]

RULE_PATTERNS = [
    # Entry rules
    r"(?:buy|enter|go long)\s+(?:when|if|at|on)\s+(.+?)(?:\.|$)",
    r"(?:sell|short|go short)\s+(?:when|if|at|on)\s+(.+?)(?:\.|$)",
    r"entry\s*(?:point|signal|trigger)?\s*(?:is|at|when|:)\s*(.+?)(?:\.|$)",
    # Exit rules
    r"(?:take profit|target|exit)\s+(?:at|when|if)\s+(.+?)(?:\.|$)",
    r"(?:stop loss|stop|cut loss)\s+(?:at|when|if|below)\s+(.+?)(?:\.|$)",
    # Risk rules
    r"(?:risk|position size)\s+(?:no more than|max|maximum|only)\s+(.+?)(?:\.|$)",
    r"(?:never|don't|do not|avoid)\s+(.+?)(?:\.|$)",
    r"(?:always|must|rule)\s*:?\s+(.+?)(?:\.|$)",
    # Percentage rules
    r"(\d+(?:\.\d+)?%\s+(?:risk|stop|target|position|per trade|daily).+?)(?:\.|$)",
    # R:R rules
    r"(?:risk.?reward|r:r|r/r)\s*(?:of|at least|minimum|ratio)?\s*([\d.:]+.+?)(?:\.|$)",
]

STRATEGY_PATTERNS = [
    r"(?:strategy|setup|system|approach|method)\s*(?:is|called|named|:)\s*(.+?)(?:\.|$)",
    r"(?:i trade|i use|my strategy)\s+(.+?)(?:\.|$)",
    r"(?:the|this)\s+(\w+\s+(?:strategy|setup|system))\s+",
]


def init_knowledge_tables():
    """Create knowledge base tables."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            strategies_extracted TEXT DEFAULT '[]',
            indicators_mentioned TEXT DEFAULT '[]',
            patterns_mentioned TEXT DEFAULT '[]',
            key_rules TEXT DEFAULT '[]',
            confidence REAL DEFAULT 0.8,
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            times_referenced INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS knowledge_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_id INTEGER,
            rule_text TEXT NOT NULL,
            rule_type TEXT DEFAULT 'general',
            indicator TEXT DEFAULT '',
            pattern TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (knowledge_id) REFERENCES knowledge_base(id)
        );

        CREATE INDEX IF NOT EXISTS idx_kb_source_type ON knowledge_base(source_type);
        CREATE INDEX IF NOT EXISTS idx_kb_tags ON knowledge_base(tags);
        CREATE INDEX IF NOT EXISTS idx_kr_rule_type ON knowledge_rules(rule_type);
        CREATE INDEX IF NOT EXISTS idx_kr_indicator ON knowledge_rules(indicator);
    """)
    conn.close()


class KnowledgeBase:
    def __init__(self):
        init_knowledge_tables()

    def ingest_youtube(self, url: str) -> dict:
        """Process a YouTube video and extract trading knowledge.
        Uses existing youtube.py processor, then extracts and stores knowledge."""
        try:
            from bot.learning.youtube import process_video
            result = process_video(url)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        if result.get("status") != "success":
            return result

        # Extract knowledge from transcript
        transcript = result.get("transcript", "")
        title = result.get("title", url)

        knowledge = self._extract_trading_knowledge(transcript)
        strategies_from_vid = [s["name"] for s in result.get("strategies", [])]
        knowledge["strategies_extracted"].extend(strategies_from_vid)
        knowledge["strategies_extracted"] = list(set(knowledge["strategies_extracted"]))

        entry_id = self._store_entry(
            source_type="youtube",
            source_url=url,
            title=title,
            content=transcript[:10000],  # cap storage
            knowledge=knowledge,
            confidence=0.7,
            tags=["youtube", "video"] + knowledge.get("indicators_mentioned", [])[:5],
        )

        # Store extracted rules individually
        for rule in knowledge.get("key_rules", []):
            self._store_rule(entry_id, rule)

        return {
            "status": "success",
            "entry_id": entry_id,
            "title": title,
            "strategies_found": len(knowledge["strategies_extracted"]),
            "indicators_found": len(knowledge["indicators_mentioned"]),
            "patterns_found": len(knowledge["patterns_mentioned"]),
            "rules_extracted": len(knowledge["key_rules"]),
        }

    def ingest_text(self, title: str, content: str, source_type: str = "manual",
                    source_url: str = "", confidence: float = 0.8) -> dict:
        """Ingest raw text content (from mentorships, articles, notes)."""
        knowledge = self._extract_trading_knowledge(content)

        entry_id = self._store_entry(
            source_type=source_type,
            source_url=source_url,
            title=title,
            content=content[:10000],
            knowledge=knowledge,
            confidence=confidence,
            tags=[source_type] + knowledge.get("indicators_mentioned", [])[:5],
        )

        for rule in knowledge.get("key_rules", []):
            self._store_rule(entry_id, rule)

        return {
            "status": "success",
            "entry_id": entry_id,
            "title": title,
            "strategies_found": len(knowledge["strategies_extracted"]),
            "indicators_found": len(knowledge["indicators_mentioned"]),
            "patterns_found": len(knowledge["patterns_mentioned"]),
            "rules_extracted": len(knowledge["key_rules"]),
        }

    def ingest_backtest_results(self, strategy_name: str, results: dict) -> dict:
        """Learn from backtest results."""
        content = json.dumps(results, indent=2)
        title = f"Backtest: {strategy_name}"

        rules = []
        win_rate = results.get("win_rate", 0)
        sharpe = results.get("sharpe_ratio", 0)
        max_dd = results.get("max_drawdown", 0)

        if win_rate > 0.6:
            rules.append(f"{strategy_name} has {win_rate:.0%} win rate — high confidence strategy")
        elif win_rate < 0.35:
            rules.append(f"{strategy_name} has {win_rate:.0%} win rate — consider disabling or refining")

        if sharpe > 1.5:
            rules.append(f"{strategy_name} Sharpe ratio {sharpe:.2f} — excellent risk-adjusted returns")
        elif sharpe < 0.5:
            rules.append(f"{strategy_name} Sharpe ratio {sharpe:.2f} — poor risk-adjusted returns")

        if max_dd > 20:
            rules.append(f"{strategy_name} max drawdown {max_dd:.1f}% — needs tighter risk management")

        knowledge = {
            "strategies_extracted": [strategy_name],
            "indicators_mentioned": [],
            "patterns_mentioned": [],
            "key_rules": rules,
        }

        confidence = min(0.95, 0.5 + (results.get("total_trades", 0) / 200))

        entry_id = self._store_entry(
            source_type="backtest_result",
            source_url="",
            title=title,
            content=content[:10000],
            knowledge=knowledge,
            confidence=confidence,
            tags=["backtest", strategy_name.lower()],
        )

        for rule in rules:
            self._store_rule(entry_id, rule, rule_type="backtest")

        return {
            "status": "success",
            "entry_id": entry_id,
            "rules_learned": len(rules),
            "confidence": confidence,
        }

    def search_knowledge(self, query: str, limit: int = 10) -> list:
        """Search the knowledge base for relevant entries."""
        conn = get_connection()
        query_lower = query.lower()
        words = query_lower.split()

        # Search in title, content, tags, strategies, indicators
        like_clauses = []
        params = []
        for word in words[:5]:  # limit to 5 search terms
            like_clauses.append(
                "(LOWER(title) LIKE ? OR LOWER(content) LIKE ? OR "
                "LOWER(tags) LIKE ? OR LOWER(strategies_extracted) LIKE ? OR "
                "LOWER(indicators_mentioned) LIKE ?)"
            )
            pattern = f"%{word}%"
            params.extend([pattern] * 5)

        if not like_clauses:
            conn.close()
            return []

        where = " AND ".join(like_clauses)
        rows = conn.execute(
            f"SELECT * FROM knowledge_base WHERE {where} "
            f"ORDER BY confidence DESC, times_referenced DESC LIMIT ?",
            params + [limit]
        ).fetchall()

        results = []
        for row in rows:
            entry = self._row_to_entry(row)
            # Increment reference count
            conn.execute(
                "UPDATE knowledge_base SET times_referenced = times_referenced + 1 WHERE id = ?",
                (row["id"],)
            )
            results.append(entry)

        conn.commit()
        conn.close()
        return results

    def get_rules_for_setup(self, setup_type: str) -> list:
        """Get all learned rules relevant to a specific setup type."""
        conn = get_connection()
        pattern = f"%{setup_type.lower()}%"
        rows = conn.execute(
            "SELECT kr.rule_text, kr.rule_type, kb.title, kb.source_type, kb.confidence "
            "FROM knowledge_rules kr "
            "JOIN knowledge_base kb ON kr.knowledge_id = kb.id "
            "WHERE LOWER(kr.rule_text) LIKE ? OR LOWER(kb.strategies_extracted) LIKE ? "
            "ORDER BY kb.confidence DESC",
            (pattern, pattern)
        ).fetchall()
        conn.close()

        return [
            {
                "rule": row["rule_text"],
                "type": row["rule_type"],
                "source": row["title"],
                "source_type": row["source_type"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def get_indicator_insights(self, indicator: str) -> list:
        """Get all knowledge about a specific indicator."""
        conn = get_connection()
        pattern = f"%{indicator.lower()}%"
        rows = conn.execute(
            "SELECT * FROM knowledge_base "
            "WHERE LOWER(indicators_mentioned) LIKE ? OR LOWER(content) LIKE ? "
            "ORDER BY confidence DESC, times_referenced DESC LIMIT 20",
            (pattern, pattern)
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            # Extract relevant snippets from content
            content = row["content"]
            snippets = self._extract_snippets(content, indicator)
            results.append({
                "title": row["title"],
                "source_type": row["source_type"],
                "confidence": row["confidence"],
                "snippets": snippets,
                "rules": [
                    r for r in json.loads(row["key_rules"] or "[]")
                    if indicator.lower() in r.lower()
                ],
            })
        return results

    def get_evolution_summary(self) -> dict:
        """Summary of how the bot has evolved."""
        conn = get_connection()

        total = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_base").fetchone()["cnt"]

        sources = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM knowledge_base GROUP BY source_type"
        ).fetchall()

        total_rules = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_rules").fetchone()["cnt"]

        most_referenced = conn.execute(
            "SELECT title, source_type, times_referenced FROM knowledge_base "
            "ORDER BY times_referenced DESC LIMIT 5"
        ).fetchall()

        timeline = conn.execute(
            "SELECT DATE(created_at) as date, COUNT(*) as cnt "
            "FROM knowledge_base GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 30"
        ).fetchall()

        all_strategies = conn.execute(
            "SELECT strategies_extracted FROM knowledge_base WHERE strategies_extracted != '[]'"
        ).fetchall()

        all_indicators = conn.execute(
            "SELECT indicators_mentioned FROM knowledge_base WHERE indicators_mentioned != '[]'"
        ).fetchall()

        conn.close()

        # Count unique strategies and indicators
        unique_strategies = set()
        for row in all_strategies:
            for s in json.loads(row["strategies_extracted"] or "[]"):
                unique_strategies.add(s)

        unique_indicators = set()
        for row in all_indicators:
            for i in json.loads(row["indicators_mentioned"] or "[]"):
                unique_indicators.add(i)

        return {
            "total_entries": total,
            "sources_breakdown": {row["source_type"]: row["cnt"] for row in sources},
            "total_rules": total_rules,
            "unique_strategies": len(unique_strategies),
            "unique_indicators": len(unique_indicators),
            "strategies_learned": sorted(unique_strategies),
            "indicators_tracked": sorted(unique_indicators),
            "most_referenced": [
                {"title": r["title"], "source": r["source_type"], "references": r["times_referenced"]}
                for r in most_referenced
            ],
            "learning_timeline": [
                {"date": r["date"], "entries_added": r["cnt"]}
                for r in timeline
            ],
        }

    def export_knowledge(self) -> dict:
        """Export all knowledge as portable JSON."""
        conn = get_connection()
        entries = conn.execute("SELECT * FROM knowledge_base ORDER BY created_at").fetchall()
        rules = conn.execute("SELECT * FROM knowledge_rules ORDER BY created_at").fetchall()
        conn.close()

        return {
            "exported_at": datetime.now().isoformat(),
            "entries": [dict(row) for row in entries],
            "rules": [dict(row) for row in rules],
            "summary": self.get_evolution_summary(),
        }

    # --- Private methods ---

    def _store_entry(self, source_type, source_url, title, content,
                     knowledge, confidence, tags) -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO knowledge_base "
            "(source_type, source_url, title, content, strategies_extracted, "
            "indicators_mentioned, patterns_mentioned, key_rules, confidence, tags, "
            "created_at, times_referenced) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                source_type, source_url, title, content,
                json.dumps(knowledge.get("strategies_extracted", [])),
                json.dumps(knowledge.get("indicators_mentioned", [])),
                json.dumps(knowledge.get("patterns_mentioned", [])),
                json.dumps(knowledge.get("key_rules", [])),
                confidence,
                json.dumps(tags),
                datetime.now().isoformat(),
            )
        )
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entry_id

    def _store_rule(self, knowledge_id, rule_text, rule_type="extracted"):
        """Store an individual rule linked to a knowledge entry."""
        # Detect rule type and associated indicator/pattern
        indicator = ""
        pattern = ""

        text_lower = rule_text.lower()
        for ind in INDICATOR_KEYWORDS:
            if ind in text_lower:
                indicator = ind
                break

        for pat in PATTERN_KEYWORDS:
            if pat in text_lower:
                pattern = pat
                break

        if "stop" in text_lower or "risk" in text_lower:
            rule_type = "risk"
        elif "entry" in text_lower or "buy" in text_lower or "sell" in text_lower:
            rule_type = "entry"
        elif "exit" in text_lower or "target" in text_lower or "profit" in text_lower:
            rule_type = "exit"

        conn = get_connection()
        conn.execute(
            "INSERT INTO knowledge_rules (knowledge_id, rule_text, rule_type, "
            "indicator, pattern, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (knowledge_id, rule_text, rule_type, indicator, pattern,
             datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def _extract_trading_knowledge(self, text: str) -> dict:
        """Extract trading knowledge from raw text using keyword analysis."""
        text_lower = text.lower()

        # Find indicators mentioned
        indicators = []
        for keyword in INDICATOR_KEYWORDS:
            if keyword in text_lower:
                indicators.append(keyword)

        # Find patterns mentioned
        patterns = []
        for keyword in PATTERN_KEYWORDS:
            if keyword in text_lower:
                patterns.append(keyword)

        # Extract rules
        rules = []
        for pattern in RULE_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                rule = match.strip()
                if len(rule) > 10 and len(rule) < 200:  # filter noise
                    rules.append(rule)

        # Extract strategy names
        strategies = []
        for pattern in STRATEGY_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                name = match.strip()
                if len(name) > 3 and len(name) < 60:
                    strategies.append(name)

        # Deduplicate
        rules = list(dict.fromkeys(rules))[:20]
        strategies = list(dict.fromkeys(strategies))[:10]

        return {
            "strategies_extracted": strategies,
            "indicators_mentioned": list(set(indicators)),
            "patterns_mentioned": list(set(patterns)),
            "key_rules": rules,
        }

    def _extract_snippets(self, content: str, keyword: str, context_chars=150) -> list:
        """Extract text snippets around a keyword mention."""
        snippets = []
        lower_content = content.lower()
        lower_key = keyword.lower()
        start = 0

        while True:
            idx = lower_content.find(lower_key, start)
            if idx == -1 or len(snippets) >= 5:
                break
            snippet_start = max(0, idx - context_chars)
            snippet_end = min(len(content), idx + len(keyword) + context_chars)
            snippet = content[snippet_start:snippet_end].strip()
            if snippet_start > 0:
                snippet = "..." + snippet
            if snippet_end < len(content):
                snippet = snippet + "..."
            snippets.append(snippet)
            start = idx + len(keyword)

        return snippets

    def _row_to_entry(self, row) -> dict:
        return {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_url": row["source_url"],
            "title": row["title"],
            "strategies_extracted": json.loads(row["strategies_extracted"] or "[]"),
            "indicators_mentioned": json.loads(row["indicators_mentioned"] or "[]"),
            "patterns_mentioned": json.loads(row["patterns_mentioned"] or "[]"),
            "key_rules": json.loads(row["key_rules"] or "[]"),
            "confidence": row["confidence"],
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"],
            "times_referenced": row["times_referenced"],
        }


def init_knowledge_base():
    """Initialize the knowledge base. Called from main.py."""
    return KnowledgeBase()
