from __future__ import annotations

import json
from langchain_core.messages import HumanMessage

from core.config import (
    ANTHROPIC_API_KEY,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    LLM_PROVIDER,
    OPENAI_API_KEY,
)
from core.logger import get_logger
from models.schemas import TrainingPlan

logger = get_logger(__name__)


def _has_configured_llm_key() -> bool:
    key_map = {
        "groq": GROQ_API_KEY,
        "gemini": GOOGLE_API_KEY,
        "openai": OPENAI_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
    }
    return bool(key_map.get(LLM_PROVIDER))


def default_training_plan(profile: dict) -> TrainingPlan:
    """Deterministic fallback plan tailored to the profiled data regime."""
    regime = profile.get("recommended_regime", "medium_tree")
    daily_rows = profile.get("daily_rows", 0)
    enable_lags = daily_rows >= 25

    if regime == "small_parametric":
        models = ["ridge_elasticity", "hist_gb_monotonic", "random_forest"]
        explanation = (
            f"Dataset has {daily_rows} daily SKU observations across {profile.get('sku_count', 1)} product(s). "
            "Prioritizing regularized log-price elasticity (Ridge) alongside monotonic gradient boosting and Random Forest."
        )
    elif regime == "count_poisson":
        models = ["hist_gb_poisson", "hist_gb_monotonic", "ridge_elasticity", "extra_trees"]
        explanation = (
            f"Daily demand is low-count/skewed (mean {profile.get('avg_daily_units', 0)} units/day). "
            "Prioritizing Poisson-loss monotonic gradient boosting alongside Ridge elasticity and Extra Trees."
        )
    else:
        models = ["hist_gb_monotonic", "hist_gb_poisson", "random_forest", "extra_trees", "ridge_elasticity"]
        explanation = (
            f"Dataset has {daily_rows} daily SKU observations with rich history ({profile.get('history_days', 0)} days). "
            "Benchmarking monotonic gradient boosting, Poisson boosting, tree ensembles, and log-price Ridge."
        )

    return TrainingPlan(
        candidate_models=models,
        use_log_price=True,
        enable_lags=enable_lags,
        outlier_clip_quantile=0.99 if daily_rows >= 40 else 1.0,
        strategy_explanation=explanation,
    )


def build_training_plan(profile: dict) -> TrainingPlan:
    """Use the LLM as a modeling strategist when configured, falling back deterministically."""
    fallback = default_training_plan(profile)
    if not _has_configured_llm_key():
        logger.info("No LLM provider key configured; using deterministic TrainingPlan")
        return fallback

    try:
        from agents.llm import get_llm

        llm = get_llm().with_structured_output(TrainingPlan)
        prompt = f"""
You are a senior pricing data scientist choosing a modeling strategy from a deterministic EDA profile.
Do NOT invent code; return a structured TrainingPlan selecting from the supported models:
- "hist_gb_monotonic": HistGradientBoostingRegressor with monotonic non-increasing price constraint
- "hist_gb_poisson": HistGradientBoostingRegressor(loss="poisson") with monotonic price constraint
- "ridge_elasticity": Log-target Ridge regression capturing smooth price elasticity on small/linear datasets
- "random_forest": RandomForestRegressor
- "extra_trees": ExtraTreesRegressor

Data profile:
{json.dumps(profile, indent=2)}

Guidelines:
- Always include at least 2 diverse candidate models, including one monotonic or parametric elasticity model.
- Set enable_lags=False if daily_rows < 25.
- Write a concise 1-2 sentence strategy_explanation for a business owner.
"""
        plan = llm.invoke([HumanMessage(content=prompt)])
        if plan and plan.candidate_models:
            return plan
    except Exception as e:
        logger.warning(f"LLM strategist failed, using deterministic TrainingPlan: {e}")

    return fallback
