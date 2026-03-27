"""
News Sentiment Scoring

Lightweight keyword-based NLP for headline sentiment analysis.
No external ML dependencies — uses curated keyword dictionaries to score
headlines from -1.0 (very bearish) to +1.0 (very bullish).

Usage:
    from bot.engine.news_sentiment import fetch_news_sentiment, score_headline

    result = score_headline("AAPL beats estimates with record revenue growth")
    report = fetch_news_sentiment("AAPL")
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    headline: str
    score: float        # -1.0 (very bearish) to +1.0 (very bullish)
    label: str          # "very_bullish", "bullish", "neutral", "bearish", "very_bearish"
    keywords_found: list
    source: str


# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

BULLISH_WORDS = [
    "beat", "upgrade", "surpass", "record", "growth", "approval", "fda approved",
    "acquisition", "buyback", "dividend increase", "strong earnings", "beat estimates",
    "outperform", "buy rating", "price target raised", "breakthrough", "partnership",
    "expansion", "revenue growth", "profit", "bullish", "rally", "surge", "soar",
]

BEARISH_WORDS = [
    "miss", "downgrade", "cut", "layoff", "recall", "investigation", "lawsuit",
    "bankruptcy", "debt", "loss", "decline", "warning", "weak", "disappoint",
    "sell rating", "price target cut", "fraud", "sec probe", "guidance cut",
    "bearish", "crash", "plunge", "selloff", "default",
]

VERY_BULLISH = ["fda approved", "acquisition", "merger", "10x", "blockbuster"]
VERY_BEARISH = ["bankruptcy", "fraud", "sec charges", "delisted", "criminal"]

# Multi-word phrases get a higher weight because they are more specific.
_PHRASE_WEIGHT = 0.20
_SINGLE_WEIGHT = 0.12
_VERY_WEIGHT = 0.30   # Extra weight for very bullish / very bearish phrases


def _match_keywords(text: str, keywords: list) -> list:
    """Return all keywords found in *text* (case-insensitive)."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def score_headline(headline: str, source: str = "") -> SentimentResult:
    """Score a single headline for sentiment.

    The score is clamped to [-1.0, +1.0].  Multi-word phrases contribute
    more weight than single words because they carry stronger signal.
    """
    bullish_hits = _match_keywords(headline, BULLISH_WORDS)
    bearish_hits = _match_keywords(headline, BEARISH_WORDS)
    very_bull = _match_keywords(headline, VERY_BULLISH)
    very_bear = _match_keywords(headline, VERY_BEARISH)

    score = 0.0
    keywords_found = []

    for kw in bullish_hits:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score += weight
        keywords_found.append(f"+{kw}")

    for kw in bearish_hits:
        weight = _PHRASE_WEIGHT if " " in kw else _SINGLE_WEIGHT
        score -= weight
        keywords_found.append(f"-{kw}")

    for kw in very_bull:
        score += _VERY_WEIGHT
        keywords_found.append(f"++{kw}")

    for kw in very_bear:
        score -= _VERY_WEIGHT
        keywords_found.append(f"--{kw}")

    # Clamp to [-1, 1]
    score = max(-1.0, min(1.0, score))
    score = round(score, 4)

    # Label
    if score >= 0.5:
        label = "very_bullish"
    elif score >= 0.15:
        label = "bullish"
    elif score <= -0.5:
        label = "very_bearish"
    elif score <= -0.15:
        label = "bearish"
    else:
        label = "neutral"

    return SentimentResult(
        headline=headline,
        score=score,
        label=label,
        keywords_found=keywords_found,
        source=source,
    )


def score_headlines(headlines: list, source: str = "") -> list:
    """Score multiple headlines and return them sorted by absolute score (strongest first)."""
    results = [score_headline(h, source=source) for h in headlines]
    results.sort(key=lambda r: abs(r.score), reverse=True)
    return results


