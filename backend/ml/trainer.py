from __future__ import annotations

import os
from typing import Any, Dict, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from core.config import DATA_DIR, MLFLOW_TRACKING_URI
from core.logger import get_logger
from ml.profiler import FORBIDDEN_LEAKAGE_COLUMNS
from models.schemas import TrainingPlan

logger = get_logger(__name__)

NUMERIC_CANDIDATES = [
    "price",
    "log_price",
    "cost",
    "is_promotion",
    "inventory_level",
    "is_holiday",
    "is_festival",
    "day_of_week",
    "is_weekend",
    "month",
    "quarter",
    "day",
    "week_of_year",
    "lag_1_units",
    "rolling_7_units",
    "rolling_7_price",
    "price_ratio_to_avg",
]
CATEGORICAL_CANDIDATES = ["product_id", "channel"]


def _select_feature_columns(df: pd.DataFrame, plan: TrainingPlan) -> Tuple[list[str], list[str]]:
    forbidden = FORBIDDEN_LEAKAGE_COLUMNS | {"units_sold", "date", "order_count", "is_closed"}
    numeric_cols = [
        c for c in NUMERIC_CANDIDATES
        if c in df.columns and c not in forbidden
    ]
    if not plan.use_log_price and "log_price" in numeric_cols:
        numeric_cols.remove("log_price")
    if not plan.enable_lags:
        for lag_col in ("lag_1_units", "rolling_7_units", "rolling_7_price", "price_ratio_to_avg"):
            if lag_col in numeric_cols:
                numeric_cols.remove(lag_col)

    # Drop numeric columns that are 100% NaN
    numeric_cols = [c for c in numeric_cols if df[c].notna().any()]
    cat_cols = [c for c in CATEGORICAL_CANDIDATES if c in df.columns and c not in forbidden]
    return numeric_cols, cat_cols


def _build_preprocessor(numeric_cols: list[str], cat_cols: list[str], scale_numeric: bool = False) -> ColumnTransformer:
    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        num_steps.append(("scaler", StandardScaler()))
    num_pipe = Pipeline(num_steps)

    transformers = [("num", num_pipe, numeric_cols)]
    if cat_cols:
        cat_pipe = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
            ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])
        transformers.append(("cat", cat_pipe, cat_cols))

    return ColumnTransformer(transformers=transformers, remainder="drop")


def _monotonic_vector(numeric_cols: list[str], total_transformed_features: int) -> list[int]:
    """Enforce non-increasing demand (-1) with respect to price features."""
    cst = [0] * total_transformed_features
    for idx, col in enumerate(numeric_cols):
        if col in {"price", "log_price", "price_ratio_to_avg"}:
            cst[idx] = -1
    return cst


def _make_candidate_pipeline(
    model_key: str,
    numeric_cols: list[str],
    cat_cols: list[str],
    transformed_dim: int,
) -> Tuple[str, Pipeline]:
    if model_key == "ridge_elasticity":
        prep = _build_preprocessor(numeric_cols, cat_cols, scale_numeric=True)
        reg = TransformedTargetRegressor(
            regressor=Ridge(alpha=2.0),
            func=np.log1p,
            inverse_func=lambda x: np.maximum(np.expm1(np.clip(x, -10, 20)), 0.0),
        )
        return "RidgeElasticity", Pipeline([("prep", prep), ("model", reg)])

    prep = _build_preprocessor(numeric_cols, cat_cols, scale_numeric=False)
    mono = _monotonic_vector(numeric_cols, transformed_dim)

    if model_key == "hist_gb_monotonic":
        est = HistGradientBoostingRegressor(
            max_iter=200,
            max_depth=5,
            learning_rate=0.06,
            min_samples_leaf=5,
            monotonic_cst=mono,
            random_state=42,
        )
        return "HistGradientBoostingMonotonic", Pipeline([("prep", prep), ("model", est)])

    if model_key == "hist_gb_poisson":
        est = HistGradientBoostingRegressor(
            loss="poisson",
            max_iter=200,
            max_depth=5,
            learning_rate=0.06,
            min_samples_leaf=5,
            monotonic_cst=mono,
            random_state=42,
        )
        return "HistGradientBoostingPoisson", Pipeline([("prep", prep), ("model", est)])

    if model_key == "extra_trees":
        est = ExtraTreesRegressor(n_estimators=200, min_samples_leaf=2, random_state=42, n_jobs=1)
        return "ExtraTreesRegressor", Pipeline([("prep", prep), ("model", est)])

    est = RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=42, n_jobs=1)
    return "RandomForestRegressor", Pipeline([("prep", prep), ("model", est)])


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_pred_clean = np.maximum(np.asarray(y_pred, dtype=float), 0.0)
    y_true_arr = np.asarray(y_true, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true_arr, y_pred_clean)))
    mae = float(mean_absolute_error(y_true_arr, y_pred_clean))
    r2 = float(r2_score(y_true_arr, y_pred_clean)) if len(y_true_arr) > 1 and np.var(y_true_arr) > 0 else 0.0
    mape = float(np.mean(np.abs(y_true_arr - y_pred_clean) / np.maximum(y_true_arr, 1.0)))
    return {
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "r2": round(r2, 4),
        "mape": round(mape, 4),
    }


