"""
AI Trainer - Walk-forward validated training with MFE/MAE labeling.

Training pipeline:
1. Fetch historical data for all watched symbols
2. Compute expanded features (40+) for each time point
3. Label using Max Favorable / Adverse Excursion (not simple future price)
4. Walk-forward cross-validation (chronological folds)
5. Hyperparameter search across a small grid
6. Feature importance analysis
7. Save best model with rich metadata
"""

import logging
import time
from collections import Counter
from itertools import product

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)

from bot.ai.feature_engine import FEATURE_NAMES, NUM_FEATURES, build_features
from bot.ai.model import (
    _build_metadata,
    create_model,
    save_model,
)
from bot.config.settings import CONFIG
from bot.data.fetcher import fetch_market_data
from bot.data.indicators import compute_indicators
from bot.data.models import MarketSnapshot

logger = logging.getLogger(__name__)

LABEL_BUY = 0
LABEL_HOLD = 1
LABEL_SELL = 2
LABEL_NAMES = {LABEL_BUY: "BUY", LABEL_HOLD: "HOLD", LABEL_SELL: "SELL"}


# ── Labeling ─────────────────────────────────────────────────────────────────

def _label_mfe_mae(candles, idx, window, profit_target, stop_loss):
    """Label a data point using Max Favorable / Adverse Excursion.

    Look forward up to *window* bars from *idx*.
    - BUY (0):  price reaches +profit_target% before hitting -stop_loss%
    - SELL (2): price reaches -profit_target% before hitting +stop_loss%
    - HOLD (1): neither target hit within the window

    Parameters
    ----------
    candles : list[Candle]
    idx : int          – index of the current bar
    window : int       – how many bars to look ahead
    profit_target : float – e.g. 0.02 for 2 %
    stop_loss : float     – e.g. 0.01 for 1 %

    Returns
    -------
    int : LABEL_BUY, LABEL_HOLD, or LABEL_SELL
    """
    current_close = candles[idx].close
    if current_close <= 0:
        return LABEL_HOLD

    end = min(idx + window + 1, len(candles))

    max_up = 0.0
    max_down = 0.0
    buy_bar = None
    sell_bar = None

    for j in range(idx + 1, end):
        hi = candles[j].high
        lo = candles[j].low

        up_pct = (hi - current_close) / current_close
        down_pct = (current_close - lo) / current_close

        if up_pct > max_up:
            max_up = up_pct
        if down_pct > max_down:
            max_down = down_pct

        # Check buy condition: profit target reached before stop
        if buy_bar is None and up_pct >= profit_target:
            buy_bar = j
        # Check sell condition: adverse move target reached before stop
        if sell_bar is None and down_pct >= profit_target:
            sell_bar = j

        # Check if stops are hit
        if buy_bar is None and down_pct >= stop_loss:
            # Stop hit on long side before reaching profit target
            # This bar is not a BUY setup
            pass
        if sell_bar is None and up_pct >= stop_loss:
            # Stop hit on short side
            pass

    # Determine label based on which target was hit first
    if buy_bar is not None and sell_bar is not None:
        # Both targets hit - whichever came first wins
        if buy_bar <= sell_bar:
            # Verify stop wasn't hit before buy_bar
            for j in range(idx + 1, buy_bar):
                down_pct = (current_close - candles[j].low) / current_close
                if down_pct >= stop_loss:
                    return LABEL_HOLD
            return LABEL_BUY
        else:
            # Verify stop wasn't hit before sell_bar
            for j in range(idx + 1, sell_bar):
                up_pct = (candles[j].high - current_close) / current_close
                if up_pct >= stop_loss:
                    return LABEL_HOLD
            return LABEL_SELL
    elif buy_bar is not None:
        # Only buy target hit - verify stop wasn't hit first
        for j in range(idx + 1, buy_bar):
            down_pct = (current_close - candles[j].low) / current_close
            if down_pct >= stop_loss:
                return LABEL_HOLD
        return LABEL_BUY
    elif sell_bar is not None:
        # Only sell target hit - verify stop wasn't hit first
        for j in range(idx + 1, sell_bar):
            up_pct = (candles[j].high - current_close) / current_close
            if up_pct >= stop_loss:
                return LABEL_HOLD
        return LABEL_SELL

    return LABEL_HOLD


# ── Data preparation ─────────────────────────────────────────────────────────

