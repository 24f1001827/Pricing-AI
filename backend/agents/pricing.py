import mlflow
import json
import os
from sqlalchemy.orm import Session
from core.config import MLFLOW_TRACKING_URI
from core.database_models import Prediction
from agents.sandbox import execute_code
from core.logger import get_logger

logger = get_logger(__name__)


def compute_predictions(
    unique_id: str,
    mlflow_run_id: str,
    file_path: str,
    column_mapping: dict,
    db: Session,
    local_model_path=None,
    user_id=None,
    optimization_objective: str = "revenue"
):
    logger.info(f"Computing predictions for job: {unique_id}, objective: {optimization_objective}")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    try:
        if local_model_path and os.path.exists(local_model_path):
            model_path = local_model_path
        else:
            model_path = mlflow.artifacts.download_artifacts(
                run_id=mlflow_run_id, artifact_path="model/model.pkl"
            )

        fe_code_path = mlflow.artifacts.download_artifacts(
            run_id=mlflow_run_id, artifact_path="code/feature_engineering.py"
        )
        with open(fe_code_path, "r") as f:
            feature_engineering_code = f.read()

    except Exception as e:
        logger.error(f"Failed to load artifacts: {str(e)}")
        return

    price_column = "price"
    demand_column = "units_sold"

    product_column = next(
        (col for col in column_mapping.get("other_columns", [])
         if any(t in col.lower() for t in ["product", "sku", "item"])),
        None
    )

    optimization_code = f"""
import pandas as pd
import numpy as np
import joblib
import json
from datetime import datetime, timedelta

model = joblib.load('/data/model.pkl')
df = pd.read_csv('/data/input.csv')

{feature_engineering_code}

if hasattr(model, 'feature_names_in_'):
    feature_cols = list(model.feature_names_in_)
else:
    excluded = ['{demand_column}', 'date']
    feature_cols = [c for c in df.select_dtypes(include='number').columns if c not in excluded]

product_column = {json.dumps(product_column)}
objective = "{optimization_objective}"

def get_objective_value(price, demand, cost_per_unit=None):
    if objective == "revenue":
        return price * demand
    elif objective == "profit" and cost_per_unit is not None:
        return (price - cost_per_unit) * demand
    elif objective == "units":
        return demand
    return price * demand

def build_curve(segment_df, product_value=None):
    min_price = float(segment_df['{price_column}'].min())
    max_price = float(segment_df['{price_column}'].max())
    if min_price == max_price:
        min_price = max_price * 0.7
    price_points = np.linspace(min_price, max_price, 100)
    scenarios = segment_df.sample(min(20, len(segment_df)), random_state=42).to_dict('records')
    avg_cost = float(segment_df['cost'].mean()) if 'cost' in segment_df.columns else None

    curve = []
    for price in price_points:
        demands = []
        for scenario in scenarios:
            row = {{col: scenario.get(col, 0) for col in feature_cols}}
            row['{price_column}'] = float(price)
            features_df = pd.DataFrame([row]).reindex(columns=feature_cols, fill_value=0)
            predicted = max(float(model.predict(features_df)[0]), 0.0)
            demands.append(predicted)
        avg_demand = float(np.mean(demands))
        obj_value = get_objective_value(price, avg_demand, avg_cost)
        revenue = float(price) * avg_demand
        profit = (float(price) - (avg_cost or 0)) * avg_demand
        point = {{
            "price": round(float(price), 2),
            "predicted_demand": round(avg_demand, 2),
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "objective_value": round(obj_value, 2)
        }}
        if product_value is not None:
            point["product"] = str(product_value)
        curve.append(point)
    return curve

def forecast_demand(segment_df, product_value=None):
    today_features = segment_df.sort_values('date').iloc[-1].to_dict() if 'date' in segment_df.columns else segment_df.iloc[-1].to_dict()
    optimal_price = float(segment_df['{price_column}'].median())

    forecasts = {{}}
    for days, key in [(1, 'day1'), (7, 'day7'), (30, 'day30')]:
        daily_preds = []
        for d in range(days):
            row = {{col: today_features.get(col, 0) for col in feature_cols}}
            row['{price_column}'] = optimal_price
            if 'day_of_week' in row:
                row['day_of_week'] = (d % 7)
            if 'is_weekend' in row:
                row['is_weekend'] = 1 if (d % 7) in [5, 6] else 0
            features_df = pd.DataFrame([row]).reindex(columns=feature_cols, fill_value=0)
            pred = max(float(model.predict(features_df)[0]), 0.0)
            daily_preds.append(pred)
        forecasts[key] = round(float(np.sum(daily_preds)), 2)
    return forecasts

# Per-product analysis
product_results = []
demand_forecast = {{}}

if product_column and product_column in df.columns and df[product_column].nunique() <= 50:
    for product_value, segment_df in df.groupby(product_column):
        if len(segment_df) >= 5:
            curve = build_curve(segment_df, product_value)
            optimal = max(curve, key=lambda x: x['objective_value'])
            forecast = forecast_demand(segment_df, product_value)
            demand_forecast[str(product_value)] = forecast
            product_results.append({{
                "product": str(product_value),
                "optimal_price": optimal["price"],
                "predicted_demand": optimal["predicted_demand"],
                "expected_revenue": optimal["revenue"],
                "expected_profit": optimal["profit"],
                "curve": curve,
                "forecast": forecast
            }})

# Overall curve
if product_results:
    all_prices = sorted(set(p["price"] for item in product_results for p in item["curve"]))
    overall_curve = []
    for price in all_prices:
        total_demand = sum(
            min(item["curve"], key=lambda p: abs(p["price"] - price))["predicted_demand"]
            for item in product_results
        )
        total_revenue = price * total_demand
        overall_curve.append({{"price": round(price, 2), "predicted_demand": round(total_demand, 2), "revenue": round(total_revenue, 2)}})
    total_forecast = {{
        "day1": round(sum(v.get("day1", 0) for v in demand_forecast.values()), 2),
        "day7": round(sum(v.get("day7", 0) for v in demand_forecast.values()), 2),
        "day30": round(sum(v.get("day30", 0) for v in demand_forecast.values()), 2),
    }}
    demand_forecast["total"] = total_forecast
else:
    overall_curve = build_curve(df)
    demand_forecast["total"] = forecast_demand(df)

overall_optimal = max(overall_curve, key=lambda x: x.get('revenue', 0))

result = {{
    "optimal_price": overall_optimal["price"],
    "predicted_demand": overall_optimal["predicted_demand"],
    "expected_revenue": overall_optimal["revenue"],
    "curve": overall_curve,
    "product_results": product_results,
    "demand_forecast": demand_forecast,
    "optimization_objective": objective
}}

print("PREDICTIONS:" + json.dumps(result))
"""

    result = execute_code(
        optimization_code,
        files={"/data/model.pkl": model_path, "/data/input.csv": file_path}
    )

    predictions = None
    if result["stdout"]:
        for line in result["stdout"]:
            if "PREDICTIONS:" in line:
                try:
                    predictions_str = line.split("PREDICTIONS:")[1].strip()
                    predictions = json.loads(predictions_str)
                    logger.info(f"Predictions computed. Optimal: ${predictions['optimal_price']}")
                except Exception as e:
                    logger.error(f"Parse error: {str(e)}")

    if result.get("error"):
        logger.error(f"Optimization error: {result['error']}")

    if not predictions:
        logger.error("No predictions produced")
        return

    prediction_record = Prediction(
        training_job_id=unique_id,
        user_id=user_id,
        optimal_price=predictions["optimal_price"],
        predicted_demand=predictions["predicted_demand"],
        expected_revenue=predictions["expected_revenue"],
        price_demand_curve=predictions["curve"],
        product_results=predictions.get("product_results", []),
        demand_forecast=predictions.get("demand_forecast", {}),
        optimization_objective=optimization_objective
    )
    db.add(prediction_record)
    db.commit()
    logger.info(f"Predictions stored for job: {unique_id}")