def train_best_pipeline(
    daily_df: pd.DataFrame,
    unique_id: str,
    plan: TrainingPlan,
    profile: dict,
) -> Dict[str, Any]:
    """Benchmark candidate pipelines chronologically, refit best on full data, and persist bundle."""
    df = daily_df.sort_values("date").reset_index(drop=True)
    if len(df) < 10:
        raise ValueError(f"Need at least 10 aggregated daily SKU records to train (got {len(df)}).")

    if plan.outlier_clip_quantile and plan.outlier_clip_quantile < 1.0:
        upper = float(df["units_sold"].quantile(plan.outlier_clip_quantile))
        df["units_sold"] = df["units_sold"].clip(upper=max(upper, 1.0))

    numeric_cols, cat_cols = _select_feature_columns(df, plan)
    if "price" not in numeric_cols:
        raise ValueError("Price column is required for training.")

    feature_cols = numeric_cols + cat_cols
    X = df[feature_cols].copy()
    y = df["units_sold"].astype(float).values

    # Fit a sample preprocessor to know exact transformed column count for monotonic_cst
    sample_prep = _build_preprocessor(numeric_cols, cat_cols, scale_numeric=False)
    transformed_sample = sample_prep.fit_transform(X)
    transformed_dim = transformed_sample.shape[1]

    # Chronological validation
    use_tscv = len(df) < 60
    candidates_results = []
    best_key = None
    best_name = None
    best_metrics = None
    best_rmse = float("inf")
    best_residuals = None

    for model_key in plan.candidate_models:
        try:
            display_name, pipe = _make_candidate_pipeline(model_key, numeric_cols, cat_cols, transformed_dim)
            if use_tscv:
                n_splits = min(4, max(2, len(df) // 8))
                tscv = TimeSeriesSplit(n_splits=n_splits)
                oos_true, oos_pred = [], []
                for tr_idx, va_idx in tscv.split(X):
                    y_tr = y[tr_idx]
                    if model_key == "hist_gb_poisson" and np.any(y_tr < 0):
                        continue
                    pipe.fit(X.iloc[tr_idx], y_tr)
                    preds = np.maximum(pipe.predict(X.iloc[va_idx]), 0.0)
                    oos_true.extend(y[va_idx])
                    oos_pred.extend(preds)
                if not oos_true:
                    continue
                metrics = _compute_metrics(np.array(oos_true), np.array(oos_pred))
                residuals = np.array(oos_true) - np.array(oos_pred)
            else:
                split_idx = min(max(int(len(df) * 0.8), 1), len(df) - 1)
                X_tr, X_va = X.iloc[:split_idx], X.iloc[split_idx:]
                y_tr, y_va = y[:split_idx], y[split_idx:]
                pipe.fit(X_tr, y_tr)
                preds = np.maximum(pipe.predict(X_va), 0.0)
                metrics = _compute_metrics(y_va, preds)
                residuals = y_va - preds

            candidates_results.append({"model_key": model_key, "model_name": display_name, **metrics})
            if metrics["rmse"] < best_rmse:
                best_rmse = metrics["rmse"]
                best_key = model_key
                best_name = display_name
                best_metrics = metrics
                best_residuals = residuals
        except Exception as e:
            logger.warning(f"Candidate model {model_key} failed during evaluation: {e}")

    if best_key is None or best_metrics is None:
        raise RuntimeError("All candidate models failed to train on the provided dataset.")

    # Refit winning pipeline on all available daily history
    _, final_pipeline = _make_candidate_pipeline(best_key, numeric_cols, cat_cols, transformed_dim)
    final_pipeline.fit(X, y)

    # Compute permutation importance on raw input columns (clean & model-agnostic)
    feature_importance: Dict[str, float] = {}
    try:
        perm = permutation_importance(
            final_pipeline,
            X,
            y,
            n_repeats=5,
            random_state=42,
            scoring="neg_root_mean_squared_error",
        )
        raw_imp = np.maximum(perm.importances_mean, 0.0)
        total_imp = float(raw_imp.sum())
        if total_imp > 0:
            feature_importance = {
                col: round(float(val / total_imp), 4)
                for col, val in sorted(zip(feature_cols, raw_imp), key=lambda kv: kv[1], reverse=True)
            }
    except Exception as e:
        logger.warning(f"Permutation importance skipped: {e}")

    # Residual std per SKU (for safety stock uncertainty)
    in_sample_preds = np.maximum(final_pipeline.predict(X), 0.0)
    sku_residual_std: Dict[str, float] = {}
    df_res = pd.DataFrame({"product_id": df["product_id"].astype(str), "err": np.abs(y - in_sample_preds)})
    global_std = float(np.std(best_residuals)) if best_residuals is not None and len(best_residuals) > 1 else float(best_metrics["rmse"])
    for pid, grp in df_res.groupby("product_id"):
        val = float(grp["err"].std(ddof=0)) if len(grp) > 1 else global_std
        sku_residual_std[str(pid)] = round(max(val, global_std * 0.5, 0.25), 4)

    models_dir = os.path.join(DATA_DIR, "models")
    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, f"{unique_id}_bundle.pkl")

    bundle = {
        "pipeline": final_pipeline,
        "feature_cols": feature_cols,
        "numeric_cols": numeric_cols,
        "cat_cols": cat_cols,
        "model_key": best_key,
        "model_name": best_name,
        "metrics": best_metrics,
        "candidates": candidates_results,
        "feature_importance": feature_importance,
        "sku_residual_std": sku_residual_std,
        "global_residual_std": round(max(global_std, 0.25), 4),
        "data_profile": profile,
        "strategy_explanation": plan.strategy_explanation,
    }
    joblib.dump(bundle, model_path)

    mlflow_run_id = _log_to_mlflow(
        unique_id=unique_id,
        best_name=best_name,
        best_metrics=best_metrics,
        feature_importance=feature_importance,
        model_path=model_path,
        profile=profile,
    )

    return {
        "model_path": model_path,
        "model_name": best_name,
        "metrics": best_metrics,
        "candidates": candidates_results,
        "feature_importance": feature_importance,
        "mlflow_run_id": mlflow_run_id,
        "strategy_explanation": plan.strategy_explanation,
    }


def _log_to_mlflow(
    unique_id: str,
    best_name: str,
    best_metrics: dict,
    feature_importance: dict,
    model_path: str,
    profile: dict,
) -> str | None:
    if not MLFLOW_TRACKING_URI:
        return None
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("dynamic-pricing")
        with mlflow.start_run(run_name=f"pricing-model-{unique_id}") as run:
            mlflow.log_params({
                "model_name": best_name,
                "daily_rows": profile.get("daily_rows"),
                "sku_count": profile.get("sku_count"),
                "regime": profile.get("recommended_regime"),
            })
            mlflow.log_metrics(best_metrics)
            if feature_importance:
                mlflow.log_dict(feature_importance, "feature_importance.json")
            mlflow.log_artifact(model_path, artifact_path="model")
            return run.info.run_id
    except Exception as e:
        logger.warning(f"MLflow logging skipped (non-fatal): {e}")
        return None
