import numpy as np
from bot.ai.feature_engine import build_features
from bot.ai.model import load_latest_model
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal

LABELS = {0: "BUY", 1: "HOLD", 2: "SELL"}


def predict_signal(snapshot: MarketSnapshot) -> Signal | None:
    """Run AI prediction on a market snapshot."""
    model, accuracy, _ = load_latest_model()
    if model is None:
        return None

    features = build_features(snapshot)
    features = np.nan_to_num(features.reshape(1, -1), nan=0.0, posinf=0.0, neginf=0.0)

    prediction = model.predict(features)[0]
    probabilities = model.predict_proba(features)[0]

    action = LABELS.get(prediction, "HOLD")
    confidence = float(probabilities[prediction])

    if action == "HOLD":
        return None

    return Signal(
        action=action,
        confidence=confidence,
        strategy_name="AI Model",
        symbol=snapshot.symbol,
        price=snapshot.latest.close,
        reasons=[
            f"AI prediction: {action} (confidence: {confidence:.1%})",
            f"Model accuracy: {accuracy:.1%}" if accuracy else "No accuracy data",
        ],
    )