def _prepare_dataset(symbols, lookback=200, window=10, profit_target=0.02,
                     stop_loss=0.01, period="2y"):
    """Build feature matrix X and label vector y from historical data.

    Returns
    -------
    X : np.ndarray (n_samples, n_features)
    y : np.ndarray (n_samples,)
    dates : list[str]  – date strings aligned with rows
    symbols_col : list[str] – symbol for each row
    """
    all_features = []
    all_labels = []
    all_dates = []
    all_symbols = []

    for symbol in symbols:
        candles = fetch_market_data(symbol, period=period, interval="1d")
        if candles is None or len(candles) < lookback + window + 1:
            print(f"  [{symbol}] skipped – not enough data ({len(candles) if candles else 0} bars)")
            continue

        n_samples = 0
        for i in range(lookback, len(candles) - window):
            hist = candles[max(0, i - lookback): i + 1]
            indicators = compute_indicators(hist)
            snapshot = MarketSnapshot(
                symbol=symbol,
                timeframe="1d",
                candles=hist,
                indicators=indicators,
            )

            features = build_features(snapshot)
            label = _label_mfe_mae(candles, i, window, profit_target, stop_loss)

            all_features.append(features)
            all_labels.append(label)
            all_dates.append(candles[i].date)
            all_symbols.append(symbol)
            n_samples += 1

        print(f"  [{symbol}] {n_samples} samples generated")

    if not all_features:
        return None, None, None, None

    X = np.array(all_features, dtype=np.float64)
    y = np.array(all_labels, dtype=np.int32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, y, all_dates, all_symbols


# ── Walk-forward validation ──────────────────────────────────────────────────

def _walkforward_split(n_samples, n_folds=5, min_train_size=100):
    """Generate chronological walk-forward train/val index pairs.

    Expanding window: each fold adds one segment to training.

    Yields (train_indices, val_indices) tuples.
    """
    fold_size = n_samples // (n_folds + 1)
    if fold_size < 20:
        # Not enough data for the requested folds; use 2 folds
        fold_size = n_samples // 3
        n_folds = 2

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        val_start = train_end
        val_end = min(val_start + fold_size, n_samples)

        if train_end < min_train_size or val_start >= n_samples:
            continue

        train_idx = np.arange(0, train_end)
        val_idx = np.arange(val_start, val_end)
        if len(val_idx) == 0:
            continue
        yield train_idx, val_idx


def _evaluate_fold(model, X_val, y_val):
    """Score a model on validation data.  Returns accuracy."""
    y_pred = model.predict(X_val)
    return accuracy_score(y_val, y_pred)


# ── Hyperparameter grid ─────────────────────────────────────────────────────

_HP_GRID_GB = [
    {"n_estimators": 150, "max_depth": 4, "learning_rate": 0.05},
    {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05},
    {"n_estimators": 250, "max_depth": 5, "learning_rate": 0.03},
    {"n_estimators": 200, "max_depth": 6, "learning_rate": 0.05},
    {"n_estimators": 300, "max_depth": 4, "learning_rate": 0.02},
]

_HP_GRID_RF = [
    {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 10},
    {"n_estimators": 300, "max_depth": 12, "min_samples_leaf": 8},
    {"n_estimators": 200, "max_depth": 15, "min_samples_leaf": 12},
    {"n_estimators": 400, "max_depth": 10, "min_samples_leaf": 15},
]


def _get_hp_grid(model_type):
    if model_type == "random_forest":
        return _HP_GRID_RF
    return _HP_GRID_GB


# ── Feature importance ───────────────────────────────────────────────────────

def _extract_feature_importance(model, feature_names):
    """Extract feature importance dict from a trained model."""
    importance = {}
    if hasattr(model, "feature_importances_"):
        for name, imp in zip(feature_names, model.feature_importances_):
            importance[name] = round(float(imp), 6)
    return importance


def _print_top_features(importance, top_n=10):
    """Print the top N most important features."""
    if not importance:
        return
    sorted_feats = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top {top_n} features:")
    for i, (name, imp) in enumerate(sorted_feats[:top_n], 1):
        bar = "#" * int(imp * 200)
        print(f"    {i:>2}. {name:<28} {imp:.4f}  {bar}")


# ── Per-class accuracy ───────────────────────────────────────────────────────

def _per_class_accuracy(y_true, y_pred, label_names=None):
    """Compute accuracy for each class individually."""
    if label_names is None:
        label_names = LABEL_NAMES
    results = {}
    for cls_id, cls_name in label_names.items():
        mask = y_true == cls_id
        if mask.sum() == 0:
            results[cls_name] = 0.0
        else:
            results[cls_name] = float(accuracy_score(y_true[mask], y_pred[mask]))
    return results


# ── Main training function ───────────────────────────────────────────────────

def train_model(symbols=None, per_symbol=False):
    """Train the AI model on historical data.

    Parameters
    ----------
    symbols : list[str], optional
        Symbols to train on.  Defaults to config watchlist.
    per_symbol : bool
        If True, train a separate model for each symbol and save the best.
        If False (default), train one universal model on all symbols.

    Returns
    -------
    tuple : (model, metadata_dict) or None on failure.
    """
    if symbols is None:
        symbols = CONFIG.get("bot", {}).get("watchlist", ["SPY"])

    ai_config = CONFIG.get("ai", {})
    window = ai_config.get("lookahead_days", 10)
    profit_target = ai_config.get("profit_target_pct", 2.0) / 100.0
    stop_loss = ai_config.get("stop_loss_pct", 1.0) / 100.0
    model_type = ai_config.get("model_type", "gradient_boosting")
    n_folds = ai_config.get("walkforward_folds", 5)
    period = ai_config.get("training_period", "2y")

    if per_symbol:
        return _train_per_symbol(symbols, window, profit_target, stop_loss,
                                 model_type, n_folds, period)

    return _train_universal(symbols, window, profit_target, stop_loss,
                            model_type, n_folds, period)


def _train_universal(symbols, window, profit_target, stop_loss,
                     model_type, n_folds, period):
    """Train a single model on data from all symbols."""
    print(f"\n{'='*60}")
    print(f"  AI TRAINING - Universal Model")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Window: {window} days | Target: +{profit_target*100:.1f}% / -{stop_loss*100:.1f}%")
    print(f"  Model: {model_type} | Walk-forward folds: {n_folds}")
    print(f"{'='*60}")

    print("\n[1/5] Preparing dataset...")
    t0 = time.time()
    X, y, dates, sym_col = _prepare_dataset(
        symbols, window=window, profit_target=profit_target,
        stop_loss=stop_loss, period=period,
    )

    if X is None or len(X) < 100:
        print("Not enough training data. Need at least 100 samples.")
        return None

    elapsed = time.time() - t0
    print(f"  Dataset ready: {X.shape[0]} samples, {X.shape[1]} features ({elapsed:.1f}s)")

    label_counts = Counter(y)
    for lid, lname in LABEL_NAMES.items():
        cnt = label_counts.get(lid, 0)
        pct = cnt / len(y) * 100
        print(f"  {lname}: {cnt} ({pct:.1f}%)")

    # ── Hyperparameter search with walk-forward CV ─────────────────────
    print(f"\n[2/5] Hyperparameter search ({model_type})...")
    hp_grid = _get_hp_grid(model_type)
    best_score = -1
    best_hp = hp_grid[0]
    best_fold_scores = []

    for hp_idx, hp in enumerate(hp_grid):
        fold_scores = []
        for train_idx, val_idx in _walkforward_split(len(X), n_folds):
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_val, y_val = X[val_idx], y[val_idx]

            model = create_model(model_type, **hp)

            # GradientBoosting doesn't accept class_weight directly;
            # use sample_weight instead
            if model_type == "gradient_boosting":
                class_counts = Counter(y_tr)
                total = len(y_tr)
                n_classes = len(class_counts) if class_counts else 1
                weights = {c: total / (n_classes * cnt)
                           for c, cnt in class_counts.items()}
                sample_w = np.array([weights.get(yi, 1.0) for yi in y_tr])
                model.fit(X_tr, y_tr, sample_weight=sample_w)
            else:
                model.fit(X_tr, y_tr)

            score = _evaluate_fold(model, X_val, y_val)
            fold_scores.append(score)

        avg = float(np.mean(fold_scores))
        print(f"  Config {hp_idx+1}/{len(hp_grid)}: avg={avg:.2%}  "
              f"folds={[f'{s:.2%}' for s in fold_scores]}  params={hp}")

        if avg > best_score:
            best_score = avg
            best_hp = hp
            best_fold_scores = fold_scores

    print(f"\n  Best config: {best_hp}  (avg walk-forward acc: {best_score:.2%})")

    # ── Train final model on all data with best params ───────────────────
    print(f"\n[3/5] Training final model on full dataset...")
    final_model = create_model(model_type, **best_hp)

    if model_type == "gradient_boosting":
        class_counts = Counter(y)
        total = len(y)
        n_classes = len(class_counts) if class_counts else 1
        weights = {c: total / (n_classes * cnt) for c, cnt in class_counts.items()}
        sample_w = np.array([weights.get(yi, 1.0) for yi in y])
        final_model.fit(X, y, sample_weight=sample_w)
    else:
        final_model.fit(X, y)

    # ── Evaluation on last fold (out-of-sample proxy) ────────────────────
    print(f"\n[4/5] Evaluation (last walk-forward fold)...")

    # Re-run last fold for detailed stats
    folds = list(_walkforward_split(len(X), n_folds))
    if folds:
        last_train_idx, last_val_idx = folds[-1]
        eval_model = create_model(model_type, **best_hp)
        X_tr, y_tr = X[last_train_idx], y[last_train_idx]
        X_val, y_val = X[last_val_idx], y[last_val_idx]

        if model_type == "gradient_boosting":
            class_counts = Counter(y_tr)
            total = len(y_tr)
            n_classes = len(class_counts) if class_counts else 1
            weights = {c: total / (n_classes * cnt) for c, cnt in class_counts.items()}
            sample_w = np.array([weights.get(yi, 1.0) for yi in y_tr])
            eval_model.fit(X_tr, y_tr, sample_weight=sample_w)
        else:
            eval_model.fit(X_tr, y_tr)

        y_pred = eval_model.predict(X_val)
        overall_acc = accuracy_score(y_val, y_pred)
        per_class = _per_class_accuracy(y_val, y_pred)

        # Confusion matrix
        labels_present = sorted(set(y_val) | set(y_pred))
        cm = confusion_matrix(y_val, y_pred, labels=labels_present)
        cm_names = [LABEL_NAMES.get(l, str(l)) for l in labels_present]

        print(f"\n  Overall accuracy (last fold): {overall_acc:.2%}")
        for cls_name, acc in per_class.items():
            print(f"    {cls_name}: {acc:.2%}")

        print(f"\n  Confusion matrix ({' / '.join(cm_names)}):")
        header = "  Predicted ->  " + "  ".join(f"{n:>6}" for n in cm_names)
        print(header)
        for i, row_label in enumerate(cm_names):
            row_vals = "  ".join(f"{cm[i, j]:>6}" for j in range(len(cm_names)))
            print(f"  {row_label:<12}    {row_vals}")
    else:
        overall_acc = best_score
        per_class = {}
        cm = None

    # ── Feature importance ───────────────────────────────────────────────
    print(f"\n[5/5] Feature importance...")
    importance = _extract_feature_importance(final_model, FEATURE_NAMES)
    _print_top_features(importance, top_n=10)

    # ── Build metadata & save ────────────────────────────────────────────
    date_range = None
    if dates:
        date_range = {"start": dates[0], "end": dates[-1]}

    confusion_summary = None
    if cm is not None:
        confusion_summary = {
            "labels": cm_names,
            "matrix": cm.tolist(),
        }

    metadata = _build_metadata(
        feature_names=FEATURE_NAMES,
        accuracy=overall_acc,
        accuracy_per_class=per_class,
        feature_importance=importance,
        confusion_summary=confusion_summary,
        date_range=date_range,
        symbols=symbols,
        hyperparams=best_hp,
        walkforward_scores=best_fold_scores,
        model_type=model_type,
        num_samples=len(X),
    )

    save_model(final_model, overall_acc, FEATURE_NAMES, metadata=metadata)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  TRAINING COMPLETE")
    print(f"  Walk-forward accuracy: {best_score:.2%}  (std: {np.std(best_fold_scores):.2%})")
    print(f"  Last fold accuracy:    {overall_acc:.2%}")
    print(f"  Samples: {len(X)} | Features: {NUM_FEATURES}")
    print(f"  Hyperparams: {best_hp}")
    print(f"{'='*60}\n")

    return final_model, metadata


def _train_per_symbol(symbols, window, profit_target, stop_loss,
                      model_type, n_folds, period):
    """Train a model for each symbol; save the best one."""
    print(f"\n  Per-symbol training for {len(symbols)} symbols...")
    best_overall = None
    best_meta = None
    best_acc = -1

    for symbol in symbols:
        print(f"\n--- Training model for {symbol} ---")
        result = _train_universal(
            [symbol], window, profit_target, stop_loss,
            model_type, n_folds, period,
        )
        if result is not None:
            model, metadata = result
            acc = metadata.get("accuracy", 0)
            if acc > best_acc:
                best_acc = acc
                best_overall = model
                best_meta = metadata

    if best_overall is None:
        print("No per-symbol models produced a valid result.")
        return None

    print(f"\nBest per-symbol model: accuracy={best_acc:.2%}, "
          f"symbol(s)={best_meta.get('symbols')}")
    return best_overall, best_meta
