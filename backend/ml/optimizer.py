from __future__ import annotations

import math
from datetime import datetime, timedelta
from statistics import NormalDist
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from core.database_models import BusinessCalendar, Prediction, Product
from core.logger import get_logger

logger = get_logger(__name__)


def _objective_value(price: float, demand: float, cost: float, objective: str) -> float:
    if objective == "profit":
        return (price - cost) * demand
    if objective == "units":
        return demand
    return price * demand


def _build_product_curve(
    pipeline,
    feature_cols: list[str],
    segment_df: pd.DataFrame,
    product_meta: Optional[Product],
    objective: str,
    n_points: int = 60,
) -> list[dict]:
    hist_min = float(segment_df["price"].min())
    hist_max = float(segment_df["price"].max())
    avg_cost = float(product_meta.cost) if (product_meta and product_meta.cost is not None) else float(segment_df["cost"].mean())

    p_low = hist_min * 0.8 if hist_min != hist_max else hist_min * 0.7
    p_high = hist_max * 1.2 if hist_min != hist_max else hist_max * 1.3

    if product_meta and product_meta.min_price is not None:
        p_low = max(p_low, float(product_meta.min_price))
    if product_meta and product_meta.max_price is not None:
        p_high = min(p_high, float(product_meta.max_price))
    if avg_cost > 0 and objective == "profit":
        p_low = max(p_low, avg_cost * 1.02)

    if p_high <= p_low:
        p_low = max(0.01, hist_min * 0.85)
        p_high = max(p_low * 1.3, hist_max * 1.15)

    price_points = np.linspace(p_low, p_high, n_points)
    scenarios = segment_df.tail(min(20, len(segment_df)))
    sku_avg_price = float(segment_df["price"].mean())

    # Vectorized grid: (n_points * len(scenarios)) rows scored in one pipeline call
    rows = []
    for price in price_points:
        for _, scen in scenarios.iterrows():
            row = {col: scen.get(col, np.nan) for col in feature_cols}
            if "price" in row:
                row["price"] = float(price)
            if "log_price" in row:
                row["log_price"] = float(math.log(max(price, 0.01)))
            if "price_ratio_to_avg" in row:
                row["price_ratio_to_avg"] = float(price / max(sku_avg_price, 0.01))
            rows.append(row)

    grid_df = pd.DataFrame(rows, columns=feature_cols)
    preds = np.maximum(pipeline.predict(grid_df), 0.0).reshape(len(price_points), len(scenarios))
    avg_demands = preds.mean(axis=1)

    curve = []
    for idx, price in enumerate(price_points):
        demand = float(avg_demands[idx])
        revenue = float(price) * demand
        profit = (float(price) - avg_cost) * demand
        obj_val = _objective_value(float(price), demand, avg_cost, objective)
        curve.append({
            "price": round(float(price), 2),
            "predicted_demand": round(demand, 2),
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "objective_value": round(obj_val, 2),
        })
    return curve


