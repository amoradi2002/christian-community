"""
YouTube Strategy Learner

Extracts trading strategies from YouTube video transcripts.
Parses mentions of indicators, price levels, and trading rules,
then converts them into structured mentorship strategies.

Usage:
    from bot.learning.youtube import process_video
    strategies = process_video("https://youtube.com/watch?v=...")
"""

import re
import json
from datetime import datetime
from bot.db.database import get_connection

# Try transcript API first, fall back to yt-dlp
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_TRANSCRIPT_API = True
except ImportError:
    HAS_TRANSCRIPT_API = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def get_video_info(url: str) -> dict:
    """Get video title and channel using yt-dlp."""
    if not HAS_YTDLP:
        return {"title": "Unknown", "channel": "Unknown"}

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "channel": info.get("channel", info.get("uploader", "Unknown")),
            }
    except Exception:
        return {"title": "Unknown", "channel": "Unknown"}


def get_transcript(video_id: str) -> str:
    """Get video transcript/captions."""
    if HAS_TRANSCRIPT_API:
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(entry["text"] for entry in transcript_list)
        except Exception:
            pass

    # Fallback: try yt-dlp subtitles
    if HAS_YTDLP:
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en"],
                "subtitlesformat": "json3",
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
                subs = info.get("subtitles", {}) or info.get("automatic_captions", {})
                if "en" in subs:
                    # Return subtitle text
                    return str(subs["en"])
        except Exception:
            pass

    return ""


# --- Strategy Extraction Engine ---

# Indicators the parser looks for in transcripts
INDICATOR_PATTERNS = {
    "rsi": {
        "patterns": [
            r'rsi\s*(?:is\s*)?(?:at\s*|below\s*|above\s*|under\s*|over\s*)?(\d+)',
            r'relative\s+strength\s+(?:index\s+)?(?:is\s*)?(?:at\s*|below\s*|above\s*)?(\d+)',
            r'rsi\s*(?:of\s*)?(\d+)',
        ],
        "indicator": "rsi_14",
    },
    "macd": {
        "patterns": [
            r'macd\s+cross(?:es|ing|ed)?\s+(above|below|over|under)',
            r'macd\s+(?:is\s+)?(?:going\s+)?(bullish|bearish)',
            r'macd\s+histogram\s+(?:is\s+)?(positive|negative)',
        ],
        "indicator": "macd_histogram",
    },
    "moving_average": {
        "patterns": [
            r'(\d+)\s*(?:day|period|d)?\s*(?:moving\s+average|ma|sma|ema)',
            r'(?:moving\s+average|ma|sma|ema)\s*(?:of\s*)?(\d+)',
            r'price\s+(?:above|below|crosses?)\s+(?:the\s+)?(\d+)\s*(?:day|d|period)?\s*(?:ma|sma|ema|moving)',
        ],
        "indicator": "sma_20",
    },
    "bollinger": {
        "patterns": [
            r'bollinger\s+band',
            r'bb\s+(?:squeeze|breakout|upper|lower)',
            r'price\s+(?:hits?|touches?|breaks?)\s+(?:the\s+)?(?:upper|lower)\s+(?:bollinger|band|bb)',
        ],
        "indicator": "bb_upper",
    },
    "support_resistance": {
        "patterns": [
            r'support\s+(?:at|level|around)\s+\$?(\d+(?:\.\d+)?)',
            r'resistance\s+(?:at|level|around)\s+\$?(\d+(?:\.\d+)?)',
        ],
        "indicator": "close",
    },
    "volume": {
        "patterns": [
            r'(?:high|heavy|big|increasing|spike\s+in)\s+volume',
            r'volume\s+(?:is\s+)?(?:above|higher|increasing)',
        ],
        "indicator": "volume",
    },
}

# Action keywords
BUY_KEYWORDS = [
    r'\bbuy\b', r'\blong\b', r'\bbullish\b', r'\bentry\b', r'\baccumulate\b',
    r'\bgo\s+long\b', r'\bcall\b', r'\bupside\b', r'\bbounce\b',
    r'\boversold\b', r'\bdip\s+buy\b', r'\bbottom\b',
]

