"""
Continuous Knowledge Crawler — 24/7 Autonomous Learning

Runs in the background and continuously ingests trading knowledge from:
- YouTube channels (top trading educators)
- Financial news articles (via RSS + web scraping)
- Reddit threads (r/options, r/daytrading, r/stocks, r/wallstreetbets)
- Finviz news and analysis
- Earnings transcripts and analysis

The crawler runs on a schedule:
- YouTube channels: every 6 hours (checks for new videos)
- News articles: every 30 minutes
- Reddit: every 2 hours
- Earnings analysis: daily at 5 PM ET

Usage:
    from bot.learning.crawler import KnowledgeCrawler
    crawler = KnowledgeCrawler()
    crawler.start()  # Runs in background thread
"""

import re
import json
import time
import logging
import hashlib
import threading
import schedule
from datetime import datetime, timedelta
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from bot.db.database import get_connection
from bot.config.settings import CONFIG
from bot.learning.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────
_CRAWLER_CFG = CONFIG.get("knowledge_crawler", {})
_YOUTUBE_INTERVAL_HOURS = _CRAWLER_CFG.get("youtube_interval_hours", 6)
_NEWS_INTERVAL_MINUTES = _CRAWLER_CFG.get("news_interval_minutes", 30)
_REDDIT_INTERVAL_HOURS = _CRAWLER_CFG.get("reddit_interval_hours", 2)
_MAX_ARTICLES_PER_RUN = _CRAWLER_CFG.get("max_articles_per_run", 20)
_MAX_VIDEOS_PER_CHANNEL = _CRAWLER_CFG.get("max_videos_per_channel", 5)
_REQUEST_TIMEOUT = _CRAWLER_CFG.get("request_timeout", 15)
_RATE_LIMIT_SECONDS = _CRAWLER_CFG.get("rate_limit_seconds", 2)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ─── YouTube Channels to Monitor ─────────────────────────────
# Top trading educators — the bot watches these for new content
DEFAULT_YOUTUBE_CHANNELS = _CRAWLER_CFG.get("youtube_channels", [
    # Day Trading
    {"name": "Warrior Trading (Ross Cameron)", "channel_id": "UCMf51MPlHkCbmOkhMOJqfjA", "topics": ["day_trading", "momentum"]},
    {"name": "The Trading Channel", "channel_id": "UCnqZ2hx377rMiFDFfOb9kCg", "topics": ["day_trading", "price_action"]},
    {"name": "Humbled Trader", "channel_id": "UCcIvNGMBSQWMnM3PmjCFJAA", "topics": ["day_trading", "small_caps"]},
    {"name": "Rayner Teo", "channel_id": "UCiTZFRkjTwX7JWLVpEJ8b1g", "topics": ["price_action", "swing_trading"]},

    # Swing Trading & Technical Analysis
    {"name": "Trading with Raghee", "channel_id": "UCBKqSa5B2cvv8gZ9lflVQnA", "topics": ["swing_trading", "indicators"]},
    {"name": "SMB Capital", "channel_id": "UCMtIYCQM_YGRsIJHfaRk8UA", "topics": ["prop_trading", "day_trading"]},
    {"name": "ChartGuys", "channel_id": "UC6CNHnGfcGkwTq72RKqwodA", "topics": ["technical_analysis", "charts"]},

    # Options Trading
    {"name": "InTheMoney (Adam)", "channel_id": "UCfMiRVQJuTj3NpZZP1tKUjg", "topics": ["options", "strategies"]},
    {"name": "Option Alpha", "channel_id": "UCxs9jUKIRMWr9gN9bAMQNYg", "topics": ["options", "premium_selling"]},
    {"name": "projectfinance", "channel_id": "UCKNFJiHJRR_s3dwrjIQHdaw", "topics": ["options", "greeks"]},
    {"name": "Sky View Trading", "channel_id": "UCEbzTO8pPfvuO-Qv-y4b2Gw", "topics": ["options", "spreads"]},
    {"name": "TastyLive", "channel_id": "UCMIzlBRnHljGOZeL3B0v4gA", "topics": ["options", "research"]},

    # Market Analysis & Education
    {"name": "Traders4ACause", "channel_id": "UCnMcjMZteu53KGlwdZBP4RQ", "topics": ["market_analysis", "psychology"]},
    {"name": "ZipTrader", "channel_id": "UCWi4rDVaHC2P09BJG3x7r_Q", "topics": ["market_analysis", "momentum"]},
    {"name": "Stock Moe", "channel_id": "UCvqvCtiZvGGwziRR3grFAMw", "topics": ["growth_investing", "analysis"]},

    # Technical Indicator Deep Dives
    {"name": "TradingLab", "channel_id": "UCIqCXbKyW-03F5GnEGauv6A", "topics": ["indicators", "backtesting"]},
    {"name": "The Moving Average", "channel_id": "UC8cS2h3RKDiy1mPBKfS3JXQ", "topics": ["indicators", "strategies"]},
])

