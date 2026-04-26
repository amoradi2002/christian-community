"""
Evolving Knowledge Base — Enhanced with structured extraction, sentence-level
analysis, deduplication, confidence scoring, and validation tracking.

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
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from bot.db.database import get_connection
from bot.config.settings import CONFIG

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────
_KB_CFG = CONFIG.get("knowledge", {})
_MIN_RELEVANCE = _KB_CFG.get("min_relevance_score", 0.3)
_DEDUP_THRESHOLD = _KB_CFG.get("dedup_similarity_threshold", 0.7)
_MIN_CONFIDENCE = _KB_CFG.get("min_rule_confidence", 0.3)
_MAX_RULES_PER_SOURCE = _KB_CFG.get("max_rules_per_source", 50)

CATEGORIES = _KB_CFG.get("categories", [
    "entry_rules", "exit_rules", "risk_rules", "market_structure",
    "psychology", "indicator_usage", "pattern_rules",
])


# ─── Indicator and pattern keyword lists ─────────────────────

INDICATOR_KEYWORDS = [
    "rsi", "macd", "bollinger band", "moving average", "sma", "ema",
    "vwap", "atr", "volume", "relative volume", "rvol", "obv",
    "stochastic", "fibonacci", "ichimoku", "adx", "cci", "williams %r",
    "parabolic sar", "pivot point", "support", "resistance",
    "50 sma", "200 sma", "8 ema", "20 ema", "50 ema", "9 ema", "21 ema",
    "rsi 14", "rsi 7", "macd histogram", "macd crossover",
    "bollinger squeeze", "bb upper", "bb lower", "bb middle",
    "keltner channel", "donchian channel", "heikin ashi",
    "money flow", "accumulation distribution", "chaikin",
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

TRADING_TERMS = set(INDICATOR_KEYWORDS + PATTERN_KEYWORDS + [
    "stop loss", "take profit", "risk reward", "position size", "entry",
    "exit", "breakout", "pullback", "reversal", "trend", "momentum",
    "swing trade", "day trade", "scalp", "options", "premium",
    "strike price", "expiration", "call", "put", "spread",
    "support", "resistance", "consolidation", "accumulation",
])

# ─── Structured Extraction Templates ────────────────────────

STRATEGY_TEMPLATES = [
    {"pattern": r"(?:when|if|once)\s+(.{10,80}?)\s*,?\s*(?:buy|go long|enter long|take a long)",
     "type": "entry_rules", "direction": "long"},
    {"pattern": r"(?:when|if|once)\s+(.{10,80}?)\s*,?\s*(?:sell|go short|enter short|take a short)",
     "type": "entry_rules", "direction": "short"},
    {"pattern": r"(?:stop loss|stop out|cut|exit)\s+(?:at|if|when)\s+(.{10,60})",
     "type": "risk_rules", "direction": ""},
    {"pattern": r"(?:take profit|target|exit|close)\s+(?:at|when|if)\s+(.{10,60})",
     "type": "exit_rules", "direction": ""},
    {"pattern": r"(?:never|don't|do not|avoid)\s+(?:trade|buy|sell|enter)\s+(.{10,60})",
     "type": "psychology", "direction": ""},
    {"pattern": r"(?:always|must|rule)\s*:?\s+(.{10,80})",
     "type": "psychology", "direction": ""},
    {"pattern": r"(?:risk|position size)\s+(?:no more than|max|maximum|only)\s+(.{10,60})",
     "type": "risk_rules", "direction": ""},
    {"pattern": r"(\d+(?:\.\d+)?%\s+(?:risk|stop|target|position|per trade|daily).{5,60})",
     "type": "risk_rules", "direction": ""},
    {"pattern": r"(?:risk.?reward|r:r|r/r)\s*(?:of|at least|minimum|ratio)?\s*([\d.:]+.{5,40})",
     "type": "risk_rules", "direction": ""},
]

INDICATOR_EXTRACTION = re.compile(
    r"(rsi|macd|sma|ema|vwap|atr|adx|obv|bollinger|stochastic)"
    r"\s*\(?\s*(\d+)?\s*\)?\s*(above|below|over|under|crosses?|at|near)\s*(\d+[\.\d]*)?",
    re.IGNORECASE
)


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate word-overlap similarity between two strings."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _sentence_relevance(sentence: str) -> float:
    """Score how relevant a sentence is to trading (0-1)."""
    lower = sentence.lower()
    score = 0.0
    term_count = 0
    for term in TRADING_TERMS:
        if term in lower:
            term_count += 1
    # Bonus for numbers (specific values are more useful)
    numbers = len(re.findall(r'\d+\.?\d*', sentence))
    score = min(1.0, (term_count * 0.15) + (numbers * 0.05))
    return score


def _split_sentences(text: str) -> list:
    """Split text into sentences."""
    # Split on period, exclamation, question mark, or newline
    sentences = re.split(r'[.!?\n]+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def init_knowledge_tables():
    """Create knowledge base tables with enhanced schema."""
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
            category TEXT DEFAULT '',
            direction TEXT DEFAULT '',
            indicator TEXT DEFAULT '',
            indicator_period INTEGER DEFAULT 0,
            condition TEXT DEFAULT '',
            condition_value TEXT DEFAULT '',
            pattern TEXT DEFAULT '',
            confidence REAL DEFAULT 0.5,
            times_validated INTEGER DEFAULT 0,
            times_profitable INTEGER DEFAULT 0,
            sentence_context TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (knowledge_id) REFERENCES knowledge_base(id)
        );

        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            url TEXT DEFAULT '',
            quality_score REAL DEFAULT 0.5,
            rules_extracted INTEGER DEFAULT 0,
            profitable_rules INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_kb_source_type ON knowledge_base(source_type);
        CREATE INDEX IF NOT EXISTS idx_kb_tags ON knowledge_base(tags);
        CREATE INDEX IF NOT EXISTS idx_kr_rule_type ON knowledge_rules(rule_type);
        CREATE INDEX IF NOT EXISTS idx_kr_category ON knowledge_rules(category);
        CREATE INDEX IF NOT EXISTS idx_kr_indicator ON knowledge_rules(indicator);
        CREATE INDEX IF NOT EXISTS idx_kr_confidence ON knowledge_rules(confidence);
    """)
    conn.close()


