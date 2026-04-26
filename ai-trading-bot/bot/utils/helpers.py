import time
import functools
import logging

logger = logging.getLogger(__name__)


def retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    wait = delay * (backoff ** attempt)
                    logger.warning("Retry %d/%d for %s: %s (waiting %.1fs)",
                                   attempt + 1, max_attempts, func.__name__, e, wait)
                    time.sleep(wait)
            raise last_exception
        return wrapper
    return decorator


def safe_divide(numerator, denominator, default=0.0):
    """Safe division that returns default instead of raising."""
    if denominator == 0:
        return default
    return numerator / denominator


def format_currency(amount):
    """Format number as currency string."""
    if amount >= 0:
        return f"${amount:,.2f}"
    return f"-${abs(amount):,.2f}"


def format_pct(value):
    """Format number as percentage string."""
    return f"{value:+.2f}%"


def clamp(value, min_val, max_val):
    """Clamp value between min and max."""
    return max(min_val, min(max_val, value))
