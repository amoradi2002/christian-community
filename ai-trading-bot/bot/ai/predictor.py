"""
AI Predictor - Enhanced prediction with ensemble averaging, explanation,
and confidence calibration.
"""

import logging

import numpy as np

from bot.ai.feature_engine import FEATURE_NAMES, NUM_FEATURES, build_features
from bot.ai.model import load_all_models, load_latest_model
from bot.data.models import MarketSnapshot
from bot.engine.signal import Signal

logger = logging.getLogger(__name__)

LABELS = {0: "BUY", 1: "HOLD", 2: "SELL"}


# ── Explanation helpers ──────────────────────────────────────────────────────

def _explain_prediction(model, features, prediction, feature_names, top_n=5):
    """Identify which features contributed most to this prediction.

    Uses feature_importances_ weighted by the feature's deviation from
    the training-set mean (approximated as 0 for normalized features).

    Returns a list of (feature_name, contribution_score) tuples.
    """
    explanations = []

    if not hasattr(model, "feature_importances_"):
        return explanations

    importances = model.feature_importances_
    flat = features.flatten()

    if len(importances) != len(flat):
        return explanations

    # Contribution = importance * |feature_value|  (rough proxy)
    contributions = importances * np.abs(flat)
    indices = np.argsort(contributions)[::-1][:top_n]

    for idx in indices:
        name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        explanations.append((name, float(flat[idx]), float(contributions[idx])))

    return explanations


def _calibrate_confidence(raw_confidence, model_accuracy, action):
    """Adjust raw model probability based on historical accuracy.

    Blends the model's probability output with its walk-forward accuracy
    to produce a more calibrated confidence score.

    - If model accuracy is low, we dampen confidence.
    - If model accuracy is high, we trust the raw probability more.
    - HOLD predictions pass through unchanged.
    """
    if action == "HOLD":
        return raw_confidence

    if model_accuracy is None or model_accuracy <= 0:
        # No accuracy data: apply a conservative 20% discount
        return raw_confidence * 0.80

    # Blend: weighted average of raw probability and accuracy
    # This prevents overconfident predictions from weak models
    alpha = 0.6  # weight on raw probability
    calibrated = alpha * raw_confidence + (1 - alpha) * model_accuracy

    # Clamp
    return max(0.01, min(0.99, calibrated))


# ── Ensemble prediction ─────────────────────────────────────────────────────

def _ensemble_predict(models_data, features):
    """Average predictions across multiple models.

    Parameters
    ----------
    models_data : list of (model, accuracy, metadata)
    features : np.ndarray of shape (1, n_features)

    Returns
    -------
    dict with keys: action, confidence, per_model_votes, avg_probabilities
    """
    all_probas = []
    votes = []
    weights = []

    for model, accuracy, metadata in models_data:
        try:
            # Verify feature count compatibility
            if hasattr(model, "n_features_in_") and model.n_features_in_ != features.shape[1]:
                logger.debug(
                    "Skipping model: expected %d features, got %d",
                    model.n_features_in_, features.shape[1],
                )
                continue

            proba = model.predict_proba(features)[0]
            pred = model.predict(features)[0]

            # Pad probabilities if model was trained with fewer classes
            if len(proba) < 3:
                padded = np.zeros(3)
                classes = model.classes_
                for i, cls in enumerate(classes):
                    if cls < 3:
                        padded[cls] = proba[i]
                proba = padded

            all_probas.append(proba)
            votes.append(int(pred))
            # Weight by accuracy (higher accuracy = more influence)
            w = accuracy if accuracy and accuracy > 0 else 0.5
            weights.append(w)
        except Exception as exc:
            logger.debug("Model prediction failed: %s", exc)
            continue

    if not all_probas:
        return None

    # Weighted average of probabilities
    weights = np.array(weights)
    weights = weights / weights.sum()
    avg_proba = np.zeros(3)
    for w, p in zip(weights, all_probas):
        avg_proba += w * p

    best_class = int(np.argmax(avg_proba))
    confidence = float(avg_proba[best_class])
    action = LABELS.get(best_class, "HOLD")

    return {
        "action": action,
        "prediction": best_class,
        "confidence": confidence,
        "avg_probabilities": avg_proba.tolist(),
        "per_model_votes": [LABELS.get(v, "HOLD") for v in votes],
        "n_models": len(all_probas),
    }