class KnowledgeBase:
    def __init__(self):
        init_knowledge_tables()

    def ingest_youtube(self, url: str) -> dict:
        """Process a YouTube video and extract trading knowledge."""
        try:
            from bot.learning.youtube import process_video
            result = process_video(url)
        except Exception as e:
            logger.error("YouTube ingestion failed: %s", e)
            return {"status": "error", "message": str(e)}

        if result.get("status") != "success":
            return result

        transcript = result.get("transcript", "")
        title = result.get("title", url)

        knowledge = self._extract_trading_knowledge(transcript)
        strategies_from_vid = [s["name"] for s in result.get("strategies", [])]
        knowledge["strategies_extracted"].extend(strategies_from_vid)
        knowledge["strategies_extracted"] = list(set(knowledge["strategies_extracted"]))

        entry_id = self._store_entry(
            source_type="youtube", source_url=url, title=title,
            content=transcript[:10000], knowledge=knowledge,
            confidence=0.7,
            tags=["youtube", "video"] + knowledge.get("indicators_mentioned", [])[:5],
        )

        rules_stored = self._store_rules_with_dedup(entry_id, knowledge)

        self._track_source(title, "youtube", url, len(knowledge.get("key_rules", [])))

        return {
            "status": "success", "entry_id": entry_id, "title": title,
            "strategies_found": len(knowledge["strategies_extracted"]),
            "indicators_found": len(knowledge["indicators_mentioned"]),
            "patterns_found": len(knowledge["patterns_mentioned"]),
            "rules_extracted": rules_stored,
        }

    def ingest_text(self, title: str, content: str, source_type: str = "manual",
                    source_url: str = "", confidence: float = 0.8) -> dict:
        """Ingest raw text (mentorships, articles, notes)."""
        knowledge = self._extract_trading_knowledge(content)

        entry_id = self._store_entry(
            source_type=source_type, source_url=source_url, title=title,
            content=content[:10000], knowledge=knowledge, confidence=confidence,
            tags=[source_type] + knowledge.get("indicators_mentioned", [])[:5],
        )

        rules_stored = self._store_rules_with_dedup(entry_id, knowledge)
        self._track_source(title, source_type, source_url, rules_stored)

        return {
            "status": "success", "entry_id": entry_id, "title": title,
            "strategies_found": len(knowledge["strategies_extracted"]),
            "indicators_found": len(knowledge["indicators_mentioned"]),
            "patterns_found": len(knowledge["patterns_mentioned"]),
            "rules_extracted": rules_stored,
        }

    def ingest_backtest_results(self, strategy_name: str, results: dict) -> dict:
        """Learn from backtest results — highest confidence source."""
        content = json.dumps(results, indent=2)
        title = f"Backtest: {strategy_name}"

        rules = []
        win_rate = results.get("win_rate", 0)
        sharpe = results.get("sharpe_ratio", 0)
        max_dd = results.get("max_drawdown_pct", results.get("max_drawdown", 0))
        total_return = results.get("total_return_pct", 0)

        if win_rate > 60:
            rules.append({"text": f"{strategy_name} has {win_rate:.0f}% win rate — high confidence", "category": "entry_rules"})
        elif win_rate < 35:
            rules.append({"text": f"{strategy_name} has {win_rate:.0f}% win rate — consider refining", "category": "risk_rules"})

        if sharpe > 1.5:
            rules.append({"text": f"{strategy_name} Sharpe {sharpe:.2f} — excellent risk-adjusted returns", "category": "entry_rules"})
        elif sharpe < 0.5:
            rules.append({"text": f"{strategy_name} Sharpe {sharpe:.2f} — poor risk-adjusted returns", "category": "risk_rules"})

        if max_dd > 20:
            rules.append({"text": f"{strategy_name} max drawdown {max_dd:.1f}% — needs tighter stops", "category": "risk_rules"})

        if total_return > 20:
            rules.append({"text": f"{strategy_name} returned {total_return:.1f}% — profitable strategy", "category": "entry_rules"})

        confidence = min(0.95, 0.5 + (results.get("total_trades", 0) / 200))

        knowledge = {
            "strategies_extracted": [strategy_name],
            "indicators_mentioned": [],
            "patterns_mentioned": [],
            "key_rules": [r["text"] for r in rules],
            "categorized_rules": rules,
        }

        entry_id = self._store_entry(
            source_type="backtest_result", source_url="", title=title,
            content=content[:10000], knowledge=knowledge, confidence=confidence,
            tags=["backtest", strategy_name.lower()],
        )

        for rule in rules:
            self._store_rule(
                entry_id, rule["text"], rule_type="backtest",
                category=rule.get("category", ""), confidence=confidence,
            )

        return {
            "status": "success", "entry_id": entry_id,
            "rules_learned": len(rules), "confidence": confidence,
        }

    def validate_rule(self, rule_id: int, profitable: bool) -> bool:
        """Mark whether a rule led to a profitable trade."""
        try:
            conn = get_connection()
            if profitable:
                conn.execute(
                    "UPDATE knowledge_rules SET times_validated = times_validated + 1, "
                    "times_profitable = times_profitable + 1, "
                    "confidence = MIN(0.99, confidence + 0.05) WHERE id = ?",
                    (rule_id,)
                )
            else:
                conn.execute(
                    "UPDATE knowledge_rules SET times_validated = times_validated + 1, "
                    "confidence = MAX(0.1, confidence - 0.03) WHERE id = ?",
                    (rule_id,)
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Failed to validate rule %d: %s", rule_id, e)
            return False

    def get_best_rules(self, min_confidence: float = 0.7, limit: int = 20) -> list:
        """Get highest-confidence rules."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT kr.*, kb.title as source_title, kb.source_type "
            "FROM knowledge_rules kr JOIN knowledge_base kb ON kr.knowledge_id = kb.id "
            "WHERE kr.confidence >= ? ORDER BY kr.confidence DESC, kr.times_profitable DESC LIMIT ?",
            (min_confidence, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_rules_by_category(self, category: str, limit: int = 20) -> list:
        """Get rules filtered by category."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT kr.*, kb.title as source_title "
            "FROM knowledge_rules kr JOIN knowledge_base kb ON kr.knowledge_id = kb.id "
            "WHERE kr.category = ? ORDER BY kr.confidence DESC LIMIT ?",
            (category, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_source_quality(self) -> list:
        """Rank sources by quality (rules that led to profits)."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM knowledge_sources ORDER BY quality_score DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_knowledge(self, query: str, limit: int = 10) -> list:
        """Search knowledge base."""
        conn = get_connection()
        words = query.lower().split()

        like_clauses = []
        params = []
        for word in words[:5]:
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
            conn.execute(
                "UPDATE knowledge_base SET times_referenced = times_referenced + 1 WHERE id = ?",
                (row["id"],)
            )
            results.append(self._row_to_entry(row))

        conn.commit()
        conn.close()
        return results

    def get_rules_for_setup(self, setup_type: str) -> list:
        """Get all rules relevant to a setup type."""
        conn = get_connection()
        pattern = f"%{setup_type.lower()}%"
        rows = conn.execute(
            "SELECT kr.rule_text, kr.rule_type, kr.category, kr.confidence, "
            "kr.times_validated, kr.times_profitable, kb.title, kb.source_type "
            "FROM knowledge_rules kr "
            "JOIN knowledge_base kb ON kr.knowledge_id = kb.id "
            "WHERE LOWER(kr.rule_text) LIKE ? OR LOWER(kb.strategies_extracted) LIKE ? "
            "ORDER BY kr.confidence DESC",
            (pattern, pattern)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

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
            snippets = self._extract_snippets(row["content"], indicator)
            results.append({
                "title": row["title"],
                "source_type": row["source_type"],
                "confidence": row["confidence"],
                "snippets": snippets,
                "rules": [r for r in json.loads(row["key_rules"] or "[]") if indicator.lower() in r.lower()],
            })
        return results

    def get_evolution_summary(self) -> dict:
        """Summary of knowledge base growth over time."""
        conn = get_connection()

        total = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_base").fetchone()["cnt"]
        sources = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM knowledge_base GROUP BY source_type"
        ).fetchall()
        total_rules = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_rules").fetchone()["cnt"]
        validated_rules = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_rules WHERE times_validated > 0"
        ).fetchone()["cnt"]
        profitable_rules = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_rules WHERE times_profitable > 0"
        ).fetchone()["cnt"]
        most_referenced = conn.execute(
            "SELECT title, source_type, times_referenced FROM knowledge_base "
            "ORDER BY times_referenced DESC LIMIT 5"
        ).fetchall()
        by_category = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM knowledge_rules "
            "WHERE category != '' GROUP BY category"
        ).fetchall()

        all_strategies = conn.execute(
            "SELECT strategies_extracted FROM knowledge_base WHERE strategies_extracted != '[]'"
        ).fetchall()
        all_indicators = conn.execute(
            "SELECT indicators_mentioned FROM knowledge_base WHERE indicators_mentioned != '[]'"
        ).fetchall()
        conn.close()

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
            "validated_rules": validated_rules,
            "profitable_rules": profitable_rules,
            "unique_strategies": len(unique_strategies),
            "unique_indicators": len(unique_indicators),
            "strategies_learned": sorted(unique_strategies),
            "indicators_tracked": sorted(unique_indicators),
            "rules_by_category": {row["category"]: row["cnt"] for row in by_category},
            "most_referenced": [
                {"title": r["title"], "source": r["source_type"], "references": r["times_referenced"]}
                for r in most_referenced
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

    # ─── Private Methods ─────────────────────────────────────

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
                confidence, json.dumps(tags), datetime.now().isoformat(),
            )
        )
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entry_id

    def _store_rule(self, knowledge_id, rule_text, rule_type="extracted",
                    category="", direction="", confidence=0.5, sentence_context=""):
        """Store a rule with full metadata."""
        indicator, period, condition, value = self._extract_indicator_params(rule_text)

        text_lower = rule_text.lower()
        if not category:
            if any(w in text_lower for w in ["stop", "risk", "position size", "never", "don't"]):
                category = "risk_rules"
            elif any(w in text_lower for w in ["buy", "long", "enter", "entry"]):
                category = "entry_rules"
            elif any(w in text_lower for w in ["exit", "target", "profit", "close"]):
                category = "exit_rules"
            elif any(w in text_lower for w in ["patience", "emotion", "revenge", "discipline"]):
                category = "psychology"

        pattern = ""
        for pat in PATTERN_KEYWORDS:
            if pat in text_lower:
                pattern = pat
                break

        # Confidence boost for specific values
        if re.search(r'\d+', rule_text):
            confidence = min(0.95, confidence + 0.1)

        conn = get_connection()
        conn.execute(
            "INSERT INTO knowledge_rules "
            "(knowledge_id, rule_text, rule_type, category, direction, indicator, "
            "indicator_period, condition, condition_value, pattern, confidence, "
            "times_validated, times_profitable, sentence_context, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (knowledge_id, rule_text, rule_type, category, direction,
             indicator, period, condition, value, pattern, confidence,
             sentence_context, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def _store_rules_with_dedup(self, entry_id, knowledge) -> int:
        """Store rules with deduplication against existing rules."""
        existing_rules = self._get_existing_rule_texts()
        stored_count = 0

        categorized = knowledge.get("categorized_rules", [])
        plain_rules = knowledge.get("key_rules", [])

        # Process categorized rules first
        for rule_data in categorized:
            text = rule_data if isinstance(rule_data, str) else rule_data.get("text", "")
            category = "" if isinstance(rule_data, str) else rule_data.get("category", "")
            direction = "" if isinstance(rule_data, str) else rule_data.get("direction", "")
            context = "" if isinstance(rule_data, str) else rule_data.get("context", "")

            if not text or len(text) < 10:
                continue
            if self._is_duplicate(text, existing_rules):
                self._increment_reference(text)
                continue

            self._store_rule(entry_id, text, category=category,
                           direction=direction, sentence_context=context)
            existing_rules.append(text)
            stored_count += 1

            if stored_count >= _MAX_RULES_PER_SOURCE:
                break

        # Process plain rules that weren't in categorized
        for rule_text in plain_rules:
            if stored_count >= _MAX_RULES_PER_SOURCE:
                break
            if not rule_text or len(rule_text) < 10:
                continue
            if self._is_duplicate(rule_text, existing_rules):
                self._increment_reference(rule_text)
                continue

            self._store_rule(entry_id, rule_text)
            existing_rules.append(rule_text)
            stored_count += 1

        return stored_count

    def _is_duplicate(self, text: str, existing: list) -> bool:
        """Check if a rule is too similar to existing ones."""
        for existing_text in existing:
            if _jaccard_similarity(text, existing_text) > _DEDUP_THRESHOLD:
                return True
        return False

    def _increment_reference(self, rule_text: str):
        """Increment reference count for a similar existing rule."""
        try:
            conn = get_connection()
            # Find the most similar existing rule
            rows = conn.execute(
                "SELECT id, rule_text FROM knowledge_rules"
            ).fetchall()
            for row in rows:
                if _jaccard_similarity(rule_text, row["rule_text"]) > _DEDUP_THRESHOLD:
                    conn.execute(
                        "UPDATE knowledge_rules SET confidence = MIN(0.99, confidence + 0.02) WHERE id = ?",
                        (row["id"],)
                    )
                    break
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Reference increment failed: %s", e)

    def _get_existing_rule_texts(self) -> list:
        """Get all existing rule texts for dedup comparison."""
        try:
            conn = get_connection()
            rows = conn.execute("SELECT rule_text FROM knowledge_rules").fetchall()
            conn.close()
            return [r["rule_text"] for r in rows]
        except Exception:
            return []

    def _extract_indicator_params(self, text: str) -> tuple:
        """Extract structured indicator data: (name, period, condition, value)."""
        match = INDICATOR_EXTRACTION.search(text)
        if match:
            name = match.group(1).lower()
            period = int(match.group(2)) if match.group(2) else 0
            condition = match.group(3).lower() if match.group(3) else ""
            value = match.group(4) or ""
            return name, period, condition, value
        return "", 0, "", ""

    def _extract_trading_knowledge(self, text: str) -> dict:
        """Extract knowledge using sentence-level analysis."""
        text_lower = text.lower()

        # Find indicators and patterns
        indicators = [kw for kw in INDICATOR_KEYWORDS if kw in text_lower]
        patterns = [kw for kw in PATTERN_KEYWORDS if kw in text_lower]

        # Sentence-level extraction
        sentences = _split_sentences(text)
        categorized_rules = []
        strategies = []

        for sentence in sentences:
            relevance = _sentence_relevance(sentence)
            if relevance < _MIN_RELEVANCE:
                continue

            # Try structured templates
            for template in STRATEGY_TEMPLATES:
                matches = re.findall(template["pattern"], sentence, re.IGNORECASE)
                for match in matches:
                    rule_text = match.strip()
                    if 10 < len(rule_text) < 200:
                        categorized_rules.append({
                            "text": rule_text,
                            "category": template["type"],
                            "direction": template.get("direction", ""),
                            "context": sentence[:200],
                            "relevance": relevance,
                        })

            # Strategy name extraction
            strategy_match = re.search(
                r"(?:strategy|setup|system)\s*(?:is|called|named|:)\s*(.{3,60}?)(?:\.|,|$)",
                sentence, re.IGNORECASE
            )
            if strategy_match:
                strategies.append(strategy_match.group(1).strip())

        # Deduplicate
        seen_rules = set()
        unique_rules = []
        for rule in categorized_rules:
            key = rule["text"][:50].lower()
            if key not in seen_rules:
                seen_rules.add(key)
                unique_rules.append(rule)

        strategies = list(dict.fromkeys(strategies))[:10]

        return {
            "strategies_extracted": strategies,
            "indicators_mentioned": list(set(indicators)),
            "patterns_mentioned": list(set(patterns)),
            "key_rules": [r["text"] for r in unique_rules[:_MAX_RULES_PER_SOURCE]],
            "categorized_rules": unique_rules[:_MAX_RULES_PER_SOURCE],
        }

    def _track_source(self, title: str, source_type: str, url: str, rules_count: int):
        """Track source quality."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO knowledge_sources (title, source_type, url, quality_score, "
                "rules_extracted, profitable_rules, created_at) VALUES (?, ?, ?, 0.5, ?, 0, ?)",
                (title, source_type, url, rules_count, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Source tracking failed: %s", e)

    def _extract_snippets(self, content: str, keyword: str, context_chars=150) -> list:
        """Extract text snippets around keyword mentions."""
        snippets = []
        lower_content = content.lower()
        lower_key = keyword.lower()
        start = 0
        while True:
            idx = lower_content.find(lower_key, start)
            if idx == -1 or len(snippets) >= 5:
                break
            s = max(0, idx - context_chars)
            e = min(len(content), idx + len(keyword) + context_chars)
            snippet = content[s:e].strip()
            if s > 0:
                snippet = "..." + snippet
            if e < len(content):
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
