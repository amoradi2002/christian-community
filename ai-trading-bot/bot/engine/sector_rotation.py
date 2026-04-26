"""
Sector Rotation Tracker

Money moves between sectors cyclically. Trading with the hot sector = swimming downstream.
Check which sectors are outperforming SPY and focus scanning there.

Sector ETFs:
  XLK (Tech), XLF (Financials), XLE (Energy), XLV (Healthcare),
  XLY (Consumer Disc), XLP (Consumer Staples), XLU (Utilities),
  XLB (Materials), XLRE (Real Estate), XLI (Industrials)
"""

from dataclasses import dataclass, field
from datetime import datetime


SECTOR_ETFS = {
    "XLK": {"name": "Technology", "hot_when": "Risk-on, low rates, growth environment"},
    "XLF": {"name": "Financials", "hot_when": "Rising interest rates, strong economy"},
    "XLE": {"name": "Energy", "hot_when": "Oil rising, inflation, geopolitical tension"},
    "XLV": {"name": "Healthcare", "hot_when": "Defensive, uncertain markets"},
    "XLY": {"name": "Consumer Discretionary", "hot_when": "Strong consumer spending, low unemployment"},
    "XLP": {"name": "Consumer Staples", "hot_when": "Defensive, recession fears"},
    "XLU": {"name": "Utilities", "hot_when": "Defensive, rate cuts expected"},
    "XLB": {"name": "Materials", "hot_when": "Inflation rising, commodities up"},
    "XLRE": {"name": "Real Estate", "hot_when": "Rate cuts expected, growth"},
    "XLI": {"name": "Industrials", "hot_when": "Infrastructure spending, economic expansion"},
}

DEFENSIVE_SECTORS = {"XLU", "XLV", "XLP"}
GROWTH_SECTORS = {"XLK", "XLY", "XLF"}


@dataclass
class SectorPerformance:
    symbol: str
    name: str
    change_pct: float = 0.0
    relative_to_spy: float = 0.0  # Outperformance vs SPY
    volume_ratio: float = 0.0
    trend: str = ""  # "leading", "lagging", "neutral"


@dataclass
class SectorRotationReport:
    timestamp: str = ""
    spy_change_pct: float = 0.0
    sectors: list = field(default_factory=list)
    top_sectors: list = field(default_factory=list)  # Top 3 by relative performance
    bottom_sectors: list = field(default_factory=list)  # Bottom 3
    market_regime: str = ""  # "risk-on", "risk-off", "mixed"
    recommendation: str = ""

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "spy_change_pct": self.spy_change_pct,
            "sectors": [{"symbol": s.symbol, "name": s.name, "change_pct": s.change_pct,
                         "relative_to_spy": s.relative_to_spy, "trend": s.trend}
                        for s in self.sectors],
            "top_sectors": [s.symbol for s in self.top_sectors],
            "bottom_sectors": [s.symbol for s in self.bottom_sectors],
            "market_regime": self.market_regime,
            "recommendation": self.recommendation,
        }


