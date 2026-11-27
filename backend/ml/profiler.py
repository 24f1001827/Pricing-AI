from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd


FORBIDDEN_LEAKAGE_COLUMNS = {"revenue", "profit", "total_revenue", "total_profit", "total_cost", "customer_email"}


def aggregate_daily_sku_demand(
    raw_df: pd.DataFrame,
    calendar_df: Optional[pd.DataFrame] = None,
    enable_lags: bool = True,
) -> pd.DataFrame:
    """Aggregate line-item order records to daily per-SKU demand without target leakage."""
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "product_id", "units_sold", "price"])
    df = df[df["price"] > 0]
    if df.empty:
        return pd.DataFrame()

    df["_line_rev"] = df["units_sold"].astype(float) * df["price"].astype(float)
    df["_line_cost"] = df["units_sold"].astype(float) * df.get("cost", pd.Series(0.0, index=df.index)).fillna(0.0).astype(float)
    df["is_promotion"] = df.get("is_promotion", 0).fillna(0).astype(int)
    if "channel" not in df.columns:
        df["channel"] = "unknown"
    df["channel"] = df["channel"].fillna("unknown").astype(str)
    if "inventory_level" not in df.columns:
        df["inventory_level"] = np.nan

    def _mode_or_first(series: pd.Series) -> str:
        modes = series.mode()
        return str(modes.iloc[0]) if not modes.empty else "unknown"

    grouped = (
        df.groupby(["date", "product_id"], as_index=False)
        .agg(
            units_sold=("units_sold", "sum"),
            _total_rev=("_line_rev", "sum"),
            _total_cost=("_line_cost", "sum"),
            is_promotion=("is_promotion", "max"),
            channel=("channel", _mode_or_first),
            inventory_level=("inventory_level", "last"),
            order_count=("units_sold", "count"),
        )
    )

    grouped["price"] = (grouped["_total_rev"] / grouped["units_sold"].clip(lower=1e-6)).round(4)
    grouped["cost"] = (grouped["_total_cost"] / grouped["units_sold"].clip(lower=1e-6)).round(4)
    grouped = grouped.drop(columns=["_total_rev", "_total_cost"])

    # Join business calendar if provided
    grouped["is_holiday"] = 0
    grouped["is_festival"] = 0
    grouped["is_closed"] = 0
    if calendar_df is not None and not calendar_df.empty:
        cal = calendar_df.copy()
        cal["date"] = pd.to_datetime(cal["date"], errors="coerce")
        cal = cal.dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")
        grouped = grouped.merge(
            cal[["date", "is_closed", "is_holiday", "is_festival"]],
            on="date",
            how="left",
            suffixes=("_drop", ""),
        )
        for col in ["is_closed", "is_holiday", "is_festival"]:
            drop_col = f"{col}_drop"
            if drop_col in grouped.columns:
                grouped = grouped.drop(columns=[drop_col])
            grouped[col] = grouped[col].fillna(0).astype(int)
        grouped = grouped[grouped["is_closed"] == 0].copy()

    if grouped.empty:
        return grouped

    grouped = grouped.sort_values(["product_id", "date"]).reset_index(drop=True)

    # Calendar & price transform features
    grouped["log_price"] = np.log(grouped["price"].clip(lower=0.01))
    grouped["day_of_week"] = grouped["date"].dt.dayofweek.astype(int)
    grouped["is_weekend"] = grouped["day_of_week"].isin([5, 6]).astype(int)
    grouped["month"] = grouped["date"].dt.month.astype(int)
    grouped["quarter"] = grouped["date"].dt.quarter.astype(int)
    grouped["day"] = grouped["date"].dt.day.astype(int)
    grouped["week_of_year"] = grouped["date"].dt.isocalendar().week.astype(int)

    # Causal lag/rolling features per SKU (shifted by 1 so current day target never leaks)
    if enable_lags:
        grouped["lag_1_units"] = grouped.groupby("product_id")["units_sold"].shift(1)
        grouped["rolling_7_units"] = (
            grouped.groupby("product_id")["units_sold"]
            .transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
        )
        grouped["rolling_7_price"] = (
            grouped.groupby("product_id")["price"]
            .transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
        )
        sku_means = grouped.groupby("product_id")["units_sold"].transform("mean")
        sku_price_means = grouped.groupby("product_id")["price"].transform("mean")
        grouped["lag_1_units"] = grouped["lag_1_units"].fillna(sku_means)
        grouped["rolling_7_units"] = grouped["rolling_7_units"].fillna(sku_means)
        grouped["rolling_7_price"] = grouped["rolling_7_price"].fillna(sku_price_means)
        grouped["price_ratio_to_avg"] = (grouped["price"] / sku_price_means.clip(lower=0.01)).round(4)

    grouped["date"] = grouped["date"].dt.strftime("%Y-%m-%d")
    return grouped


def profile_dataset(daily_df: pd.DataFrame) -> dict:
    """Produce a deterministic EDA summary used for model selection and UI insights."""
    if daily_df.empty:
        return {
            "daily_rows": 0,
            "sku_count": 0,
            "history_days": 0,
            "recommended_regime": "small_parametric",
            "warnings": ["No valid daily demand records found."],
        }

    dates = pd.to_datetime(daily_df["date"])
    history_days = int((dates.max() - dates.min()).days) + 1
    sku_count = int(daily_df["product_id"].nunique())
    daily_rows = int(len(daily_df))

    # Price variability per SKU
    price_stds = daily_df.groupby("product_id")["price"].std().fillna(0)
    price_means = daily_df.groupby("product_id")["price"].mean().clip(lower=0.01)
    avg_price_cv = float((price_stds / price_means).mean())

    promo_share = float(daily_df["is_promotion"].mean()) if "is_promotion" in daily_df else 0.0
    low_count_share = float((daily_df["units_sold"] <= 3).mean())
    avg_daily_units = float(daily_df["units_sold"].mean())
    max_daily_units = float(daily_df["units_sold"].max())

    weekend_mask = daily_df["is_weekend"] == 1
    weekday_mean = float(daily_df.loc[~weekend_mask, "units_sold"].mean()) if (~weekend_mask).any() else avg_daily_units
    weekend_mean = float(daily_df.loc[weekend_mask, "units_sold"].mean()) if weekend_mask.any() else avg_daily_units
    weekend_lift = round((weekend_mean - weekday_mean) / max(weekday_mean, 1e-3), 3)

    warnings = []
    if daily_rows < 30:
        warnings.append("Limited daily history (< 30 SKU-day observations); parametric elasticity models preferred.")
    if avg_price_cv < 0.02:
        warnings.append("Historical prices barely changed across dates; price elasticity estimates have higher uncertainty.")

    if daily_rows < 80:
        regime = "small_parametric"
    elif low_count_share > 0.45 or avg_daily_units < 10:
        regime = "count_poisson"
    else:
        regime = "medium_tree"

    return {
        "daily_rows": daily_rows,
        "sku_count": sku_count,
        "date_start": dates.min().strftime("%Y-%m-%d"),
        "date_end": dates.max().strftime("%Y-%m-%d"),
        "history_days": history_days,
        "avg_price_cv": round(avg_price_cv, 4),
        "promo_share": round(promo_share, 4),
        "low_count_share": round(low_count_share, 4),
        "avg_daily_units": round(avg_daily_units, 2),
        "max_daily_units": round(max_daily_units, 2),
        "weekend_lift": weekend_lift,
        "recommended_regime": regime,
        "warnings": warnings,
    }
