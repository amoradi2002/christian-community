"""
News Sentiment Scoring

Keyword-based NLP for headline sentiment analysis with negation handling,
context-aware scoring, source weighting, and sentiment trend detection.

No external ML dependencies -- uses curated keyword dictionaries to score
headlines from -1.0 (very bearish) to +1.0 (very bullish).

Usage:
    from bot.engine.news_sentiment import fetch_news_sentiment, score_headline

    result = score_headline("AAPL beats estimates with record revenue growth")
    report = fetch_news_sentiment("AAPL")

    # Enhanced: context-aware scoring with source/recency weighting
    result = score_headline_enhanced("AAPL beats estimates", source="reuters",
                                     published_days_ago=0)
"""

import os
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SentimentResult:
    """Result of scoring a single headline."""
    headline: str
    score: float        # -1.0 (very bearish) to +1.0 (very bullish)
    label: str          # "very_bullish", "bullish", "neutral", "bearish", "very_bearish"
    keywords_found: list
    source: str


@dataclass
class EnhancedSentimentResult:
    """Extended result with context-aware scoring details."""
    headline: str
    raw_score: float          # score before source/recency adjustments
    adjusted_score: float     # final score after all adjustments
    label: str
    keywords_found: list
    negations_detected: list  # negation phrases that flipped keyword polarity
    source: str
    source_weight: float
    recency_weight: float
    published_days_ago: float


@dataclass
class SentimentTrend:
    """Tracks sentiment direction over time."""
    current_score: float       # latest aggregate score
    previous_score: float      # aggregate score from prior period
    direction: str             # "improving", "deteriorating", "stable"
    shift_magnitude: float     # absolute change
    is_reversal: bool          # sentiment polarity flipped
    day_scores: list           # list of (date_str, avg_score) tuples
    description: str


# ---------------------------------------------------------------------------
# Negation handling
# ---------------------------------------------------------------------------

NEGATION_WORDS = [
    "not", "no", "never", "isn't", "doesn't", "won't", "can't", "couldn't",
    "shouldn't", "wouldn't", "didn't", "hasn't", "haven't", "hadn't",
    "failed to", "unable to", "lack of", "failing to", "without",
    "barely", "hardly", "neither", "nor", "despite not",
]

# Pre-compile for performance: sort by length descending so longer phrases match first
_NEGATION_PATTERNS = sorted(NEGATION_WORDS, key=len, reverse=True)

_NEGATION_WINDOW = 3  # check N words before each keyword for negation


def _has_negation(text_lower: str, keyword: str) -> Optional[str]:
    """Check if a negation word appears within _NEGATION_WINDOW words before *keyword*.

    Returns the negation word found, or None.
    """
    kw_pos = text_lower.find(keyword.lower())
    if kw_pos < 0:
        return None

    # Get the text window before the keyword
    prefix = text_lower[:kw_pos].strip()
    prefix_words = prefix.split()

    # Check last N words for single-word negations
    window_words = prefix_words[-_NEGATION_WINDOW:] if prefix_words else []
    window_text = " ".join(window_words)

    for neg in _NEGATION_PATTERNS:
        if " " in neg:
            # Multi-word negation: check in the window text
            if neg in window_text:
                return neg
        else:
            # Single-word negation
            if neg in window_words:
                return neg

    return None


# ---------------------------------------------------------------------------
# Keyword dictionaries (100+ terms)
# ---------------------------------------------------------------------------