def analyze_sector_rotation(sector_data: dict[str, dict]) -> SectorRotationReport:
    """
    Analyze sector rotation from price data.

    Args:
        sector_data: Dict of {symbol: {"change_pct": float, "volume_ratio": float}}
                     Must include "SPY" key.

    Returns:
        SectorRotationReport with analysis and recommendations.
    """
    report = SectorRotationReport(timestamp=datetime.now().isoformat())

    spy_data = sector_data.get("SPY", {})
    report.spy_change_pct = spy_data.get("change_pct", 0.0)

    performances = []
    for etf, info in SECTOR_ETFS.items():
        data = sector_data.get(etf, {})
        change = data.get("change_pct", 0.0)
        relative = change - report.spy_change_pct

        trend = "neutral"
        if relative > 1.0:
            trend = "leading"
        elif relative < -1.0:
            trend = "lagging"

        perf = SectorPerformance(
            symbol=etf,
            name=info["name"],
            change_pct=round(change, 2),
            relative_to_spy=round(relative, 2),
            volume_ratio=data.get("volume_ratio", 0.0),
            trend=trend,
        )
        performances.append(perf)

    # Sort by relative performance
    performances.sort(key=lambda p: p.relative_to_spy, reverse=True)
    report.sectors = performances
    report.top_sectors = performances[:3]
    report.bottom_sectors = performances[-3:]

    # Determine market regime
    top_symbols = {s.symbol for s in report.top_sectors}
    defensive_leading = len(top_symbols & DEFENSIVE_SECTORS)
    growth_leading = len(top_symbols & GROWTH_SECTORS)

    if defensive_leading >= 2:
        report.market_regime = "risk-off"
        report.recommendation = (
            "Defensive sectors leading — risk appetite is dropping. "
            "Reduce position size and be more selective on longs. "
            "Consider short setups in lagging growth sectors."
        )
    elif growth_leading >= 2:
        report.market_regime = "risk-on"
        report.recommendation = (
            "Growth sectors leading — risk-on environment. "
            "Focus swing trade scanning in top sectors. "
            f"Best opportunities in: {', '.join(s.symbol for s in report.top_sectors)}"
        )
    else:
        report.market_regime = "mixed"
        report.recommendation = (
            "Mixed sector rotation — no clear theme. "
            "Be selective. Focus on individual stock setups with strong catalysts."
        )

    return report


def get_sector_for_stock(symbol: str) -> str:
    """Get the sector ETF for a given stock. Returns empty string if unknown."""
    # Common stock -> sector mappings
    STOCK_SECTORS = {
        "AAPL": "XLK", "MSFT": "XLK", "GOOGL": "XLK", "GOOG": "XLK",
        "META": "XLK", "NVDA": "XLK", "AMD": "XLK", "INTC": "XLK",
        "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "NKE": "XLY",
        "JPM": "XLF", "BAC": "XLF", "GS": "XLF", "MS": "XLF",
        "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
        "JNJ": "XLV", "UNH": "XLV", "PFE": "XLV", "ABBV": "XLV",
        "PG": "XLP", "KO": "XLP", "PEP": "XLP", "WMT": "XLP",
        "NEE": "XLU", "DUK": "XLU", "SO": "XLU",
        "CAT": "XLI", "BA": "XLI", "GE": "XLI", "UNP": "XLI",
    }
    return STOCK_SECTORS.get(symbol.upper(), "")


def check_sector_alignment(symbol: str, action: str, sector_data: dict) -> dict:
    """
    Check if a trade setup aligns with sector rotation.
    Returns alignment info.
    """
    sector_etf = get_sector_for_stock(symbol)
    if not sector_etf or sector_etf not in sector_data:
        return {"aligned": None, "sector": "", "message": "Sector unknown"}

    report = analyze_sector_rotation(sector_data)
    sector_perf = next((s for s in report.sectors if s.symbol == sector_etf), None)

    if not sector_perf:
        return {"aligned": None, "sector": sector_etf, "message": "No data"}

    is_long = action.upper() == "BUY"

    if is_long and sector_perf.trend == "leading":
        return {
            "aligned": True,
            "sector": sector_etf,
            "sector_name": sector_perf.name,
            "message": f"Tailwind: {sector_perf.name} ({sector_etf}) is leading ({sector_perf.relative_to_spy:+.1f}% vs SPY)",
        }
    elif is_long and sector_perf.trend == "lagging":
        return {
            "aligned": False,
            "sector": sector_etf,
            "sector_name": sector_perf.name,
            "message": f"Headwind: {sector_perf.name} ({sector_etf}) is lagging ({sector_perf.relative_to_spy:+.1f}% vs SPY)",
        }
    else:
        return {
            "aligned": None,
            "sector": sector_etf,
            "sector_name": sector_perf.name,
            "message": f"{sector_perf.name} ({sector_etf}) is neutral ({sector_perf.relative_to_spy:+.1f}% vs SPY)",
        }