def get_overall_sentiment(results: list) -> dict:
    """Aggregate a list of SentimentResults into a summary.

    Returns:
        {
            "avg_score": float,
            "bullish_count": int,
            "bearish_count": int,
            "neutral_count": int,
            "total": int,
            "overall_label": str,
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
        }

    scores = [r.score for r in results]
    avg = sum(scores) / len(scores)
    avg = round(avg, 4)

    bullish_count = sum(1 for r in results if r.label in ("bullish", "very_bullish"))
    bearish_count = sum(1 for r in results if r.label in ("bearish", "very_bearish"))
    neutral_count = sum(1 for r in results if r.label == "neutral")

    if avg >= 0.5:
        overall_label = "very_bullish"
    elif avg >= 0.15:
        overall_label = "bullish"
    elif avg <= -0.5:
        overall_label = "very_bearish"
    elif avg <= -0.15:
        overall_label = "bearish"
    else:
        overall_label = "neutral"

    return {
        "avg_score": avg,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "total": len(results),
        "overall_label": overall_label,
    }


# ---------------------------------------------------------------------------
# News fetching helpers
# ---------------------------------------------------------------------------

def _fetch_finnhub_news(symbol: str) -> Optional[List[str]]:
    """Fetch recent company news headlines from Finnhub.

    Returns a list of headline strings, or None on failure.
    """
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        logger.debug("FINNHUB_API_KEY not set, skipping finnhub news")
        return None

    try:
        import requests
        from datetime import datetime, timedelta

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

        headlines = [a.get("headline", "") for a in articles if a.get("headline")]
        return headlines[:30]  # Cap at 30 most recent

    except Exception as exc:
        logger.warning("Finnhub news fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_yfinance_news(symbol: str) -> Optional[List[str]]:
    """Fallback: pull news titles from yfinance."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        news = ticker.news or []

        headlines = []
        for item in news:
            title = item.get("title", "")
            if not title:
                # Some yfinance versions nest under 'content'
                content = item.get("content", {})
                if isinstance(content, dict):
                    title = content.get("title", "")
            if title:
                headlines.append(title)

        return headlines[:30] if headlines else None

    except Exception as exc:
        logger.warning("yfinance news fetch failed for %s: %s", symbol, exc)
        return None


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
    headlines = _fetch_finnhub_news(symbol)
    source = "finnhub"

    if not headlines:
        headlines = _fetch_yfinance_news(symbol)
        source = "yfinance"

    if not headlines:
        return {
            "symbol": symbol,
            "headlines": [],
            "overall_score": 0.0,
            "overall_label": "neutral",
            "recommendation": "No recent news found — sentiment is unknown.",
            "source": "none",
        }

    results = score_headlines(headlines, source=source)
    overall = get_overall_sentiment(results)

    # Build recommendation string
    avg = overall["avg_score"]
    label = overall["overall_label"]

    if label == "very_bullish":
        recommendation = (
            f"Strong bullish sentiment ({avg:+.2f}). "
            "News flow supports long entries — look for technical confirmation."
        )
    elif label == "bullish":
        recommendation = (
            f"Mildly bullish sentiment ({avg:+.2f}). "
            "Positive headlines — no major red flags in the news."
        )
    elif label == "very_bearish":
        recommendation = (
            f"Strong bearish sentiment ({avg:+.2f}). "
            "Significant negative news — avoid new longs, consider short setups."
        )
    elif label == "bearish":
        recommendation = (
            f"Mildly bearish sentiment ({avg:+.2f}). "
            "Negative headlines present — exercise caution on entries."
        )
    else:
        recommendation = (
            f"Neutral sentiment ({avg:+.2f}). "
            "News is mixed or unremarkable — rely on technical analysis."
        )

    return {
        "symbol": symbol,
        "headlines": results,
        "overall_score": avg,
        "overall_label": label,
        "recommendation": recommendation,
        "source": source,
    }