BULLISH_WORDS = [
    # Earnings & fundamentals
    "beat", "beats", "upgrade", "surpass", "record", "growth", "approval",
    "fda approved", "acquisition", "buyback", "dividend increase",
    "strong earnings", "beat estimates", "outperform", "buy rating",
    "price target raised", "breakthrough", "partnership", "expansion",
    "revenue growth", "profit", "profitability", "margin expansion",
    "raised guidance", "guidance raised", "upside surprise",
    "revenue beat", "eps beat", "record revenue", "record profit",
    "analyst upgrade", "double upgrade", "initiated buy",
    "strong demand", "backlog growth", "market share gain",
    "positive data", "positive results", "accelerating growth",
    "exceeded expectations", "all-time high",
    # Trading-specific
    "bullish", "rally", "surge", "soar", "breakout", "gap up",
    "short squeeze", "oversold bounce", "accumulation",
    "golden cross", "new highs", "parabolic",
    "squeeze", "melt up", "risk on",
    # Options-specific
    "unusual options activity", "call sweep", "gamma squeeze",
    "call buying", "bullish flow", "bullish options",
    # Macro positive
    "rate cut", "fed pivot", "quantitative easing", "soft landing",
    "disinflation", "cooling inflation", "jobs growth",
    "gdp growth", "economic expansion", "stimulus",
    "consumer confidence", "crypto rally", "bitcoin rally",
]

BEARISH_WORDS = [
    # Earnings & fundamentals
    "miss", "misses", "downgrade", "cut", "layoff", "layoffs", "recall",
    "investigation", "lawsuit", "bankruptcy", "debt", "loss", "losses",
    "decline", "warning", "weak", "disappoint", "disappointing",
    "sell rating", "price target cut", "fraud", "sec probe",
    "guidance cut", "lowered guidance", "guidance lowered",
    "revenue miss", "eps miss", "missed estimates",
    "analyst downgrade", "double downgrade", "initiated sell",
    "weak demand", "margin compression", "market share loss",
    "negative data", "negative results", "decelerating growth",
    "below expectations", "restructuring", "write-down",
    "impairment", "going concern", "cash burn",
    # Trading-specific
    "bearish", "crash", "plunge", "selloff", "sell-off", "default",
    "breakdown", "gap down", "dead cat bounce", "capitulation",
    "distribution", "death cross", "new lows", "free fall",
    "risk off", "flash crash",
    # Options-specific
    "put sweep", "iv crush", "bearish flow", "put buying",
    "bearish options", "unusual put activity",
    # Macro negative
    "rate hike", "quantitative tightening", "inflation",
    "recession", "hard landing", "stagflation",
    "rising inflation", "hawkish", "inverted yield curve",
    "unemployment rising", "job losses", "gdp contraction",
    "economic slowdown", "crypto crash", "bitcoin crash",
    "bank run", "contagion", "systemic risk",
]

VERY_BULLISH = [
    "fda approved", "acquisition", "merger", "10x", "blockbuster",
    "transformative deal", "record quarter", "massive beat",
    "blowout earnings", "game changer", "breakthrough drug",
    "doubled revenue", "tripled revenue", "historic",
    "landmark deal", "short squeeze", "gamma squeeze",
]

VERY_BEARISH = [
    "bankruptcy", "fraud", "sec charges", "delisted", "criminal",
    "ponzi", "class action", "criminal investigation",
    "executive arrested", "accounting fraud", "massive layoffs",
    "default", "insolvency", "liquidation", "bank failure",
    "systemic risk", "margin call", "forced selling",
    "flash crash", "circuit breaker",
]

# Multi-word phrases get a higher weight because they are more specific.
_PHRASE_WEIGHT = 0.20
_SINGLE_WEIGHT = 0.12
_VERY_WEIGHT = 0.30   # Extra weight for very bullish / very bearish phrases

# ---------------------------------------------------------------------------
# Source weighting
# ---------------------------------------------------------------------------

_SOURCE_WEIGHTS: Dict[str, float] = {
    # Premium / high-credibility
    "reuters": 1.5,
    "bloomberg": 1.5,
    "wsj": 1.4,
    "wall street journal": 1.4,
    "financial times": 1.4,
    "ft": 1.4,
    "barrons": 1.3,
    "cnbc": 1.2,
    "marketwatch": 1.2,
    "sec filing": 1.5,
    "sec": 1.5,
    "finnhub": 1.0,
    "yfinance": 1.0,
    # Social / lower credibility
    "twitter": 0.5,
    "x": 0.5,
    "reddit": 0.5,
    "stocktwits": 0.5,
    "seeking alpha": 0.7,
    "motley fool": 0.6,
    "benzinga": 0.8,
    "investorplace": 0.6,
    "social media": 0.5,
}


