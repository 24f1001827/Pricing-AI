import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents.chat_agent import create_chat_agent
from core.database import get_db
from core.database_models import Prediction, TrainingJob, User
from core.dependencies import get_current_user
from core.logger import get_logger
from models.schemas import ChatRequest

router = APIRouter()
logger = get_logger(__name__)


def _prediction_payload(prediction: Prediction) -> dict:
    """Keep the list and job-specific prediction responses consistent."""
    return {
        "training_job_id": prediction.training_job_id,
        "optimal_price": prediction.optimal_price,
        "predicted_demand": prediction.predicted_demand,
        "expected_revenue": prediction.expected_revenue,
        "price_demand_curve": prediction.price_demand_curve,
        "product_results": prediction.product_results or [],
        "demand_forecast": prediction.demand_forecast or {},
        "inventory_recommendations": prediction.inventory_recommendations or [],
        "model_summary": prediction.model_summary or {},
        "optimization_objective": prediction.optimization_objective or "revenue",
        "created_at": prediction.created_at,
    }


@router.get("/latest")
def get_latest_predictions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prediction = (
        db.query(Prediction)
        .filter(Prediction.user_id == current_user.id)
        .order_by(Prediction.created_at.desc())
        .first()
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="No predictions found. Train a model first.")
    return _prediction_payload(prediction)


@router.get("/{training_job_id}")
def get_predictions(
    training_job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prediction = (
        db.query(Prediction)
        .filter(
            Prediction.training_job_id == training_job_id,
            Prediction.user_id == current_user.id,
        )
        .first()
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="Predictions not found")
    return _prediction_payload(prediction)


@router.post("/chat/{training_job_id}")
def chat(
    training_job_id: str,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prediction = (
        db.query(Prediction)
        .filter(
            Prediction.training_job_id == training_job_id,
            Prediction.user_id == current_user.id,
        )
        .first()
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="Predictions not found")

    model_summary = prediction.model_summary or {}
    feature_importance = model_summary.get("feature_importance", {})
    model_metrics = model_summary.get("metrics", {})

    if not model_metrics or not feature_importance:
        job = db.query(TrainingJob).filter(TrainingJob.unique_id == training_job_id).first()
        if job and job.metrics:
            model_metrics = job.metrics
        elif job and job.mlflow_run_id:
            try:
                import mlflow
                from core.config import MLFLOW_TRACKING_URI

                if MLFLOW_TRACKING_URI:
                    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
                    client = mlflow.tracking.MlflowClient()
                    local_path = client.download_artifacts(job.mlflow_run_id, "feature_importance.json")
                    with open(local_path) as f:
                        feature_importance = json.load(f)
                    model_metrics = client.get_run(job.mlflow_run_id).data.metrics
            except Exception as e:
                logger.warning(f"Failed to load MLflow metadata for chat: {e}")

    chat_fn = create_chat_agent(
        predictions={
            "optimal_price": prediction.optimal_price,
            "predicted_demand": prediction.predicted_demand,
            "expected_revenue": prediction.expected_revenue,
            "optimization_objective": prediction.optimization_objective,
            "product_results": prediction.product_results or [],
            "inventory_recommendations": prediction.inventory_recommendations or [],
            "strategy_explanation": model_summary.get("strategy_explanation", ""),
            "model_name": model_summary.get("model_name", ""),
        },
        feature_importance=feature_importance,
        model_metrics=model_metrics,
        column_mapping={
            "pricing_column": "price",
            "demand_column": "units_sold",
            "date_column": "date",
        },
        price_demand_curve=prediction.price_demand_curve or [],
    )

    history = [msg.model_dump() for msg in request.history]
    response = chat_fn(request.message, history)
    return {"response": response}
