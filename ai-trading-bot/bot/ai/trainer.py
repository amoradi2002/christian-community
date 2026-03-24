"""
AI Trainer - Trains the model on historical data with strategy performance feedback.

The training loop:
1. Fetch historical data for all watched symbols
2. Compute features for each time point
3. Label: look forward N days to determine BUY/SELL/HOLD
4. Include strategy performance as implicit feature weighting
5. Train and save model
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from bot.data.fetcher import fetch_market_data
from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot, IndicatorSet
from bot.ai.feature_engine import build_features, FEATURE_NAMES
from bot.ai.model import create_model, save_model
from bot.config.settings import CONFIG


def train_model(symbols=None):
    """Train the AI model on historical data."""
    if symbols is None:
        symbols = CONFIG.get("bot", {}).get("watchlist", ["SPY"])

    ai_config = CONFIG.get("ai", {})
    lookahead = ai_config.get("lookahead_days", 5)
    min_move = ai_config.get("min_move_pct", 2.0) / 100.0

    all_features = []
    all_labels = []

    for symbol in symbols:
        candles = fetch_market_data(symbol, period="2y", interval="1d")
        if len(candles) < 250:
            continue

        # Slide through history building features and labels
        for i in range(200, len(candles) - lookahead):
            window = candles[max(0, i - 200):i + 1]
            indicators = compute_indicators(window)

            snapshot = MarketSnapshot(
                symbol=symbol,
                timeframe="1d",
                candles=window,
                indicators=indicators,
            )

            features = build_features(snapshot)

            # Label: look ahead N days
            current_price = candles[i].close
            future_price = candles[i + lookahead].close
            pct_change = (future_price - current_price) / current_price

            if pct_change > min_move:
                label = 0  # BUY
            elif pct_change < -min_move:
                label = 2  # SELL
            else:
                label = 1  # HOLD

            all_features.append(features)
            all_labels.append(label)

    if len(all_features) < 50:
        print("Not enough training data. Need at least 50 samples.")
        return None

    X = np.array(all_features)
    y = np.array(all_labels)

    # Replace NaN/inf with 0
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=False  # Time-series: no shuffle
    )

    model = create_model()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"Model trained - Accuracy: {accuracy:.2%}")
    print(f"  Samples: {len(X)} (train: {len(X_train)}, test: {len(X_test)})")

    save_model(model, accuracy, FEATURE_NAMES)
    return model, accuracy