# ─── News Sources (RSS + Direct) ─────────────────────────────
DEFAULT_NEWS_SOURCES = _CRAWLER_CFG.get("news_sources", [
    # Financial News RSS Feeds
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "type": "rss"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news.rss", "type": "rss"},
    {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories/", "type": "rss"},
    {"name": "Seeking Alpha", "url": "https://seekingalpha.com/market_currents.xml", "type": "rss"},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "type": "rss"},

    # Trading Education Sites
    {"name": "Investopedia", "url": "https://www.investopedia.com/terms/", "type": "education"},
    {"name": "BabyPips", "url": "https://www.babypips.com/learn", "type": "education"},
    {"name": "TradingView Ideas", "url": "https://www.tradingview.com/ideas/", "type": "ideas"},
])

# ─── Reddit Subreddits ───────────────────────────────────────
DEFAULT_SUBREDDITS = _CRAWLER_CFG.get("subreddits", [
    {"name": "r/options", "subreddit": "options", "min_score": 50, "topics": ["options"]},
    {"name": "r/daytrading", "subreddit": "daytrading", "min_score": 30, "topics": ["day_trading"]},
    {"name": "r/stocks", "subreddit": "stocks", "min_score": 100, "topics": ["stocks", "analysis"]},
    {"name": "r/swingtrading", "subreddit": "swingtrading", "min_score": 20, "topics": ["swing_trading"]},
    {"name": "r/RealDayTrading", "subreddit": "RealDayTrading", "min_score": 30, "topics": ["day_trading", "education"]},
    {"name": "r/thetagang", "subreddit": "thetagang", "min_score": 30, "topics": ["options", "theta"]},
])


def init_crawler_tables():
    """Create tables for tracking crawled content."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crawler_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            content_id TEXT NOT NULL UNIQUE,
            title TEXT DEFAULT '',
            url TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            rules_extracted INTEGER DEFAULT 0,
            crawled_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crawler_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL,
            topics TEXT DEFAULT '[]',
            last_checked TEXT DEFAULT '',
            videos_processed INTEGER DEFAULT 0,
            rules_extracted INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT 1,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crawler_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            youtube_videos INTEGER DEFAULT 0,
            articles INTEGER DEFAULT 0,
            reddit_posts INTEGER DEFAULT 0,
            total_rules INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_ch_content_id ON crawler_history(content_id);
        CREATE INDEX IF NOT EXISTS idx_ch_source_type ON crawler_history(source_type);
        CREATE INDEX IF NOT EXISTS idx_cc_channel_id ON crawler_channels(channel_id);
    """)
    conn.close()


