"""
Day Trade Scanner — The 5 Pillars

Every day trade candidate must meet ALL 5 before it's worth considering:
1. Already moving — Up at least 10% on the day
2. Relative volume — 5x above 50-day average
3. Catalyst — Breaking news (earnings, FDA, contract, etc.)
4. Price — $2-$20 sweet spot ($5-$10 ideal)
5. Float — Under 10 million shares (lower = better)

Also includes:
- Small cap scan: Market cap < $1B, Gap >= 10%, Price >= $1, Premarket vol >= 20K
- Large cap scan: Market cap > $1B, Gap >= 3%, Price >= $1, Premarket vol >= 50K
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DayTradeCandidate:
    symbol: str
    price: float = 0.0
    day_change_pct: float = 0.0
    relative_volume: float = 0.0
    catalyst: str = ""
    catalyst_tier: str = ""  # S, A, B, C, Skip
    float_shares: float = 0.0  # in millions
    market_cap: float = 0.0  # in millions
    pillars_met: int = 0
    pillar_details: dict = field(default_factory=dict)
    scan_type: str = ""  # "small_cap", "large_cap"
    passed: bool = False

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "price": self.price,
            "day_change_pct": self.day_change_pct,
            "relative_volume": self.relative_volume,
            "catalyst": self.catalyst,
            "catalyst_tier": self.catalyst_tier,
            "float_shares_m": self.float_shares,
            "market_cap_m": self.market_cap,
            "pillars_met": self.pillars_met,
            "pillar_details": self.pillar_details,
            "scan_type": self.scan_type,
            "passed": self.passed,
        }


# Catalyst quality tiers
CATALYST_TIERS = {
    "S": {
        "name": "S-Tier",
        "description": "FDA approval, earnings beat + raised guidance, major acquisition",
        "keywords": ["fda approv", "guidance raise", "raised guidance", "acquisition",
                      "buyout", "merger", "takeover", "breakthrough"],
        "reliability": "Highest — market moves hard and holds",
    },
    "A": {
        "name": "A-Tier",
        "description": "Earnings beat, major contract, partnership with big company",
        "keywords": ["earnings beat", "revenue beat", "contract win", "partnership",
                      "strategic agreement", "awarded contract", "major deal"],
        "reliability": "Strong — good follow-through",
    },
    "B": {
        "name": "B-Tier",
        "description": "Sector news, analyst upgrade, product launch",
        "keywords": ["upgrade", "price target", "product launch", "sector",
                      "initiat", "positive data", "clinical"],
        "reliability": "Moderate — depends on broader market",
    },
    "C": {
        "name": "C-Tier",
        "description": "Press release, vague update, social media buzz",
        "keywords": ["press release", "strategic update", "social media",
                      "trending", "meme", "reddit", "wsb"],
        "reliability": "Weak — often fades quickly",
    },
}


def grade_catalyst(news_text: str) -> str:
    """Grade a catalyst from S to C based on keywords. Returns tier or 'Skip'."""
    if not news_text:
        return "Skip"

    text_lower = news_text.lower()
    for tier in ["S", "A", "B", "C"]:
        for keyword in CATALYST_TIERS[tier]["keywords"]:
            if keyword in text_lower:
                return tier
    return "Skip"


def check_five_pillars(
    symbol: str,
    price: float,
    day_change_pct: float,
    relative_volume: float,
    catalyst: str = "",
    float_shares_m: float = 0.0,
) -> DayTradeCandidate:
    """
    Check a stock against the 5 Pillars of day trade selection.
    Returns a DayTradeCandidate with details on which pillars are met.
    """
    candidate = DayTradeCandidate(
        symbol=symbol,
        price=price,
        day_change_pct=day_change_pct,
        relative_volume=relative_volume,
        catalyst=catalyst,
        float_shares=float_shares_m,
    )

    pillars = {}
    count = 0

    # Pillar 1: Already moving (up 10%+)
    if day_change_pct >= 10:
        pillars["already_moving"] = {"met": True, "value": f"+{day_change_pct:.1f}%"}
        count += 1
    else:
        pillars["already_moving"] = {"met": False, "value": f"+{day_change_pct:.1f}%", "need": "10%+"}

    # Pillar 2: Relative Volume (5x above 50-day average)
    if relative_volume >= 5.0:
        pillars["relative_volume"] = {"met": True, "value": f"{relative_volume:.1f}x"}
        count += 1
    else:
        pillars["relative_volume"] = {"met": False, "value": f"{relative_volume:.1f}x", "need": "5x+"}

    # Pillar 3: Catalyst
    tier = grade_catalyst(catalyst)
    candidate.catalyst_tier = tier
    if tier in ("S", "A"):
        pillars["catalyst"] = {"met": True, "value": f"Tier {tier}: {catalyst[:50]}"}
        count += 1
    elif tier == "B":
        pillars["catalyst"] = {"met": False, "value": f"Tier B (weak): {catalyst[:50]}", "need": "Tier S or A"}
    else:
        pillars["catalyst"] = {"met": False, "value": catalyst[:50] if catalyst else "None found", "need": "Real news catalyst"}

    # Pillar 4: Price $2-$20 (sweet spot $5-$10)
    if 2 <= price <= 20:
        label = "Sweet spot" if 5 <= price <= 10 else "OK"
        pillars["price_range"] = {"met": True, "value": f"${price:.2f} ({label})"}
        count += 1
    else:
        pillars["price_range"] = {"met": False, "value": f"${price:.2f}", "need": "$2-$20"}

    # Pillar 5: Float under 10M shares
    if 0 < float_shares_m < 10:
        pillars["low_float"] = {"met": True, "value": f"{float_shares_m:.1f}M shares"}
        count += 1
    elif float_shares_m == 0:
        pillars["low_float"] = {"met": False, "value": "Unknown", "need": "<10M shares"}
    else:
        pillars["low_float"] = {"met": False, "value": f"{float_shares_m:.1f}M shares", "need": "<10M shares"}

    candidate.pillars_met = count
    candidate.pillar_details = pillars
    candidate.passed = count >= 5

    return candidate


def scan_small_cap(stocks: list[dict]) -> list[DayTradeCandidate]:
    """
    Small cap scan: Market cap < $1B, Gap >= 10%, Price >= $1, Premarket vol >= 20K
    """
    candidates = []
    for stock in stocks:
        mc = stock.get("market_cap", 0)
        gap = stock.get("day_change_pct", 0)
        price = stock.get("price", 0)
        vol = stock.get("premarket_volume", stock.get("volume", 0))

        if mc < 1_000 and gap >= 10 and price >= 1 and vol >= 20_000:
            c = check_five_pillars(
                symbol=stock.get("symbol", ""),
                price=price,
                day_change_pct=gap,
                relative_volume=stock.get("relative_volume", 0),
                catalyst=stock.get("catalyst", ""),
                float_shares_m=stock.get("float_shares_m", 0),
            )
            c.market_cap = mc
            c.scan_type = "small_cap"
            candidates.append(c)

    return sorted(candidates, key=lambda c: c.pillars_met, reverse=True)


def scan_large_cap(stocks: list[dict]) -> list[DayTradeCandidate]:
    """
    Large cap scan: Market cap > $1B, Gap >= 3%, Price >= $1, Premarket vol >= 50K
    """
    candidates = []
    for stock in stocks:
        mc = stock.get("market_cap", 0)
        gap = stock.get("day_change_pct", 0)
        price = stock.get("price", 0)
        vol = stock.get("premarket_volume", stock.get("volume", 0))

        if mc >= 1_000 and gap >= 3 and price >= 1 and vol >= 50_000:
            c = DayTradeCandidate(
                symbol=stock.get("symbol", ""),
                price=price,
                day_change_pct=gap,
                relative_volume=stock.get("relative_volume", 0),
                catalyst=stock.get("catalyst", ""),
                catalyst_tier=grade_catalyst(stock.get("catalyst", "")),
                market_cap=mc,
                scan_type="large_cap",
                passed=True,  # Large caps have different criteria
            )
            candidates.append(c)

    return sorted(candidates, key=lambda c: c.day_change_pct, reverse=True)


def get_no_trade_reasons(indicators: dict) -> list[str]:
    """
    Check no-trade conditions from the skill.
    Returns list of reasons NOT to trade. Empty = OK to trade.
    """
    reasons = []

    # No catalyst
    if not indicators.get("catalyst"):
        reasons.append("No catalyst present")

    # Low volume / choppy
    rvol = indicators.get("relative_volume", 0)
    if 0 < rvol < 1.0:
        reasons.append(f"Low relative volume ({rvol:.1f}x) — choppy price action likely")

    # Setup doesn't meet minimum R:R
    rr = indicators.get("risk_reward", 0)
    if 0 < rr < 2.0:
        reasons.append(f"R:R only {rr:.1f}:1 — minimum 2:1 required")

    return reasons