SELL_KEYWORDS = [
    r'\bsell\b', r'\bshort\b', r'\bbearish\b', r'\bexit\b',
    r'\bgo\s+short\b', r'\bput\b', r'\bdownside\b',
    r'\boverbought\b', r'\btop\b', r'\bbreak\s*down\b',
]


def extract_strategies_from_transcript(transcript: str, video_title: str = "") -> list[dict]:
    """Parse a transcript and extract trading strategies."""
    if not transcript:
        return []

    text = transcript.lower()
    sentences = re.split(r'[.!?]+', text)
    strategies = []
    found_conditions = []

    # Scan for indicator mentions with values
    for sent in sentences:
        conditions = []

        # RSI conditions
        for pattern in INDICATOR_PATTERNS["rsi"]["patterns"]:
            match = re.search(pattern, sent)
            if match:
                value = int(match.group(1))
                if "below" in sent or "under" in sent or "oversold" in sent:
                    conditions.append({"indicator": "rsi_14", "operator": "<=", "value": value})
                elif "above" in sent or "over" in sent or "overbought" in sent:
                    conditions.append({"indicator": "rsi_14", "operator": ">=", "value": value})
                else:
                    # Default: if value < 50, treat as oversold buy; > 50, overbought sell
                    if value <= 40:
                        conditions.append({"indicator": "rsi_14", "operator": "<=", "value": value})
                    elif value >= 60:
                        conditions.append({"indicator": "rsi_14", "operator": ">=", "value": value})

        # MACD conditions
        for pattern in INDICATOR_PATTERNS["macd"]["patterns"]:
            match = re.search(pattern, sent)
            if match:
                val = match.group(1)
                if val in ("above", "over", "bullish", "positive"):
                    conditions.append({"indicator": "macd_histogram", "operator": ">", "value": 0})
                elif val in ("below", "under", "bearish", "negative"):
                    conditions.append({"indicator": "macd_histogram", "operator": "<", "value": 0})

        # Moving average conditions
        for pattern in INDICATOR_PATTERNS["moving_average"]["patterns"]:
            match = re.search(pattern, sent)
            if match:
                period = int(match.group(1))
                ma_name = f"sma_{period}" if period in (20, 50, 200) else "sma_20"
                if "above" in sent or "over" in sent or "crosses" in sent:
                    conditions.append({"indicator": "close", "operator": ">", "ref": ma_name})
                elif "below" in sent or "under" in sent:
                    conditions.append({"indicator": "close", "operator": "<", "ref": ma_name})

        # Bollinger conditions
        for pattern in INDICATOR_PATTERNS["bollinger"]["patterns"]:
            if re.search(pattern, sent):
                if "upper" in sent or "overbought" in sent:
                    conditions.append({"indicator": "close", "operator": ">=", "ref": "bb_upper"})
                elif "lower" in sent or "oversold" in sent or "squeeze" in sent:
                    conditions.append({"indicator": "close", "operator": "<=", "ref": "bb_lower"})

        if conditions:
            found_conditions.extend(conditions)

    # Determine signal direction from overall transcript
    buy_score = sum(1 for kw in BUY_KEYWORDS if re.search(kw, text))
    sell_score = sum(1 for kw in SELL_KEYWORDS if re.search(kw, text))

    if not found_conditions:
        return []

    # Deduplicate conditions
    seen = set()
    unique_conditions = []
    for c in found_conditions:
        key = (c["indicator"], c["operator"], c.get("value", c.get("ref", "")))
        if key not in seen:
            seen.add(key)
            unique_conditions.append(c)

    # Group conditions into coherent strategies
    # If we have both buy and sell indicators, create separate strategies
    if buy_score > 0 and unique_conditions:
        buy_conditions = [c for c in unique_conditions
                         if not (c["indicator"] == "rsi_14" and c["operator"] == ">=" and c.get("value", 0) >= 60)]
        if buy_conditions:
            strategies.append({
                "name": _make_strategy_name(video_title, "Buy"),
                "description": f"Extracted from: {video_title}",
                "conditions": buy_conditions[:5],  # Max 5 conditions
                "signal": "BUY",
                "symbols": [],
            })

    if sell_score > 0 and unique_conditions:
        sell_conditions = [c for c in unique_conditions
                          if not (c["indicator"] == "rsi_14" and c["operator"] == "<=" and c.get("value", 0) <= 40)]
        if sell_conditions:
            strategies.append({
                "name": _make_strategy_name(video_title, "Sell"),
                "description": f"Extracted from: {video_title}",
                "conditions": sell_conditions[:5],
                "signal": "SELL",
                "symbols": [],
            })

    # If no clear direction but we have conditions, default to BUY
    if not strategies and unique_conditions:
        signal = "BUY" if buy_score >= sell_score else "SELL"
        strategies.append({
            "name": _make_strategy_name(video_title, signal.title()),
            "description": f"Extracted from: {video_title}",
            "conditions": unique_conditions[:5],
            "signal": signal,
            "symbols": [],
        })

    return strategies