def _forecast_product_horizon(
    pipeline,
    feature_cols: list[str],
    segment_df: pd.DataFrame,
    optimal_price: float,
    calendar_map: Dict[str, dict],
    days: int = 30,
) -> dict:
    latest_row = segment_df.sort_values("date").iloc[-1]
    sku_avg_price = float(segment_df["price"].mean())
    base_lag = float(latest_row.get("units_sold", segment_df["units_sold"].mean()))
    rolling_7 = float(segment_df["units_sold"].tail(7).mean())

    start_date = datetime.utcnow().date() + timedelta(days=1)
    daily_preds: List[float] = []

    for d in range(days):
        target_date = start_date + timedelta(days=d)
        date_str = target_date.strftime("%Y-%m-%d")
        cal = calendar_map.get(date_str, {})
        if cal.get("is_closed"):
            daily_preds.append(0.0)
            continue

        row = {col: latest_row.get(col, np.nan) for col in feature_cols}
        if "price" in row:
            row["price"] = float(optimal_price)
        if "log_price" in row:
            row["log_price"] = float(math.log(max(optimal_price, 0.01)))
        if "price_ratio_to_avg" in row:
            row["price_ratio_to_avg"] = float(optimal_price / max(sku_avg_price, 0.01))
        if "day_of_week" in row:
            row["day_of_week"] = int(target_date.weekday())
        if "is_weekend" in row:
            row["is_weekend"] = 1 if target_date.weekday() in (5, 6) else 0
        if "month" in row:
            row["month"] = int(target_date.month)
        if "quarter" in row:
            row["quarter"] = int(((target_date.month - 1) // 3) + 1)
        if "day" in row:
            row["day"] = int(target_date.day)
        if "week_of_year" in row:
            row["week_of_year"] = int(target_date.isocalendar()[1])
        if "is_holiday" in row:
            row["is_holiday"] = 1 if cal.get("is_holiday") else 0
        if "is_festival" in row:
            row["is_festival"] = 1 if cal.get("is_festival") else 0
        if "lag_1_units" in row:
            row["lag_1_units"] = base_lag if d == 0 else daily_preds[-1]
        if "rolling_7_units" in row:
            recent = ([rolling_7] * max(0, 7 - len(daily_preds))) + daily_preds[-7:]
            row["rolling_7_units"] = float(np.mean(recent))

        pred = max(float(pipeline.predict(pd.DataFrame([row], columns=feature_cols))[0]), 0.0)
        daily_preds.append(pred)

    return {
        "day1": round(float(daily_preds[0]), 2) if daily_preds else 0.0,
        "day7": round(float(sum(daily_preds[:7])), 2),
        "day30": round(float(sum(daily_preds[:30])), 2),
    }


def _compute_inventory_metrics(
    product_id: str,
    product_meta: Optional[Product],
    segment_df: pd.DataFrame,
    forecast: dict,
    curve: list[dict],
    base_optimal: dict,
    demand_std: float,
) -> dict:
    avg_daily = max(float(forecast.get("day7", 0.0)) / 7.0, float(forecast.get("day1", 0.0)), 0.01)

    if product_meta and product_meta.stock_on_hand is not None:
        stock_on_hand = int(product_meta.stock_on_hand)
    elif segment_df["inventory_level"].dropna().any():
        stock_on_hand = int(segment_df["inventory_level"].dropna().iloc[-1])
    else:
        stock_on_hand = 0

    lead_time = int(product_meta.lead_time_days) if (product_meta and product_meta.lead_time_days) else 7
    service_level = float(product_meta.service_level) if (product_meta and product_meta.service_level) else 0.95
    service_level = min(max(service_level, 0.5), 0.999)
    unit_cost = float(product_meta.cost) if (product_meta and product_meta.cost is not None) else float(segment_df["cost"].mean() or 1.0)
    holding_cost = (
        float(product_meta.holding_cost_per_unit)
        if (product_meta and product_meta.holding_cost_per_unit is not None and product_meta.holding_cost_per_unit > 0)
        else max(unit_cost * 0.25, 0.5)
    )
    reorder_cost = (
        float(product_meta.reorder_cost)
        if (product_meta and product_meta.reorder_cost is not None and product_meta.reorder_cost > 0)
        else 50.0
    )

    z = NormalDist().inv_cdf(service_level)
    hist_std = float(segment_df["units_sold"].std(ddof=0)) if len(segment_df) > 1 else 0.0
    sigma = max(demand_std, hist_std * 0.5, 0.25)

    safety_stock = int(math.ceil(z * sigma * math.sqrt(lead_time)))
    reorder_point = int(math.ceil(avg_daily * lead_time + safety_stock))
    days_of_cover = round(stock_on_hand / max(avg_daily, 0.05), 1)
    annual_demand = avg_daily * 365.0
    eoq = int(math.ceil(math.sqrt((2.0 * annual_demand * reorder_cost) / max(holding_cost, 0.01))))
    recommended_order_qty = (
        max(eoq, reorder_point - stock_on_hand + int(math.ceil(avg_daily * lead_time)))
        if stock_on_hand <= reorder_point
        else 0
    )

    if stock_on_hand <= 0 or days_of_cover < lead_time:
        status = "stockout_risk"
    elif stock_on_hand <= reorder_point:
        status = "reorder_now"
    elif days_of_cover > max(60.0, lead_time * 6.0):
        status = "overstock"
    else:
        status = "healthy"

    # Inventory-aware price adjustment
    adjusted_price = base_optimal["price"]
    price_action_note = "Standard optimal price aligns with current stock."
    if status in ("stockout_risk", "reorder_now") and stock_on_hand > 0:
        max_daily_sustainable = stock_on_hand / max(lead_time, 1)
        feasible = [pt for pt in curve if pt["predicted_demand"] <= max_daily_sustainable]
        if feasible:
            best_feasible = max(feasible, key=lambda pt: pt["objective_value"])
            if best_feasible["price"] > base_optimal["price"]:
                adjusted_price = best_feasible["price"]
                price_action_note = (
                    f"Raise price to ${adjusted_price} to slow demand until replenishment arrives ({lead_time}d lead time)."
                )
    elif status == "overstock":
        # Prefer slightly higher-volume point within 90% of peak objective to accelerate sell-through
        peak_obj = max(pt["objective_value"] for pt in curve) if curve else 0.0
        markdown_candidates = [
            pt for pt in curve
            if pt["price"] <= base_optimal["price"] and pt["objective_value"] >= peak_obj * 0.90
        ]
        if markdown_candidates:
            best_markdown = max(markdown_candidates, key=lambda pt: pt["predicted_demand"])
            if best_markdown["price"] < base_optimal["price"]:
                adjusted_price = best_markdown["price"]
                price_action_note = (
                    f"Overstock detected ({days_of_cover}d cover). Markdown to ${adjusted_price} clears excess stock while preserving >=90% objective."
                )

    return {
        "product_id": str(product_id),
        "product_name": product_meta.product_name if product_meta else str(product_id),
        "stock_on_hand": stock_on_hand,
        "lead_time_days": lead_time,
        "service_level": service_level,
        "avg_daily_demand": round(avg_daily, 2),
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "days_of_cover": days_of_cover,
        "eoq": eoq,
        "recommended_order_qty": recommended_order_qty,
        "stock_status": status,
        "base_optimal_price": base_optimal["price"],
        "inventory_adjusted_price": adjusted_price,
        "price_action_note": price_action_note,
    }


def compute_and_store_predictions(
    unique_id: str,
    daily_df: pd.DataFrame,
    training_result: dict,
    db: Session,
    user_id: int,
    optimization_objective: str = "revenue",
) -> Prediction:
    """Run vectorized price optimization, multi-day forecasting, and inventory analysis."""
    bundle = joblib.load(training_result["model_path"])
    pipeline = bundle["pipeline"]
    feature_cols = bundle["feature_cols"]
    sku_residual_std = bundle.get("sku_residual_std", {})
    global_std = bundle.get("global_residual_std", 1.0)

    products_by_id = {
        p.product_id: p
        for p in db.query(Product).filter(Product.user_id == user_id).all()
    }
    calendar_rows = db.query(BusinessCalendar).filter(BusinessCalendar.user_id == user_id).all()
    calendar_map = {
        c.date: {"is_closed": c.is_closed, "is_holiday": c.is_holiday, "is_festival": c.is_festival}
        for c in calendar_rows
    }

    product_results = []
    inventory_recommendations = []
    demand_forecast: Dict[str, dict] = {}

    for product_id, segment_df in daily_df.groupby("product_id"):
        if len(segment_df) < 2:
            continue
        pid_str = str(product_id)
        product_meta = products_by_id.get(pid_str)
        curve = _build_product_curve(pipeline, feature_cols, segment_df, product_meta, optimization_objective)
        optimal = max(curve, key=lambda pt: pt["objective_value"])
        forecast = _forecast_product_horizon(pipeline, feature_cols, segment_df, optimal["price"], calendar_map, days=30)
        inv = _compute_inventory_metrics(
            product_id=pid_str,
            product_meta=product_meta,
            segment_df=segment_df,
            forecast=forecast,
            curve=curve,
            base_optimal=optimal,
            demand_std=float(sku_residual_std.get(pid_str, global_std)),
        )

        demand_forecast[pid_str] = forecast
        inventory_recommendations.append(inv)
        product_results.append({
            "product": pid_str,
            "product_name": product_meta.product_name if product_meta else pid_str,
            "optimal_price": optimal["price"],
            "inventory_adjusted_price": inv["inventory_adjusted_price"],
            "predicted_demand": optimal["predicted_demand"],
            "expected_revenue": optimal["revenue"],
            "expected_profit": optimal["profit"],
            "stock_status": inv["stock_status"],
            "curve": curve,
            "forecast": forecast,
        })

    if not product_results:
        raise ValueError("Not enough per-product daily data to generate pricing curves.")

    demand_forecast["total"] = {
        "day1": round(sum(v.get("day1", 0.0) for v in demand_forecast.values()), 2),
        "day7": round(sum(v.get("day7", 0.0) for v in demand_forecast.values()), 2),
        "day30": round(sum(v.get("day30", 0.0) for v in demand_forecast.values()), 2),
    }

    # Build a portfolio sensitivity curve using relative multipliers (-20% to +20% around each product's curve)
    # so multi-SKU portfolios with different price tiers aggregate meaningfully.
    if len(product_results) == 1:
        overall_curve = product_results[0]["curve"]
        overall_optimal = max(overall_curve, key=lambda pt: pt["objective_value"])
        headline_price = overall_optimal["price"]
        headline_demand = overall_optimal["predicted_demand"]
        headline_revenue = overall_optimal["revenue"]
    else:
        n_pts = len(product_results[0]["curve"])
        overall_curve = []
        for i in range(n_pts):
            # Average price weighted by predicted demand at index i across products
            dem_sum = sum(pr["curve"][i]["predicted_demand"] for pr in product_results if i < len(pr["curve"]))
            rev_sum = sum(pr["curve"][i]["revenue"] for pr in product_results if i < len(pr["curve"]))
            prof_sum = sum(pr["curve"][i]["profit"] for pr in product_results if i < len(pr["curve"]))
            obj_sum = sum(pr["curve"][i]["objective_value"] for pr in product_results if i < len(pr["curve"]))
            avg_p = rev_sum / dem_sum if dem_sum > 0 else float(np.mean([pr["curve"][i]["price"] for pr in product_results]))
            overall_curve.append({
                "price": round(float(avg_p), 2),
                "predicted_demand": round(float(dem_sum), 2),
                "revenue": round(float(rev_sum), 2),
                "profit": round(float(prof_sum), 2),
                "objective_value": round(float(obj_sum), 2),
            })
        headline_demand = round(sum(pr["predicted_demand"] for pr in product_results), 2)
        headline_revenue = round(sum(pr["expected_revenue"] for pr in product_results), 2)
        headline_price = round(headline_revenue / max(headline_demand, 1e-6), 2)

    model_summary = {
        "model_name": training_result["model_name"],
        "metrics": training_result["metrics"],
        "candidates": training_result.get("candidates", []),
        "feature_importance": training_result.get("feature_importance", {}),
        "data_profile": bundle.get("data_profile", {}),
        "strategy_explanation": training_result.get("strategy_explanation", ""),
    }

    record = Prediction(
        training_job_id=unique_id,
        user_id=user_id,
        optimal_price=headline_price,
        predicted_demand=headline_demand,
        expected_revenue=headline_revenue,
        price_demand_curve=overall_curve,
        product_results=product_results,
        demand_forecast=demand_forecast,
        inventory_recommendations=inventory_recommendations,
        model_summary=model_summary,
        optimization_objective=optimization_objective,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"Stored predictions & inventory recommendations for job {unique_id}")
    return record
