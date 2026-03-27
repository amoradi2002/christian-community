"""
Model Management - Save, load, version, and compare AI models.

Stores models in the model_snapshots table with rich metadata.  Keeps the
last N versions and auto-cleans older ones.
"""

import json
import logging
import pickle
from datetime import datetime

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

from bot.config.settings import CONFIG
from bot.db.database import get_connection

logger = logging.getLogger(__name__)

MAX_MODEL_VERSIONS = 5


# ── Model creation ───────────────────────────────────────────────────────────

def create_model(model_type=None, **overrides):
    """Create a fresh ML classifier.

    Parameters
    ----------
    model_type : str, optional
        "gradient_boosting" or "random_forest".  Defaults to config value.
    **overrides : dict
        Keyword args forwarded to the sklearn constructor (e.g. n_estimators,
        max_depth, learning_rate, class_weight).
    """
    if model_type is None:
        model_type = CONFIG.get("ai", {}).get("model_type", "gradient_boosting")

    if model_type == "random_forest":
        defaults = dict(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        defaults.update(overrides)
        return RandomForestClassifier(**defaults)

    # Default: Gradient Boosting
    defaults = dict(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        min_samples_leaf=10,
        subsample=0.8,
        random_state=42,
    )
    defaults.update(overrides)
    return GradientBoostingClassifier(**defaults)


# ── Metadata helpers ─────────────────────────────────────────────────────────

def _build_metadata(
    *,
    feature_names,
    accuracy,
    accuracy_per_class=None,
    feature_importance=None,
    confusion_summary=None,
    date_range=None,
    symbols=None,
    hyperparams=None,
    walkforward_scores=None,
    model_type=None,
    num_samples=None,
):
    """Build a JSON-serialisable metadata dict."""
    meta = {
        "feature_names": list(feature_names) if feature_names else [],
        "accuracy": float(accuracy) if accuracy is not None else None,
        "trained_at": datetime.utcnow().isoformat(),
        "model_type": model_type or "unknown",
        "num_samples": num_samples,
    }
    if accuracy_per_class is not None:
        meta["accuracy_per_class"] = {
            str(k): float(v) for k, v in accuracy_per_class.items()
        }
    if feature_importance is not None:
        meta["feature_importance"] = {
            str(k): float(v) for k, v in feature_importance.items()
        }
    if confusion_summary is not None:
        meta["confusion_summary"] = confusion_summary
    if date_range is not None:
        meta["date_range"] = date_range
    if symbols is not None:
        meta["symbols"] = list(symbols)
    if hyperparams is not None:
        meta["hyperparams"] = hyperparams
    if walkforward_scores is not None:
        meta["walkforward_scores"] = [float(s) for s in walkforward_scores]
    return meta


# ── Save / Load ──────────────────────────────────────────────────────────────

def save_model(model, accuracy, feature_names, metadata=None):
    """Save a trained model to the database with metadata.

    Parameters
    ----------
    model : sklearn estimator
    accuracy : float
    feature_names : list[str]
    metadata : dict, optional
        Extra metadata (feature importance, per-class accuracy, etc.).
        If None a minimal metadata dict is built.
    """
    if metadata is None:
        metadata = _build_metadata(
            feature_names=feature_names,
            accuracy=accuracy,
        )

    model_blob = pickle.dumps(model)
    features_json = json.dumps(metadata)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO model_snapshots (model_blob, accuracy, features) "
            "VALUES (?, ?, ?)",
            (model_blob, accuracy, features_json),
        )
        conn.commit()
        logger.info("Model saved (accuracy=%.4f)", accuracy)

        # Auto-cleanup: keep only the last MAX_MODEL_VERSIONS models
        _cleanup_old_models(conn)
    finally:
        conn.close()


def _cleanup_old_models(conn):
    """Remove all but the newest MAX_MODEL_VERSIONS model rows."""
    rows = conn.execute(
        "SELECT id FROM model_snapshots ORDER BY trained_at DESC"
    ).fetchall()
    if len(rows) > MAX_MODEL_VERSIONS:
        ids_to_remove = [r["id"] for r in rows[MAX_MODEL_VERSIONS:]]
        placeholders = ",".join("?" * len(ids_to_remove))
        conn.execute(
            f"DELETE FROM model_snapshots WHERE id IN ({placeholders})",
            ids_to_remove,
        )
        conn.commit()
        logger.info("Cleaned up %d old model(s)", len(ids_to_remove))


def load_latest_model():
    """Load the most recently trained model.

    Returns
    -------
    tuple : (model, accuracy, metadata_dict) or (None, None, None)
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT model_blob, accuracy, features "
            "FROM model_snapshots ORDER BY trained_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None, None, None

    model = pickle.loads(row["model_blob"])
    accuracy = row["accuracy"]

    # Parse metadata - may be JSON dict or legacy Python list repr
    raw = row["features"]
    metadata = _parse_metadata(raw)

    return model, accuracy, metadata


def load_all_models(limit=MAX_MODEL_VERSIONS):
    """Load multiple recent models for ensemble prediction.

    Returns
    -------
    list[tuple] : [(model, accuracy, metadata), ...]
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT model_blob, accuracy, features "
            "FROM model_snapshots ORDER BY trained_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        try:
            model = pickle.loads(row["model_blob"])
            metadata = _parse_metadata(row["features"])
            results.append((model, row["accuracy"], metadata))
        except Exception as exc:
            logger.warning("Failed to load model id: %s", exc)
    return results


def _parse_metadata(raw):
    """Try to parse metadata as JSON; fall back to a minimal dict."""
    if raw is None:
        return {}
    try:
        meta = json.loads(raw)
        if isinstance(meta, dict):
            return meta
    except (json.JSONDecodeError, TypeError):
        pass
    # Legacy format: the old code stored str(feature_names)
    return {"feature_names_legacy": raw}


# ── Model comparison ─────────────────────────────────────────────────────────

def compare_models():
    """Print a comparison table of all stored models.

    Returns a list of summary dicts.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, accuracy, features, trained_at "
            "FROM model_snapshots ORDER BY trained_at DESC"
        ).fetchall()
    finally:
        conn.close()

    summaries = []
    for row in rows:
        meta = _parse_metadata(row["features"])
        summary = {
            "id": row["id"],
            "trained_at": row["trained_at"],
            "accuracy": row["accuracy"],
            "model_type": meta.get("model_type", "unknown"),
            "num_samples": meta.get("num_samples"),
            "symbols": meta.get("symbols"),
            "walkforward_avg": None,
        }
        wf = meta.get("walkforward_scores")
        if wf:
            summary["walkforward_avg"] = float(np.mean(wf))
        summaries.append(summary)

    # Print table
    print(f"\n{'ID':>4}  {'Trained At':<20}  {'Accuracy':>8}  {'WF Avg':>8}  "
          f"{'Type':<18}  {'Samples':>7}  Symbols")
    print("-" * 95)
    for s in summaries:
        wf_str = f"{s['walkforward_avg']:.2%}" if s["walkforward_avg"] else "   N/A"
        acc_str = f"{s['accuracy']:.2%}" if s["accuracy"] else "   N/A"
        sym_str = ", ".join(s["symbols"][:5]) if s["symbols"] else "N/A"
        samp_str = str(s["num_samples"]) if s["num_samples"] else "N/A"
        print(f"{s['id']:>4}  {str(s['trained_at']):<20}  {acc_str:>8}  "
              f"{wf_str:>8}  {s['model_type']:<18}  {samp_str:>7}  {sym_str}")
    print()

    return summaries
