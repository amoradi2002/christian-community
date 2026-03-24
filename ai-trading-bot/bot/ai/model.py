import pickle
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from bot.config.settings import CONFIG
from bot.db.database import get_connection


def create_model():
    """Create a new ML model based on config."""
    model_type = CONFIG.get("ai", {}).get("model_type", "gradient_boosting")
    if model_type == "random_forest":
        return RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        )
    return GradientBoostingClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
    )


def save_model(model, accuracy, feature_names):
    """Save trained model to database."""
    model_blob = pickle.dumps(model)
    features_json = str(feature_names)
    conn = get_connection()
    conn.execute(
        "INSERT INTO model_snapshots (model_blob, accuracy, features) VALUES (?, ?, ?)",
        (model_blob, accuracy, features_json),
    )
    conn.commit()
    conn.close()


def load_latest_model():
    """Load the most recently trained model."""
    conn = get_connection()
    row = conn.execute(
        "SELECT model_blob, accuracy, features FROM model_snapshots ORDER BY trained_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return None, None, None

    model = pickle.loads(row["model_blob"])
    return model, row["accuracy"], row["features"]