def _make_strategy_name(video_title: str, direction: str) -> str:
    """Generate a clean strategy name from video title."""
    # Clean up title
    clean = re.sub(r'[^\w\s]', '', video_title or "YouTube")
    words = clean.split()[:4]
    name = " ".join(words)
    return f"{name} {direction}"


def process_video(url: str) -> dict:
    """
    Full pipeline: URL -> transcript -> strategies -> save to DB.

    Returns dict with status, strategies found, and any errors.
    """
    video_id = extract_video_id(url)
    if not video_id:
        return {"status": "error", "message": "Invalid YouTube URL"}

    conn = get_connection()

    # Check if already processed
    existing = conn.execute(
        "SELECT * FROM youtube_lessons WHERE video_id = ?", (video_id,)
    ).fetchone()
    if existing and existing["status"] == "done":
        conn.close()
        return {
            "status": "already_processed",
            "message": f"Video already processed: {existing['title']}",
            "strategies": json.loads(existing["extracted_strategies"] or "[]"),
        }

    # Get video info
    info = get_video_info(url)
    title = info["title"]
    channel = info["channel"]

    # Get transcript
    transcript = get_transcript(video_id)
    if not transcript:
        conn.execute(
            """INSERT OR REPLACE INTO youtube_lessons
               (video_url, video_id, title, channel_name, status)
               VALUES (?, ?, ?, ?, 'no_transcript')""",
            (url, video_id, title, channel),
        )
        conn.commit()
        conn.close()
        return {
            "status": "no_transcript",
            "message": f"No transcript available for: {title}. Try a video with captions/subtitles.",
        }

    # Extract strategies
    strategies = extract_strategies_from_transcript(transcript, title)

    # Save to database
    conn.execute(
        """INSERT OR REPLACE INTO youtube_lessons
           (video_url, video_id, title, channel_name, transcript, extracted_strategies, status, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, 'done', ?)""",
        (url, video_id, title, channel, transcript[:10000], json.dumps(strategies),
         datetime.now().isoformat()),
    )
    conn.commit()

    # Auto-save extracted strategies as mentorship strategies
    saved_count = 0
    from bot.strategies.store import save_strategy, get_strategy_by_name
    for strat in strategies:
        if not get_strategy_by_name(strat["name"]):
            save_strategy(
                name=strat["name"],
                strategy_type="mentorship",
                description=strat["description"],
                rules=strat,
                is_active=False,  # Disabled by default, user reviews and enables
            )
            saved_count += 1

    conn.close()

    return {
        "status": "success",
        "title": title,
        "channel": channel,
        "strategies_found": len(strategies),
        "strategies_saved": saved_count,
        "strategies": strategies,
        "transcript_length": len(transcript),
    }


def get_lesson_history(limit=50):
    """Get all processed YouTube lessons."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, video_url, video_id, title, channel_name, status, extracted_strategies, created_at "
        "FROM youtube_lessons ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