class KnowledgeCrawler:
    """24/7 autonomous knowledge ingestion system."""

    def __init__(self):
        init_crawler_tables()
        self.kb = KnowledgeBase()
        self.running = False
        self._thread = None
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._today_stats = {"youtube": 0, "articles": 0, "reddit": 0, "rules": 0, "errors": 0}

        # Initialize channel tracking
        self._init_channels()

    def _init_channels(self):
        """Ensure all configured channels are in the database."""
        conn = get_connection()
        for ch in DEFAULT_YOUTUBE_CHANNELS:
            existing = conn.execute(
                "SELECT id FROM crawler_channels WHERE channel_id = ?",
                (ch["channel_id"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO crawler_channels (channel_id, channel_name, topics, added_at) "
                    "VALUES (?, ?, ?, ?)",
                    (ch["channel_id"], ch["name"], json.dumps(ch.get("topics", [])),
                     datetime.now().isoformat())
                )
        conn.commit()
        conn.close()

    # ─── Public API ───────────────────────────────────────────

    def start(self):
        """Start the crawler in a background daemon thread."""
        if self.running:
            logger.info("Crawler already running")
            return

        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="KnowledgeCrawler")
        self._thread.start()
        logger.info("Knowledge Crawler started — learning 24/7")
        print("Knowledge Crawler started — continuously learning from YouTube, news, and Reddit")

    def stop(self):
        """Stop the crawler."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Knowledge Crawler stopped")

    def crawl_now(self):
        """Run all crawlers once immediately (for manual trigger)."""
        print("Running full knowledge crawl...")
        self._crawl_youtube()
        self._crawl_news()
        self._crawl_reddit()
        self._save_daily_stats()
        summary = self.get_stats()
        print(f"Crawl complete: {summary['today']['youtube']} videos, "
              f"{summary['today']['articles']} articles, "
              f"{summary['today']['reddit']} reddit posts, "
              f"{summary['today']['rules']} rules extracted")
        return summary

    def add_youtube_channel(self, channel_url: str, name: str = "", topics: list = None):
        """Add a new YouTube channel to monitor."""
        # Extract channel ID from URL
        channel_id = self._extract_channel_id(channel_url)
        if not channel_id:
            return {"status": "error", "message": "Could not extract channel ID from URL"}

        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM crawler_channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()

        if existing:
            conn.close()
            return {"status": "exists", "message": f"Channel already being monitored"}

        conn.execute(
            "INSERT INTO crawler_channels (channel_id, channel_name, topics, added_at) "
            "VALUES (?, ?, ?, ?)",
            (channel_id, name or channel_url, json.dumps(topics or []),
             datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        logger.info("Added YouTube channel: %s (%s)", name or channel_url, channel_id)
        return {"status": "success", "channel_id": channel_id, "name": name}

    def get_monitored_channels(self) -> list:
        """Get all monitored YouTube channels."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM crawler_channels ORDER BY videos_processed DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_crawl_history(self, source_type: str = None, limit: int = 50) -> list:
        """Get recent crawl history."""
        conn = get_connection()
        if source_type:
            rows = conn.execute(
                "SELECT * FROM crawler_history WHERE source_type = ? "
                "ORDER BY crawled_at DESC LIMIT ?",
                (source_type, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM crawler_history ORDER BY crawled_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get crawler statistics."""
        conn = get_connection()
        total_crawled = conn.execute("SELECT COUNT(*) as cnt FROM crawler_history").fetchone()["cnt"]
        by_source = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM crawler_history GROUP BY source_type"
        ).fetchall()
        total_rules = conn.execute(
            "SELECT SUM(rules_extracted) as total FROM crawler_history"
        ).fetchone()["total"] or 0
        channels = conn.execute("SELECT COUNT(*) as cnt FROM crawler_channels").fetchone()["cnt"]
        recent_stats = conn.execute(
            "SELECT * FROM crawler_stats ORDER BY date DESC LIMIT 7"
        ).fetchall()
        conn.close()

        return {
            "total_crawled": total_crawled,
            "by_source": {r["source_type"]: r["cnt"] for r in by_source},
            "total_rules_extracted": total_rules,
            "channels_monitored": channels,
            "today": dict(self._today_stats),
            "last_7_days": [dict(r) for r in recent_stats],
        }

    # ─── Main Loop ────────────────────────────────────────────

    def _run_loop(self):
        """Main crawler loop with scheduling."""
        # Schedule recurring tasks
        schedule.every(_YOUTUBE_INTERVAL_HOURS).hours.do(self._safe_crawl, "youtube")
        schedule.every(_NEWS_INTERVAL_MINUTES).minutes.do(self._safe_crawl, "news")
        schedule.every(_REDDIT_INTERVAL_HOURS).hours.do(self._safe_crawl, "reddit")
        schedule.every().day.at("17:00").do(self._save_daily_stats)

        # Run initial crawl after a short delay
        time.sleep(10)
        self._safe_crawl("youtube")
        self._safe_crawl("news")
        self._safe_crawl("reddit")

        while self.running:
            schedule.run_pending()
            time.sleep(30)

    def _safe_crawl(self, source: str):
        """Wrap crawl in error handler."""
        try:
            if source == "youtube":
                self._crawl_youtube()
            elif source == "news":
                self._crawl_news()
            elif source == "reddit":
                self._crawl_reddit()
        except Exception as e:
            logger.error("Crawler error (%s): %s", source, e, exc_info=True)
            self._today_stats["errors"] += 1

    # ─── YouTube Crawler ──────────────────────────────────────

    def _crawl_youtube(self):
        """Check all monitored channels for new videos and ingest them."""
        logger.info("YouTube crawler: checking channels for new videos...")

        conn = get_connection()
        channels = conn.execute(
            "SELECT * FROM crawler_channels WHERE enabled = 1"
        ).fetchall()
        conn.close()

        for channel in channels:
            try:
                channel_id = channel["channel_id"]
                video_ids = self._get_channel_recent_videos(channel_id)

                for video_id in video_ids[:_MAX_VIDEOS_PER_CHANNEL]:
                    content_id = f"yt_{video_id}"

                    # Skip if already crawled
                    if self._is_already_crawled(content_id):
                        continue

                    url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info("Ingesting YouTube video: %s", url)

                    result = self.kb.ingest_youtube(url)
                    rules = result.get("rules_extracted", 0)

                    self._record_crawl(
                        source_type="youtube",
                        source_name=channel["channel_name"],
                        content_id=content_id,
                        title=result.get("title", ""),
                        url=url,
                        status=result.get("status", "error"),
                        rules_extracted=rules,
                    )

                    # Update channel stats
                    conn = get_connection()
                    conn.execute(
                        "UPDATE crawler_channels SET videos_processed = videos_processed + 1, "
                        "rules_extracted = rules_extracted + ?, last_checked = ? "
                        "WHERE channel_id = ?",
                        (rules, datetime.now().isoformat(), channel_id)
                    )
                    conn.commit()
                    conn.close()

                    self._today_stats["youtube"] += 1
                    self._today_stats["rules"] += rules
                    time.sleep(_RATE_LIMIT_SECONDS)

            except Exception as e:
                logger.error("YouTube channel %s error: %s", channel["channel_name"], e)
                self._today_stats["errors"] += 1

    def _get_channel_recent_videos(self, channel_id: str) -> list:
        """Get recent video IDs from a YouTube channel via RSS feed."""
        # YouTube provides RSS feeds for channels
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            resp = self._session.get(feed_url, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            entries = soup.find_all("entry")
            video_ids = []

            for entry in entries[:_MAX_VIDEOS_PER_CHANNEL]:
                video_id_tag = entry.find("yt:videoid")
                if video_id_tag:
                    video_ids.append(video_id_tag.text)
                else:
                    # Fallback: extract from link
                    link = entry.find("link")
                    if link and link.get("href"):
                        match = re.search(r'v=([a-zA-Z0-9_-]{11})', link["href"])
                        if match:
                            video_ids.append(match.group(1))

            return video_ids

        except Exception as e:
            logger.debug("Channel RSS fetch failed for %s: %s", channel_id, e)
            return []

    # ─── News Article Crawler ─────────────────────────────────

    def _crawl_news(self):
        """Fetch and ingest trading-related news articles."""
        logger.info("News crawler: fetching articles...")
        articles_ingested = 0

        for source in DEFAULT_NEWS_SOURCES:
            if articles_ingested >= _MAX_ARTICLES_PER_RUN:
                break

            try:
                if source["type"] == "rss":
                    articles = self._fetch_rss_articles(source["url"], source["name"])
                else:
                    continue  # Skip non-RSS for now

                for article in articles:
                    if articles_ingested >= _MAX_ARTICLES_PER_RUN:
                        break

                    content_id = self._content_hash(article["url"])
                    if self._is_already_crawled(content_id):
                        continue

                    # Fetch full article text
                    full_text = self._fetch_article_text(article["url"])
                    if not full_text or len(full_text) < 100:
                        continue

                    # Ingest into knowledge base
                    result = self.kb.ingest_text(
                        title=article["title"],
                        content=full_text,
                        source_type="news_article",
                        source_url=article["url"],
                        confidence=0.6,
                    )

                    rules = result.get("rules_extracted", 0)
                    self._record_crawl(
                        source_type="news",
                        source_name=source["name"],
                        content_id=content_id,
                        title=article["title"],
                        url=article["url"],
                        status=result.get("status", "error"),
                        rules_extracted=rules,
                    )

                    articles_ingested += 1
                    self._today_stats["articles"] += 1
                    self._today_stats["rules"] += rules
                    time.sleep(_RATE_LIMIT_SECONDS)

            except Exception as e:
                logger.error("News source %s error: %s", source["name"], e)
                self._today_stats["errors"] += 1

    def _fetch_rss_articles(self, feed_url: str, source_name: str) -> list:
        """Parse an RSS feed and return article entries."""
        try:
            resp = self._session.get(feed_url, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = []

            # Try RSS 2.0 format
            items = soup.find_all("item")
            if not items:
                # Try Atom format
                items = soup.find_all("entry")

            for item in items[:_MAX_ARTICLES_PER_RUN]:
                title_tag = item.find("title")
                link_tag = item.find("link")

                title = title_tag.text.strip() if title_tag else ""
                if link_tag:
                    link = link_tag.get("href") or link_tag.text.strip()
                else:
                    link = ""

                # Only keep articles related to trading/markets
                if title and link and self._is_trading_relevant(title):
                    articles.append({
                        "title": title,
                        "url": link,
                        "source": source_name,
                    })

            return articles

        except Exception as e:
            logger.debug("RSS fetch failed for %s: %s", feed_url, e)
            return []

    def _fetch_article_text(self, url: str) -> str:
        """Fetch and extract main text content from an article URL."""
        try:
            resp = self._session.get(url, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return ""

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove scripts, styles, nav, footer
            for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Try common article body selectors
            article = (
                soup.find("article") or
                soup.find("div", class_=re.compile(r"article|content|post|story|body", re.I)) or
                soup.find("main")
            )

            if article:
                text = article.get_text(separator=" ", strip=True)
            else:
                # Fallback: get all paragraph text
                paragraphs = soup.find_all("p")
                text = " ".join(p.get_text(strip=True) for p in paragraphs)

            # Clean up
            text = re.sub(r'\s+', ' ', text).strip()

            # Limit to reasonable size
            return text[:15000]

        except Exception as e:
            logger.debug("Article fetch failed for %s: %s", url, e)
            return ""

    # ─── Reddit Crawler ───────────────────────────────────────

    def _crawl_reddit(self):
        """Fetch top posts from trading subreddits."""
        logger.info("Reddit crawler: checking subreddits...")

        for sub_info in DEFAULT_SUBREDDITS:
            try:
                posts = self._fetch_reddit_posts(
                    sub_info["subreddit"],
                    min_score=sub_info.get("min_score", 30),
                )

                for post in posts:
                    content_id = f"reddit_{post['id']}"
                    if self._is_already_crawled(content_id):
                        continue

                    # Combine title and body
                    full_text = f"{post['title']}\n\n{post['body']}"
                    if len(full_text) < 100:
                        continue

                    result = self.kb.ingest_text(
                        title=f"[r/{sub_info['subreddit']}] {post['title'][:100]}",
                        content=full_text,
                        source_type="reddit",
                        source_url=post["url"],
                        confidence=0.4,  # Lower confidence for Reddit
                    )

                    rules = result.get("rules_extracted", 0)
                    self._record_crawl(
                        source_type="reddit",
                        source_name=f"r/{sub_info['subreddit']}",
                        content_id=content_id,
                        title=post["title"][:200],
                        url=post["url"],
                        status=result.get("status", "error"),
                        rules_extracted=rules,
                    )

                    self._today_stats["reddit"] += 1
                    self._today_stats["rules"] += rules
                    time.sleep(_RATE_LIMIT_SECONDS)

            except Exception as e:
                logger.error("Reddit r/%s error: %s", sub_info["subreddit"], e)
                self._today_stats["errors"] += 1

    def _fetch_reddit_posts(self, subreddit: str, min_score: int = 30) -> list:
        """Fetch top posts from a subreddit using Reddit's JSON API."""
        posts = []
        # Reddit provides JSON without auth for public subreddits
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"

        try:
            resp = self._session.get(url, timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return []

            data = resp.json()
            children = data.get("data", {}).get("children", [])

            for child in children:
                post = child.get("data", {})
                score = post.get("score", 0)

                if score < min_score:
                    continue

                # Skip link-only posts with no body
                body = post.get("selftext", "")
                title = post.get("title", "")

                if not self._is_trading_relevant(f"{title} {body[:200]}"):
                    continue

                posts.append({
                    "id": post.get("id", ""),
                    "title": title,
                    "body": body[:10000],
                    "score": score,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                })

            return posts

        except Exception as e:
            logger.debug("Reddit fetch failed for r/%s: %s", subreddit, e)
            return []

    # ─── Helpers ──────────────────────────────────────────────

    def _is_trading_relevant(self, text: str) -> bool:
        """Check if text is relevant to trading/investing."""
        lower = text.lower()
        trading_terms = [
            "stock", "trade", "trading", "market", "option", "call", "put",
            "bullish", "bearish", "earnings", "dividend", "etf", "index",
            "portfolio", "invest", "rally", "sell-off", "correction",
            "breakout", "resistance", "support", "chart", "technical",
            "fundamental", "indicator", "rsi", "macd", "moving average",
            "swing", "day trade", "momentum", "volatility", "premium",
            "spread", "strike", "expiration", "hedge", "position",
            "profit", "loss", "risk", "reward", "entry", "exit",
            "fed", "inflation", "interest rate", "gdp", "jobs",
            "s&p", "nasdaq", "dow", "russell", "vix",
            "squeeze", "gap", "volume", "candle", "pattern",
        ]
        matches = sum(1 for term in trading_terms if term in lower)
        return matches >= 2  # At least 2 trading terms = relevant

    def _is_already_crawled(self, content_id: str) -> bool:
        """Check if content has already been crawled."""
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM crawler_history WHERE content_id = ?",
            (content_id,)
        ).fetchone()
        conn.close()
        return existing is not None

    def _record_crawl(self, source_type, source_name, content_id, title, url,
                      status, rules_extracted):
        """Record a crawl in the history table."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO crawler_history "
                "(source_type, source_name, content_id, title, url, status, "
                "rules_extracted, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source_type, source_name, content_id, title, url, status,
                 rules_extracted, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Record crawl failed: %s", e)

    def _save_daily_stats(self):
        """Save today's crawl stats to the database."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            conn = get_connection()

            existing = conn.execute(
                "SELECT id FROM crawler_stats WHERE date = ?", (today,)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE crawler_stats SET youtube_videos = ?, articles = ?, "
                    "reddit_posts = ?, total_rules = ?, errors = ? WHERE date = ?",
                    (self._today_stats["youtube"], self._today_stats["articles"],
                     self._today_stats["reddit"], self._today_stats["rules"],
                     self._today_stats["errors"], today)
                )
            else:
                conn.execute(
                    "INSERT INTO crawler_stats (date, youtube_videos, articles, "
                    "reddit_posts, total_rules, errors) VALUES (?, ?, ?, ?, ?, ?)",
                    (today, self._today_stats["youtube"], self._today_stats["articles"],
                     self._today_stats["reddit"], self._today_stats["rules"],
                     self._today_stats["errors"])
                )

            conn.commit()
            conn.close()

            # Reset daily stats
            self._today_stats = {"youtube": 0, "articles": 0, "reddit": 0, "rules": 0, "errors": 0}

        except Exception as e:
            logger.error("Save daily stats failed: %s", e)

    def _content_hash(self, text: str) -> str:
        """Create a short hash for content deduplication."""
        return hashlib.md5(text.encode()).hexdigest()[:16]

    def _extract_channel_id(self, url: str) -> str:
        """Extract YouTube channel ID from various URL formats."""
        # Direct channel ID
        match = re.search(r'channel/([a-zA-Z0-9_-]{24})', url)
        if match:
            return match.group(1)

        # @handle format — need to resolve
        match = re.search(r'@([\w.-]+)', url)
        if match:
            try:
                resp = self._session.get(
                    f"https://www.youtube.com/@{match.group(1)}",
                    timeout=_REQUEST_TIMEOUT
                )
                ch_match = re.search(r'"channelId":"([a-zA-Z0-9_-]{24})"', resp.text)
                if ch_match:
                    return ch_match.group(1)
            except Exception:
                pass

        # If it looks like a raw channel ID
        if re.match(r'^UC[a-zA-Z0-9_-]{22}$', url):
            return url

        return ""