def _get_source_weight(source: str) -> float:
    """Return credibility multiplier for a news source."""
    if not source:
        return 1.0
    source_lower = source.lower().strip()
    for key, weight in _SOURCE_WEIGHTS.items():
        if key in source_lower:
            return weight
    return 1.0


def _get_recency_weight(days_ago: float) -> float:
    """Return recency multiplier. Today = 1.0, decays over a week."""
    if days_ago <= 0:
        return 1.0
    if days_ago <= 1:
        return 0.95
    if days_ago <= 3:
        return 0.7
    if days_ago <= 5:
        return 0.55
    if days_ago <= 7:
        return 0.4
    return 0.2


# ---------------------------------------------------------------------------
# Keyword matching (with negation)
# ---------------------------------------------------------------------------

def _match_keywords(text: str, keywords: list) -> list:
    """Return all keywords found in *text* (case-insensitive)."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def _match_keywords_negation_aware(
    text: str,
    keywords: list,
) -> Tuple[list, list, list]:
    """Match keywords with negation detection.

    Returns:
        (matched_keywords, negated_keywords, negation_phrases)
    """
    text_lower = text.lower()
    matched = []
    negated = []
    negation_phrases = []

    for kw in keywords:
        if kw.lower() in text_lower:
            neg = _has_negation(text_lower, kw.lower())
            if neg:
                negated.append(kw)
                negation_phrases.append(f'"{neg}" before "{kw}"')
            else:
                matched.append(kw)

    return matched, negated, negation_phrases


# ---------------------------------------------------------------------------
# Scoring functions (backward-compatible originals + enhanced versions)
# ---------------------------------------------------------------------------

def score_headline(headline: str, source: str = "") -> SentimentResult:
    """Score a single headline for sentiment.

    The score is clamped to [-1.0, +1.0].  Multi-word phrases contribute
    more weight than single words because they carry stronger signal.

    Now includes negation handling: a negated bullish keyword counts as
    bearish and vice versa.
    """
    text_lower = headline.lower()

    # Match with negation awareness
    bull_matched, bull_negated, bull_neg_phrases = _match_keywords_negation_aware(
        headline, BULLISH_WORDS,
    )
    bear_matched, bear_negated, bear_neg_phrases = _match_keywords_negation_aware(
        headline, BEARISH_WORDS,
    )
    very_bull_matched, very_bull_negated, _ = _match_keywords_negation_aware(
        headline, VERY_BULLISH,
    )
    very_bear_matched, very_bear_negated, _ = _match_keywords_negation_aware(
        headline, VERY_BEARISH,
    )

    score = 0.0
    keywords_found = []

    # Bullish keywords: add score
    for kw in bull_matched:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score += weight
        keywords_found.append(f"+{kw}")

    # Negated bullish keywords: subtract score (negation flips polarity)
    for kw in bull_negated:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score -= weight
        keywords_found.append(f"~neg+{kw}")

    # Bearish keywords: subtract score
    for kw in bear_matched:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score -= weight
        keywords_found.append(f"-{kw}")

    # Negated bearish keywords: add score (negation flips polarity)
    for kw in bear_negated:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score += weight
        keywords_found.append(f"~neg-{kw}")

    # Very bullish
    for kw in very_bull_matched:
        score += _VERY_WEIGHT
        keywords_found.append(f"++{kw}")
    for kw in very_bull_negated:
        score -= _VERY_WEIGHT
        keywords_found.append(f"~neg++{kw}")

    # Very bearish
    for kw in very_bear_matched:
        score -= _VERY_WEIGHT
        keywords_found.append(f"--{kw}")
    for kw in very_bear_negated:
        score += _VERY_WEIGHT
        keywords_found.append(f"~neg--{kw}")

    # Clamp to [-1, 1]
    score = max(-1.0, min(1.0, score))
    score = round(score, 4)

    label = _score_to_label(score)

    return SentimentResult(
        headline=headline,
        score=score,
        label=label,
        keywords_found=keywords_found,
        source=source,
    )


def score_headline_enhanced(
    headline: str,
    source: str = "",
    published_days_ago: float = 0.0,
) -> EnhancedSentimentResult:
    """Score a headline with source weighting, recency, and negation.

    Returns an EnhancedSentimentResult with full details.
    """
    # Get the raw score from the base scorer
    base = score_headline(headline, source=source)
    raw_score = base.score

    # Collect negation info
    _, bull_negated, bull_neg_phrases = _match_keywords_negation_aware(headline, BULLISH_WORDS)
    _, bear_negated, bear_neg_phrases = _match_keywords_negation_aware(headline, BEARISH_WORDS)
    negations = bull_neg_phrases + bear_neg_phrases

    # Apply source and recency weights
    source_w = _get_source_weight(source)
    recency_w = _get_recency_weight(published_days_ago)

    adjusted = raw_score * source_w * recency_w
    adjusted = max(-1.0, min(1.0, adjusted))
    adjusted = round(adjusted, 4)

    label = _score_to_label(adjusted)

    return EnhancedSentimentResult(
        headline=headline,
        raw_score=raw_score,
        adjusted_score=adjusted,
        label=label,
        keywords_found=base.keywords_found,
        negations_detected=negations,
        source=source,
        source_weight=source_w,
        recency_weight=recency_w,
        published_days_ago=published_days_ago,
    )


def _score_to_label(score: float) -> str:
    """Convert a numeric score to a sentiment label."""
    if score >= 0.5:
        return "very_bullish"
    if score >= 0.15:
        return "bullish"
    if score <= -0.5:
        return "very_bearish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def score_headlines(headlines: list, source: str = "") -> list:
    """Score multiple headlines and return them sorted by absolute score (strongest first)."""
    results = [score_headline(h, source=source) for h in headlines]
    results.sort(key=lambda r: abs(r.score), reverse=True)
    return results


def score_headlines_enhanced(
    headline_entries: List[dict],
) -> List[EnhancedSentimentResult]:
    """Score multiple headlines with full context.

    Args:
        headline_entries: list of dicts, each with keys:
            - "headline" (str, required)
            - "source" (str, optional)
            - "published_days_ago" (float, optional)

    Returns:
        List of EnhancedSentimentResult sorted by absolute adjusted score.
    """
    results = []
    for entry in headline_entries:
        headline = entry.get("headline", "")
        if not headline:
            continue
        result = score_headline_enhanced(
            headline,
            source=entry.get("source", ""),
            published_days_ago=entry.get("published_days_ago", 0.0),
        )
        results.append(result)

    results.sort(key=lambda r: abs(r.adjusted_score), reverse=True)
    return results


def get_overall_sentiment(results: list) -> dict:
    """Aggregate a list of SentimentResults into a summary.

    Works with both SentimentResult and EnhancedSentimentResult objects.

    Returns:
        {
            "avg_score": float,
            "bullish_count": int,
            "bearish_count": int,
            "neutral_count": int,
            "total": int,
            "overall_label": str,
            "contested": bool,
        }
    """
    if not results:
        return {
            "avg_score": 0.0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "total": 0,
            "overall_label": "neutral",
            "contested": False,
        }

    # Support both result types
    scores = []
    for r in results:
        if hasattr(r, "adjusted_score"):
            scores.append(r.adjusted_score)
        else:
            scores.append(r.score)

    avg = round(sum(scores) / len(scores), 4)

    bullish_count = sum(1 for r in results if r.label in ("bullish", "very_bullish"))
    bearish_count = sum(1 for r in results if r.label in ("bearish", "very_bearish"))
    neutral_count = sum(1 for r in results if r.label == "neutral")

    # Contradiction detection: roughly equal bullish and bearish
    total_opinionated = bullish_count + bearish_count
    contested = False
    if total_opinionated >= 4:
        ratio = min(bullish_count, bearish_count) / max(bullish_count, bearish_count, 1)
        contested = ratio > 0.6  # 60%+ balance = contested

    overall_label = _score_to_label(avg)
    if contested:
        overall_label = "contested"

    return {
        "avg_score": avg,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "total": len(results),
        "overall_label": overall_label,
        "contested": contested,
    }


def get_overall_sentiment_enhanced(results: List[EnhancedSentimentResult]) -> dict:
    """Aggregate enhanced results with coverage volume amplification.

    Returns the same dict as get_overall_sentiment plus additional keys:
        - "volume_factor": amplification based on article count
        - "contested": bool
        - "signal_strength": "strong", "moderate", "weak"
    """
    base = get_overall_sentiment(results)

    # Volume amplification: more articles on same direction = stronger signal
    total = base["total"]
    if total == 0:
        base["volume_factor"] = 1.0
        base["signal_strength"] = "weak"
        return base

    # Volume factor: 1-5 articles = 1.0, 6-15 = 1.2, 16+ = 1.4
    if total <= 5:
        volume_factor = 1.0
    elif total <= 15:
        volume_factor = 1.2
    else:
        volume_factor = 1.4

    base["volume_factor"] = volume_factor

    # Adjust avg_score by volume factor (still clamped)
    amplified = base["avg_score"] * volume_factor
    amplified = max(-1.0, min(1.0, amplified))
    base["avg_score"] = round(amplified, 4)

    # Recalculate label after amplification
    if not base["contested"]:
        base["overall_label"] = _score_to_label(base["avg_score"])

    # Signal strength
    abs_score = abs(base["avg_score"])
    if abs_score >= 0.4:
        base["signal_strength"] = "strong"
    elif abs_score >= 0.15:
        base["signal_strength"] = "moderate"
    else:
        base["signal_strength"] = "weak"

    return base


# ---------------------------------------------------------------------------
# Sentiment trend tracking
# ---------------------------------------------------------------------------

# In-memory store for sentiment history (symbol -> list of (datetime, score))
_sentiment_history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)


def _record_sentiment(symbol: str, score: float, timestamp: Optional[datetime] = None):
    """Record a sentiment data point for trend tracking."""
    ts = timestamp or datetime.now()
    _sentiment_history[symbol].append((ts, score))

    # Prune entries older than 14 days
    cutoff = datetime.now() - timedelta(days=14)
    _sentiment_history[symbol] = [
        (t, s) for t, s in _sentiment_history[symbol] if t > cutoff
    ]


def get_sentiment_trend(symbol: str, lookback_days: int = 7) -> SentimentTrend:
    """Analyze sentiment trend over time for a symbol.

    Splits the lookback window into two halves and compares average sentiment.

    Returns:
        SentimentTrend with direction and reversal detection.
    """
    symbol = symbol.upper()
    history = _sentiment_history.get(symbol, [])

    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = [(t, s) for t, s in history if t > cutoff]

    if len(recent) < 2:
        return SentimentTrend(
            current_score=recent[-1][1] if recent else 0.0,
            previous_score=0.0,
            direction="stable",
            shift_magnitude=0.0,
            is_reversal=False,
            day_scores=[],
            description="Not enough sentiment history for trend analysis.",
        )

    # Group by date
    day_buckets: Dict[str, List[float]] = defaultdict(list)
    for ts, score in recent:
        day_key = ts.strftime("%Y-%m-%d")
        day_buckets[day_key].append(score)

    day_scores = sorted([
        (day, round(sum(scores) / len(scores), 4))
        for day, scores in day_buckets.items()
    ])

    # Split into first half and second half
    mid = len(recent) // 2
    first_half = [s for _, s in recent[:mid]]
    second_half = [s for _, s in recent[mid:]]

    prev_avg = sum(first_half) / len(first_half) if first_half else 0.0
    curr_avg = sum(second_half) / len(second_half) if second_half else 0.0

    shift = curr_avg - prev_avg
    abs_shift = abs(shift)

    # Direction
    if abs_shift < 0.05:
        direction = "stable"
    elif shift > 0:
        direction = "improving"
    else:
        direction = "deteriorating"

    # Reversal detection: polarity flipped
    is_reversal = (prev_avg > 0.1 and curr_avg < -0.1) or (prev_avg < -0.1 and curr_avg > 0.1)

    # Description
    if is_reversal:
        if curr_avg > prev_avg:
            desc = (
                f"Sentiment reversal detected: was bearish ({prev_avg:+.2f}), "
                f"now turning bullish ({curr_avg:+.2f}). Potential reversal signal."
            )
        else:
            desc = (
                f"Sentiment reversal detected: was bullish ({prev_avg:+.2f}), "
                f"now turning bearish ({curr_avg:+.2f}). Potential top signal."
            )
    elif direction == "improving":
        desc = f"Sentiment improving: {prev_avg:+.2f} -> {curr_avg:+.2f} over {lookback_days} days."
    elif direction == "deteriorating":
        desc = f"Sentiment deteriorating: {prev_avg:+.2f} -> {curr_avg:+.2f} over {lookback_days} days."
    else:
        desc = f"Sentiment stable around {curr_avg:+.2f} over {lookback_days} days."

    return SentimentTrend(
        current_score=round(curr_avg, 4),
        previous_score=round(prev_avg, 4),
        direction=direction,
        shift_magnitude=round(abs_shift, 4),
        is_reversal=is_reversal,
        day_scores=day_scores,
        description=desc,
    )


# ---------------------------------------------------------------------------
# News fetching helpers
# ---------------------------------------------------------------------------

def _fetch_finnhub_news(symbol: str) -> Optional[List[dict]]:
    """Fetch recent company news from Finnhub.

    Returns a list of dicts with 'headline', 'source', 'datetime' keys,
    or None on failure.
    """
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        logger.debug("FINNHUB_API_KEY not set, skipping finnhub news")
        return None

    try:
        import requests

        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol.upper(),
                "from": week_ago,
                "to": today,
                "token": token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json()

        if not isinstance(articles, list):
            return None

        results = []
        now = datetime.now()
        for a in articles:
            headline = a.get("headline", "")
            if not headline:
                continue

            source = a.get("source", "finnhub")
            # Calculate days ago from epoch timestamp
            epoch = a.get("datetime", 0)
            if epoch:
                pub_time = datetime.fromtimestamp(epoch)
                days_ago = (now - pub_time).total_seconds() / 86400.0
            else:
                days_ago = 0.0

            results.append({
                "headline": headline,
                "source": source,
                "published_days_ago": max(0.0, round(days_ago, 2)),
            })

        return results[:30] if results else None

    except Exception as exc:
        logger.warning("Finnhub news fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_yfinance_news(symbol: str) -> Optional[List[dict]]:
    """Fallback: pull news from yfinance."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        news = ticker.news or []

        results = []
        now = datetime.now()
        for item in news:
            title = item.get("title", "")
            if not title:
                content = item.get("content", {})
                if isinstance(content, dict):
                    title = content.get("title", "")
            if not title:
                continue

            source = item.get("publisher", "yfinance")
            if not source:
                source = "yfinance"

            # Estimate days ago from providerPublishTime
            pub_ts = item.get("providerPublishTime", 0)
            if pub_ts:
                pub_time = datetime.fromtimestamp(pub_ts)
                days_ago = (now - pub_time).total_seconds() / 86400.0
            else:
                days_ago = 0.0

            results.append({
                "headline": title,
                "source": source,
                "published_days_ago": max(0.0, round(days_ago, 2)),
            })

        return results[:30] if results else None

    except Exception as exc:
        logger.warning("yfinance news fetch failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Public API -- backward compatible
# ---------------------------------------------------------------------------

def fetch_news_sentiment(symbol: str) -> dict:
    """Fetch recent news for a symbol and score sentiment.

    Tries Finnhub first, falls back to yfinance.

    Returns:
        {
            "symbol": str,
            "headlines": [SentimentResult, ...],
            "overall_score": float,
            "overall_label": str,
            "recommendation": str,
            "source": str,
        }
    """
    symbol = symbol.upper()

    # Try sources in order
    articles = _fetch_finnhub_news(symbol)
    source = "finnhub"

    if not articles:
        articles = _fetch_yfinance_news(symbol)
        source = "yfinance"

    if not articles:
        return {
            "symbol": symbol,
            "headlines": [],
            "overall_score": 0.0,
            "overall_label": "neutral",
            "recommendation": "No recent news found -- sentiment is unknown.",
            "source": "none",
        }

    # Score using the basic scorer for backward compatibility
    headlines_text = [a["headline"] for a in articles]
    results = score_headlines(headlines_text, source=source)
    overall = get_overall_sentiment(results)

    # Record for trend tracking
    _record_sentiment(symbol, overall["avg_score"])

    avg = overall["avg_score"]
    label = overall["overall_label"]
    recommendation = _build_recommendation(avg, label, overall.get("contested", False))

    return {
        "symbol": symbol,
        "headlines": results,
        "overall_score": avg,
        "overall_label": label,
        "recommendation": recommendation,
        "source": source,
    }


def fetch_news_sentiment_enhanced(symbol: str) -> dict:
    """Fetch recent news with full context-aware scoring.

    Returns:
        {
            "symbol": str,
            "headlines": [EnhancedSentimentResult, ...],
            "overall_score": float,
            "overall_label": str,
            "contested": bool,
            "signal_strength": str,
            "volume_factor": float,
            "recommendation": str,
            "sentiment_trend": SentimentTrend,
            "source": str,
        }
    """
    symbol = symbol.upper()

    articles = _fetch_finnhub_news(symbol)
    source = "finnhub"

    if not articles:
        articles = _fetch_yfinance_news(symbol)
        source = "yfinance"

    if not articles:
        return {
            "symbol": symbol,
            "headlines": [],
            "overall_score": 0.0,
            "overall_label": "neutral",
            "contested": False,
            "signal_strength": "weak",
            "volume_factor": 1.0,
            "recommendation": "No recent news found -- sentiment is unknown.",
            "sentiment_trend": get_sentiment_trend(symbol),
            "source": "none",
        }

    # Score with enhanced context
    results = score_headlines_enhanced(articles)
    overall = get_overall_sentiment_enhanced(results)

    # Record for trend tracking
    _record_sentiment(symbol, overall["avg_score"])

    avg = overall["avg_score"]
    label = overall["overall_label"]
    contested = overall.get("contested", False)
    recommendation = _build_recommendation(avg, label, contested)

    trend = get_sentiment_trend(symbol)

    return {
        "symbol": symbol,
        "headlines": results,
        "overall_score": avg,
        "overall_label": label,
        "contested": contested,
        "signal_strength": overall.get("signal_strength", "weak"),
        "volume_factor": overall.get("volume_factor", 1.0),
        "recommendation": recommendation,
        "sentiment_trend": trend,
        "source": source,
    }


def _build_recommendation(avg: float, label: str, contested: bool) -> str:
    """Build a human-readable recommendation string."""
    if contested:
        return (
            f"Contested sentiment ({avg:+.2f}). "
            "Bullish and bearish headlines roughly balanced -- the market is "
            "debating this name. Rely on technical analysis and be cautious."
        )

    if label == "very_bullish":
        return (
            f"Strong bullish sentiment ({avg:+.2f}). "
            "News flow supports long entries -- look for technical confirmation."
        )
    if label == "bullish":
        return (
            f"Mildly bullish sentiment ({avg:+.2f}). "
            "Positive headlines -- no major red flags in the news."
        )
    if label == "very_bearish":
        return (
            f"Strong bearish sentiment ({avg:+.2f}). "
            "Significant negative news -- avoid new longs, consider short setups."
        )
    if label == "bearish":
        return (
            f"Mildly bearish sentiment ({avg:+.2f}). "
            "Negative headlines present -- exercise caution on entries."
        )
    return (
        f"Neutral sentiment ({avg:+.2f}). "
        "News is mixed or unremarkable -- rely on technical analysis."
    )
