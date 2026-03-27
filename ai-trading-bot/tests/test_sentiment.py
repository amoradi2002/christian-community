"""Tests for news sentiment analysis."""
import pytest
from bot.engine.news_sentiment import score_headline, score_headlines, get_overall_sentiment, SentimentResult


class TestSentimentScoring:
    def test_bullish_headline(self):
        result = score_headline("AAPL beats earnings estimates with record revenue growth")
        assert result.score > 0
        assert result.label in ("bullish", "very_bullish")

    def test_bearish_headline(self):
        result = score_headline("Company faces lawsuit and SEC investigation")
        assert result.score < 0
        assert result.label in ("bearish", "very_bearish")

    def test_neutral_headline(self):
        result = score_headline("Company releases quarterly report")
        assert abs(result.score) < 0.15
        assert result.label == "neutral"

    def test_very_bullish(self):
        result = score_headline("FDA approved blockbuster drug acquisition complete")
        assert result.score > 0.3

    def test_very_bearish(self):
        result = score_headline("Company files for bankruptcy amid fraud charges")
        assert result.score < -0.3

    def test_score_clamped(self):
        """Score should be between -1.0 and +1.0."""
        result = score_headline("beat upgrade surpass record growth approval buyback rally surge soar profit bullish")
        assert -1.0 <= result.score <= 1.0

    def test_keywords_found_populated(self):
        result = score_headline("AAPL beats estimates with strong earnings")
        assert len(result.keywords_found) > 0

    def test_result_has_source(self):
        result = score_headline("Test headline", source="finnhub")
        assert result.source == "finnhub"


class TestOverallSentiment:
    def test_empty_results(self):
        overall = get_overall_sentiment([])
        assert overall["total"] == 0
        assert overall["overall_label"] == "neutral"

    def test_bullish_overall(self):
        results = [
            score_headline("Stock surges on record earnings"),
            score_headline("Upgrade and price target raised"),
            score_headline("Revenue growth beats expectations"),
        ]
        overall = get_overall_sentiment(results)
        assert overall["avg_score"] > 0
        assert overall["bullish_count"] > 0

    def test_score_headlines_sorted(self):
        headlines = [
            "Neutral company update",
            "Major bankruptcy filing",
            "Slight growth",
        ]
        results = score_headlines(headlines)
        # Should be sorted by absolute score (strongest first)
        abs_scores = [abs(r.score) for r in results]
        assert abs_scores == sorted(abs_scores, reverse=True)
