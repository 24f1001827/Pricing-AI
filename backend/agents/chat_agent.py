from agents.llm import get_llm
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from core.logger import get_logger
import json

logger = get_logger(__name__)

llm = get_llm()

def create_chat_agent(
    predictions: dict,
    feature_importance: dict,
    model_metrics: dict,
    column_mapping: dict,
    price_demand_curve: list
):
    # Build context about this specific business
    context = f"""
    You are a pricing intelligence assistant for a business owner.
    You have access to their sales data analysis and pricing model results.
    
    THEIR MODEL RESULTS:
    - Optimal price: ${predictions.get('optimal_price')}
    - Predicted demand at optimal price: {predictions.get('predicted_demand')} units
    - Expected revenue at optimal price: ${predictions.get('expected_revenue')}
    
    MODEL PERFORMANCE:
    - R2 Score: {model_metrics.get('r2')} (how well the model fits the data, 1.0 is perfect)
    - RMSE: {model_metrics.get('rmse')} (average prediction error in units)
    - MAE: {model_metrics.get('mae')}
    
    WHAT DRIVES DEMAND (feature importance):
    {json.dumps(feature_importance, indent=2)}
    
    COLUMN MAPPING:
    - Price column: {column_mapping.get('pricing_column')}
    - Demand column: {column_mapping.get('demand_column')}
    - Date column: {column_mapping.get('date_column')}
    
    You can answer questions about their pricing, demand patterns, and business insights.
    When asked about a specific price scenario, use the price-demand curve data to calculate results.
    Be conversational, clear, and avoid technical jargon.
    Always relate answers back to their specific business context.
    """

    @tool
    def run_scenario(price: float) -> str:
        """Run a price scenario analysis. Given a price, returns predicted demand and revenue."""
        logger.info(f"Running scenario for price: {price}")
        
        # Find closest price point in curve
        closest = min(
            price_demand_curve,
            key=lambda x: abs(x["price"] - price)
        )
        
        # If price is outside curve range, extrapolate simply
        if price < price_demand_curve[0]["price"] or price > price_demand_curve[-1]["price"]:
            return f"Price ${price} is outside the observed range. Based on trend extrapolation: predicted demand ≈ {closest['predicted_demand']} units, revenue ≈ ${closest['revenue']}. Note: predictions outside observed price range are less reliable."
        
        return json.dumps({
            "price": price,
            "predicted_demand": closest["predicted_demand"],
            "expected_revenue": closest["revenue"],
            "vs_optimal": {
                "price_diff": round(price - predictions.get("optimal_price"), 2),
                "revenue_diff": round(closest["revenue"] - predictions.get("expected_revenue"), 2)
            }
        })

    @tool
    def get_feature_importance() -> str:
        """Returns which factors most influence demand for this business."""
        logger.info("Getting feature importance")
        if not feature_importance:
            return "Feature importance data is not available for this model."
        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )
        result = "Factors driving demand (most to least important):\n"
        for feature, importance in sorted_features:
            result += f"- {feature}: {round(importance * 100, 1)}% influence\n"
        return result

    @tool
    def get_price_curve_summary() -> str:
        """Returns a summary of how revenue changes across price points."""
        logger.info("Getting price curve summary")
        if not price_demand_curve:
            return "Price curve data is not available."
        
        min_price = price_demand_curve[0]["price"]
        max_price = price_demand_curve[-1]["price"]
        max_revenue_point = max(price_demand_curve, key=lambda x: x["revenue"])
        min_revenue_point = min(price_demand_curve, key=lambda x: x["revenue"])
        
        return json.dumps({
            "price_range": f"${min_price} to ${max_price}",
            "highest_revenue_price": max_revenue_point["price"],
            "highest_revenue": max_revenue_point["revenue"],
            "lowest_revenue_price": min_revenue_point["price"],
            "lowest_revenue": min_revenue_point["revenue"]
        })

    tools = [run_scenario, get_feature_importance, get_price_curve_summary]
    llm_with_tools = llm.bind_tools(tools)

    def chat(message: str, history: list) -> str:
        messages = [SystemMessage(content=context)]
        
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        
        messages.append(HumanMessage(content=message))
        
        # First LLM call — may decide to use tools
        response = llm_with_tools.invoke(messages)
        
        # If LLM called tools, execute them and feed results back
        if response.tool_calls:
            messages.append(response)
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                
                # Find and execute the right tool
                tool_result = None
                for t in tools:
                    if t.name == tool_name:
                        tool_result = t.invoke(tool_args)
                        break
                
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call["id"]
                ))
            
            # Second LLM call — generate final response with tool results
            final_response = llm.invoke(messages)
            return final_response.content
        
        return response.content

    return chat