import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from core.logger import get_logger
from ml.strategist import _has_configured_llm_key

logger = get_logger(__name__)


def create_chat_agent(
    predictions: dict,
    feature_importance: dict,
    model_metrics: dict,
    column_mapping: dict,
    price_demand_curve: list,
):
    product_results = predictions.get("product_results") or []
    inventory_recs = predictions.get("inventory_recommendations") or []

    compact_products = [
        {
            "product": p.get("product"),
            "optimal_price": p.get("optimal_price"),
            "inventory_adjusted_price": p.get("inventory_adjusted_price"),
            "predicted_demand": p.get("predicted_demand"),
            "expected_revenue": p.get("expected_revenue"),
            "stock_status": p.get("stock_status"),
        }
        for p in product_results[:20]
    ]

    context = f"""
You are a pricing and inventory intelligence assistant for a business owner.
You have access to their trained model results, per-product price recommendations, and inventory alerts.

PORTFOLIO SUMMARY:
- Optimization objective: {predictions.get('optimization_objective', 'revenue')}
- Winning model: {predictions.get('model_name') or 'AutoML ensemble'}
- Strategy: {predictions.get('strategy_explanation') or 'Chronological cross-validated demand forecasting'}
- Headline optimal/avg price: ${predictions.get('optimal_price')}
- Predicted daily demand: {predictions.get('predicted_demand')} units
- Expected daily revenue: ${predictions.get('expected_revenue')}

MODEL PERFORMANCE:
- R2 Score: {model_metrics.get('r2')}
- RMSE: {model_metrics.get('rmse')}
- MAE: {model_metrics.get('mae')}

PER-PRODUCT RECOMMENDATIONS:
{json.dumps(compact_products, indent=2)}

INVENTORY STATUS:
{json.dumps(inventory_recs[:20], indent=2)}

WHAT DRIVES DEMAND (feature importance):
{json.dumps(feature_importance, indent=2)}

Be conversational, concise, and practical. Relate answers directly to their specific products, prices, and stock levels.
"""

    @tool
    def run_scenario(price: float, product_id: str = "") -> str:
        """Run a price scenario analysis. Optionally specify product_id for SKU-level simulation."""
        logger.info(f"Running scenario for price={price}, product_id={product_id}")
        curve = price_demand_curve
        target_opt = predictions.get("optimal_price")
        target_rev = predictions.get("expected_revenue")

        if product_id:
            match = next((p for p in product_results if p.get("product") == product_id), None)
            if match and match.get("curve"):
                curve = match["curve"]
                target_opt = match.get("optimal_price")
                target_rev = match.get("expected_revenue")

        if not curve:
            return "Price curve data is unavailable."

        closest = min(curve, key=lambda x: abs(x["price"] - price))
        outside = price < curve[0]["price"] or price > curve[-1]["price"]
        return json.dumps({
            "product_id": product_id or "portfolio",
            "requested_price": price,
            "closest_modeled_price": closest["price"],
            "predicted_demand": closest["predicted_demand"],
            "expected_revenue": closest["revenue"],
            "outside_observed_range": outside,
            "vs_optimal": {
                "price_diff": round(price - (target_opt or 0), 2),
                "revenue_diff": round(closest["revenue"] - (target_rev or 0), 2),
            },
        })

    @tool
    def get_feature_importance() -> str:
        """Return which factors most influence demand for this business."""
        if not feature_importance:
            return "Feature importance data is not available for this model."
        sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
        lines = [f"- {feat}: {round(imp * 100, 1)}% influence" for feat, imp in sorted_features[:10]]
        return "Top demand drivers:\n" + "\n".join(lines)

    @tool
    def get_inventory_alerts() -> str:
        """Return products at risk of stockout, needing reorder, or overstocked."""
        if not inventory_recs:
            return "No inventory data available."
        return json.dumps(inventory_recs[:20])

    tools = [run_scenario, get_feature_importance, get_inventory_alerts]

    def chat(message: str, history: list) -> str:
        if not _has_configured_llm_key():
            top_driver = next(iter(feature_importance), "price") if feature_importance else "price"
            at_risk = [r["product_id"] for r in inventory_recs if r.get("stock_status") in ("stockout_risk", "reorder_now")]
            risk_note = f" Products needing attention/reorder: {', '.join(at_risk)}." if at_risk else ""
            return (
                f"LLM chat key is not configured, so here is a direct model summary: "
                f"Using {predictions.get('model_name') or 'AutoML'}, headline expected daily revenue is "
                f"${predictions.get('expected_revenue')} across {predictions.get('predicted_demand')} predicted units, "
                f"with '{top_driver}' as the top demand driver.{risk_note}"
            )

        from agents.llm import get_llm

        llm = get_llm()
        llm_with_tools = llm.bind_tools(tools)

        messages = [SystemMessage(content=context)]
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=message))

        response = llm_with_tools.invoke(messages)
        if getattr(response, "tool_calls", None):
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_result = None
                for t in tools:
                    if t.name == tool_name:
                        tool_result = t.invoke(tool_args)
                        break
                messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
                )
            final_response = llm.invoke(messages)
            return final_response.content

        return response.content

    return chat
