"""
Portfolio Correlation Analysis

Calculates pairwise return correlations across held positions to detect
overlapping risk.  Uses yfinance for historical prices and numpy for the
correlation matrix.

Usage:
    from bot.engine.correlation import (
        check_portfolio_correlation,
        get_diversification_score,
        format_correlation_report,
    )

    alerts = check_portfolio_correlation(["AAPL", "MSFT", "XOM", "JPM"])
    report = format_correlation_report(["AAPL", "MSFT", "XOM", "JPM"])
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CorrelationAlert:
    symbol_a: str
    symbol_b: str
    correlation: float
    risk_level: str   # "high" (>0.8), "moderate" (0.6-0.8), "low" (<0.6)
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_returns(symbols: list, period: str = "30d") -> Optional[dict]:
    """Download daily close prices via yfinance and compute daily returns.

    Returns:
        dict mapping symbol -> np.ndarray of daily returns, or None on
        failure.  Only symbols with enough data are included.
    """
    try:
        import yfinance as yf

        # Download all tickers in one call for efficiency
        tickers_str = " ".join(s.upper() for s in symbols)
        data = yf.download(tickers_str, period=period, progress=False, threads=True)

        if data.empty:
            logger.warning("yfinance returned empty data for %s", symbols)
            return None

        # yf.download returns MultiIndex columns when len(symbols) > 1
        close = data.get("Close", data)
        if close is None or close.empty:
            return None

        # Single-ticker download returns a Series or single-column DataFrame
        if len(symbols) == 1:
            sym = symbols[0].upper()
            series = close.squeeze()
            returns = series.pct_change().dropna().values
            if len(returns) < 5:
                return None
            return {sym: returns}

        result = {}
        for sym in symbols:
            sym_upper = sym.upper()
            if sym_upper not in close.columns:
                logger.debug("No price data for %s, skipping", sym_upper)
                continue
            series = close[sym_upper].dropna()
            returns = series.pct_change().dropna().values
            if len(returns) >= 5:
                result[sym_upper] = returns

        return result if result else None

    except Exception as exc:
        logger.error("Failed to fetch returns: %s", exc)
        return None


def _classify_correlation(corr: float) -> str:
    """Return risk level string for a correlation value."""
    abs_corr = abs(corr)
    if abs_corr > 0.8:
        return "high"
    elif abs_corr > 0.6:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_correlation_matrix(symbols: list, period: str = "30d") -> dict:
    """Calculate pairwise correlation matrix for a list of symbols.

    Returns:
        {
            "pairs": [{"symbol_a": str, "symbol_b": str, "correlation": float}, ...],
            "matrix": [[float, ...], ...],
            "symbols": [str, ...],
        }

    If data cannot be retrieved, returns a dict with empty values and an
    "error" key.
    """
    if len(symbols) < 2:
        return {
            "pairs": [],
            "matrix": [[1.0]] if symbols else [],
            "symbols": [s.upper() for s in symbols],
            "error": "Need at least 2 symbols for correlation analysis.",
        }

    returns_data = _fetch_returns(symbols, period)
    if returns_data is None:
        return {
            "pairs": [],
            "matrix": [],
            "symbols": [s.upper() for s in symbols],
            "error": "Could not fetch price data from yfinance.",
        }

    # Align all return series to the same length (shortest)
    ordered_syms = sorted(returns_data.keys())
    min_len = min(len(returns_data[s]) for s in ordered_syms)
    aligned = np.array([returns_data[s][:min_len] for s in ordered_syms])

    # numpy corrcoef returns an NxN matrix
    corr_matrix = np.corrcoef(aligned)
    # Replace any NaN with 0.0
    corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

    # Build pairs list
    pairs = []
    n = len(ordered_syms)
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({
                "symbol_a": ordered_syms[i],
                "symbol_b": ordered_syms[j],
                "correlation": round(float(corr_matrix[i][j]), 4),
            })

    return {
        "pairs": pairs,
        "matrix": [[round(float(corr_matrix[i][j]), 4) for j in range(n)] for i in range(n)],
        "symbols": ordered_syms,
    }


def check_portfolio_correlation(symbols: list, threshold: float = 0.7) -> List[CorrelationAlert]:
    """Check for dangerously correlated positions.

    Returns a list of CorrelationAlert for every pair whose absolute
    correlation exceeds *threshold* (default 0.7).
    """
    result = calculate_correlation_matrix(symbols)
    if result.get("error"):
        logger.warning("Correlation check skipped: %s", result["error"])
        return []

    alerts = []
    for pair in result["pairs"]:
        corr = pair["correlation"]
        if abs(corr) > threshold:
            risk = _classify_correlation(corr)
            direction = "positively" if corr > 0 else "negatively"
            msg = (
                f"{pair['symbol_a']} and {pair['symbol_b']} are highly "
                f"{direction} correlated ({corr:+.2f}). "
            )
            if risk == "high":
                msg += "These positions carry similar risk — consider reducing one."
            else:
                msg += "Monitor for overlapping moves."

            alerts.append(CorrelationAlert(
                symbol_a=pair["symbol_a"],
                symbol_b=pair["symbol_b"],
                correlation=corr,
                risk_level=risk,
                message=msg,
            ))

    # Sort by absolute correlation descending
    alerts.sort(key=lambda a: abs(a.correlation), reverse=True)
    return alerts


def get_diversification_score(symbols: list) -> dict:
    """Score portfolio diversification from 0 to 100.

    100 = perfectly uncorrelated, 0 = all identical movements.

    Returns:
        {
            "score": int,
            "rating": str,          # "excellent", "good", "fair", "poor"
            "highly_correlated_pairs": [{"symbol_a", "symbol_b", "correlation"}, ...],
            "suggestions": [str, ...],
        }
    """
    if len(symbols) < 2:
        return {
            "score": 100,
            "rating": "n/a",
            "highly_correlated_pairs": [],
            "suggestions": ["Add more positions to analyze diversification."],
        }

    result = calculate_correlation_matrix(symbols)
    if result.get("error"):
        return {
            "score": 0,
            "rating": "unknown",
            "highly_correlated_pairs": [],
            "suggestions": [f"Could not calculate: {result['error']}"],
        }

    pairs = result["pairs"]
    if not pairs:
        return {
            "score": 100,
            "rating": "n/a",
            "highly_correlated_pairs": [],
            "suggestions": [],
        }

    # Average absolute correlation across all pairs
    avg_abs_corr = sum(abs(p["correlation"]) for p in pairs) / len(pairs)

    # Score: 100 when avg_abs_corr = 0, 0 when avg_abs_corr = 1
    score = int(round((1.0 - avg_abs_corr) * 100))
    score = max(0, min(100, score))

    if score >= 80:
        rating = "excellent"
    elif score >= 60:
        rating = "good"
    elif score >= 40:
        rating = "fair"
    else:
        rating = "poor"

    high_pairs = [p for p in pairs if abs(p["correlation"]) > 0.7]
    high_pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)

    # Build suggestions
    suggestions = []
    if high_pairs:
        worst = high_pairs[0]
        suggestions.append(
            f"Consider reducing overlap between {worst['symbol_a']} and "
            f"{worst['symbol_b']} (corr {worst['correlation']:+.2f})."
        )
    if score < 40:
        suggestions.append(
            "Portfolio is concentrated — add positions in uncorrelated sectors "
            "(e.g., utilities, healthcare, commodities)."
        )
    elif score < 60:
        suggestions.append(
            "Diversification is fair — look for opportunities in sectors not "
            "currently represented."
        )

    if not suggestions:
        suggestions.append("Portfolio diversification looks solid.")

    return {
        "score": score,
        "rating": rating,
        "highly_correlated_pairs": high_pairs,
        "suggestions": suggestions,
    }


def format_correlation_report(symbols: list) -> str:
    """Return a human-readable correlation report."""
    if len(symbols) < 2:
        return "Need at least 2 symbols for a correlation report."

    result = calculate_correlation_matrix(symbols)
    if result.get("error"):
        return f"Correlation report unavailable: {result['error']}"

    lines = []
    lines.append("=" * 60)
    lines.append("  PORTFOLIO CORRELATION REPORT")
    lines.append("=" * 60)

    ordered = result["symbols"]
    matrix = result["matrix"]

    # Header row
    col_w = 8
    header = " " * 7
    for sym in ordered:
        header += f"{sym:>{col_w}}"
    lines.append(header)
    lines.append("-" * len(header))

    for i, sym in enumerate(ordered):
        row = f"{sym:<7}"
        for j in range(len(ordered)):
            val = matrix[i][j]
            row += f"{val:>{col_w}.2f}"
        lines.append(row)

    lines.append("")

    # Alerts
    alerts = check_portfolio_correlation(symbols)
    if alerts:
        lines.append("  CORRELATION ALERTS")
        lines.append("-" * 40)
        for alert in alerts:
            icon = "!!" if alert.risk_level == "high" else " !"
            lines.append(f"  {icon} {alert.message}")
        lines.append("")

    # Diversification score
    div = get_diversification_score(symbols)
    lines.append(f"  Diversification Score: {div['score']}/100 ({div['rating']})")

    for s in div["suggestions"]:
        lines.append(f"  -> {s}")

    lines.append("=" * 60)
    return "\n".join(lines)