# ── Public API ───────────────────────────────────────────────────────────────

def predict_signal(snapshot: MarketSnapshot, use_ensemble=True) -> Signal | None:
    """Run AI prediction on a market snapshot.

    Parameters
    ----------
    snapshot : MarketSnapshot
    use_ensemble : bool
        If True and multiple models exist, average their predictions.

    Returns
    -------
    Signal or None (if prediction is HOLD or no model available)
    """
    features = build_features(snapshot)
    features = np.nan_to_num(
        features.reshape(1, -1), nan=0.0, posinf=0.0, neginf=0.0
    )

    # ── Try ensemble first ───────────────────────────────────────────────
    ensemble_result = None
    if use_ensemble:
        models_data = load_all_models(limit=3)
        if len(models_data) >= 2:
            ensemble_result = _ensemble_predict(models_data, features)

    if ensemble_result is not None:
        action = ensemble_result["action"]
        raw_confidence = ensemble_result["confidence"]
        prediction = ensemble_result["prediction"]

        # Use the latest model's accuracy for calibration
        _, latest_accuracy, latest_meta = load_latest_model()
        confidence = _calibrate_confidence(raw_confidence, latest_accuracy, action)

        if action == "HOLD":
            return None

        # Explanations from the latest model
        latest_model = models_data[0][0] if models_data else None
        explanations = []
        if latest_model:
            explanations = _explain_prediction(
                latest_model, features, prediction, FEATURE_NAMES
            )

        reasons = _build_reasons(
            action, confidence, raw_confidence, latest_accuracy,
            explanations, ensemble_result,
        )

        return Signal(
            action=action,
            confidence=confidence,
            strategy_name="AI Model (Ensemble)",
            symbol=snapshot.symbol,
            price=snapshot.latest.close,
            reasons=reasons,
        )

    # ── Single model fallback ────────────────────────────────────────────
    model, accuracy, metadata = load_latest_model()
    if model is None:
        return None

    try:
        prediction = model.predict(features)[0]
        probabilities = model.predict_proba(features)[0]
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        return None

    action = LABELS.get(prediction, "HOLD")
    raw_confidence = float(probabilities[prediction]) if prediction < len(probabilities) else 0.0
    confidence = _calibrate_confidence(raw_confidence, accuracy, action)

    if action == "HOLD":
        return None

    explanations = _explain_prediction(model, features, prediction, FEATURE_NAMES)

    reasons = _build_reasons(
        action, confidence, raw_confidence, accuracy,
        explanations, ensemble_result=None,
    )

    return Signal(
        action=action,
        confidence=confidence,
        strategy_name="AI Model",
        symbol=snapshot.symbol,
        price=snapshot.latest.close,
        reasons=reasons,
    )


def _build_reasons(action, confidence, raw_confidence, accuracy,
                   explanations, ensemble_result):
    """Assemble a list of human-readable reason strings."""
    reasons = [
        f"AI prediction: {action} (calibrated confidence: {confidence:.1%})",
    ]

    if accuracy:
        reasons.append(f"Model walk-forward accuracy: {accuracy:.1%}")

    if ensemble_result:
        votes = ensemble_result.get("per_model_votes", [])
        n = ensemble_result.get("n_models", 0)
        agreement = votes.count(action) / len(votes) if votes else 0
        reasons.append(
            f"Ensemble: {n} models, {agreement:.0%} agreement "
            f"(votes: {', '.join(votes)})"
        )

    if raw_confidence != confidence:
        reasons.append(f"Raw model probability: {raw_confidence:.1%}")

    if explanations:
        top_feats = ", ".join(
            f"{name}={val:.3f}" for name, val, _ in explanations[:3]
        )
        reasons.append(f"Top contributing features: {top_feats}")

    return reasons
