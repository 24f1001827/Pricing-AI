from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from core.database import get_db, SessionLocal
from core.database_models import Order, OrderLineItem, TrainingJob, User, Prediction, DailyEvaluation, BusinessCalendar, Product
from core.dependencies import get_current_user
from core.logger import get_logger
from core.config import MIN_RECORDS_TO_TRAIN, RETRAIN_NEW_DATA_THRESHOLD, RETRAIN_ERROR_THRESHOLD, RETRAIN_DRIFT_THRESHOLD
from monitoring.drift import check_drift
from agents.graph import pipeline
from agents.pricing import compute_predictions
import uuid
import pandas as pd
import os
from datetime import datetime, timedelta

router = APIRouter()
logger = get_logger(__name__)


def build_training_dataframe(user_id: int, db: Session) -> pd.DataFrame:
    orders = db.query(Order).filter(Order.user_id == user_id).all()
    items = db.query(OrderLineItem).filter(OrderLineItem.user_id == user_id).all()

    # Build order lookup
    order_map = {o.order_id: o for o in orders}

    # Build product cost lookup
    products = db.query(Product).filter(Product.user_id == user_id).all()
    product_cost_map = {p.product_id: p.cost or 0 for p in products}

    rows = []
    for item in items:
        order = order_map.get(item.order_id)
        if not order:
            continue
        dt = order.order_time
        rows.append({
            "date": order.date,
            "hour": dt.hour if dt else 0,
            "product_id": item.product_id,
            "units_sold": item.quantity,
            "price": item.unit_price,
            "cost": item.unit_cost or product_cost_map.get(item.product_id, 0),
            "revenue": item.quantity * item.unit_price,
            "profit": item.quantity * (item.unit_price - (item.unit_cost or product_cost_map.get(item.product_id, 0))),
            "is_promotion": 1 if order.is_promotion else 0,
            "inventory_level": item.inventory_level,
            "channel": order.channel or "unknown",
            "customer_email": order.customer_email or "guest"
        })

    return pd.DataFrame(rows)


def export_training_csv(user_id: int, unique_id: str, db: Session):
    df = build_training_dataframe(user_id, db)
    df["date"] = pd.to_datetime(df["date"])
    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["day"] = df["date"].dt.day
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    os.makedirs("data/training", exist_ok=True)
    file_path = f"data/training/{unique_id}.csv"
    df.to_csv(file_path, index=False)
    return file_path, len(df)


def check_retrain_triggers(user_id: int, db: Session) -> dict:
    result = {"should_retrain": False, "triggers": [], "details": {}}

    last_job = db.query(TrainingJob).filter(
        TrainingJob.user_id == user_id,
        TrainingJob.status == "completed"
    ).order_by(TrainingJob.created_at.desc()).first()

    current_count = db.query(OrderLineItem).filter(OrderLineItem.user_id == user_id).count()

    if last_job and last_job.training_record_count:
        growth = (current_count - last_job.training_record_count) / max(last_job.training_record_count, 1)
        result["details"]["data_growth"] = round(growth, 3)
        if growth >= RETRAIN_NEW_DATA_THRESHOLD:
            result["triggers"].append("new_data")
            result["should_retrain"] = True
    elif not last_job and current_count >= MIN_RECORDS_TO_TRAIN:
        result["triggers"].append("first_training")
        result["should_retrain"] = True

    # Compare the data used by the latest successful model with current order data.
    # The reference file is persisted alongside the training run in the shared volume.
    if last_job:
        reference_path = f"data/training/{last_job.unique_id}.csv"
        if os.path.exists(reference_path):
            try:
                reference_df = pd.read_csv(reference_path)
                current_df = build_training_dataframe(user_id, db)
                if not reference_df.empty and not current_df.empty:
                    drift = check_drift(reference_df, current_df, RETRAIN_DRIFT_THRESHOLD)
                    result["details"]["drift"] = drift
                    if drift.get("drift_share", 0) >= RETRAIN_DRIFT_THRESHOLD:
                        result["triggers"].append("data_drift")
                        result["should_retrain"] = True
            except Exception as e:
                logger.error(f"Drift detection failed for user {user_id}: {e}")
                result["details"]["drift_error"] = str(e)

    recent_evals = db.query(DailyEvaluation).filter(
        DailyEvaluation.user_id == user_id,
        DailyEvaluation.skipped == False,
        DailyEvaluation.error.isnot(None)
    ).order_by(DailyEvaluation.date.desc()).limit(7).all()

    if len(recent_evals) >= 3:
        avg_error = sum(e.error for e in recent_evals) / len(recent_evals)
        result["details"]["recent_avg_error"] = round(avg_error, 3)
        if avg_error > RETRAIN_ERROR_THRESHOLD:
            result["triggers"].append("performance_degradation")
            result["should_retrain"] = True

    return result


@router.post("/start")
async def start_training(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record_count = db.query(OrderLineItem).filter(OrderLineItem.user_id == current_user.id).count()
    if record_count < MIN_RECORDS_TO_TRAIN:
        raise HTTPException(status_code=400, detail=f"Need at least {MIN_RECORDS_TO_TRAIN} order line items. You have {record_count}.")

    active_job = db.query(TrainingJob).filter(
        TrainingJob.user_id == current_user.id,
        TrainingJob.status.in_(["pending", "training"])
    ).first()
    if active_job:
        raise HTTPException(status_code=409, detail="A training job is already running for this workspace.")

    unique_id = str(uuid.uuid4())
    job = TrainingJob(
        user_id=current_user.id,
        unique_id=unique_id,
        status="pending",
        trigger="manual",
        training_record_count=record_count
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(run_pipeline, current_user.id, unique_id, current_user.optimization_objective or "revenue")
    return {"message": "Training started", "unique_id": unique_id}


@router.get("/status/{unique_id}")
def get_status(unique_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.query(TrainingJob).filter(
        TrainingJob.unique_id == unique_id,
        TrainingJob.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": job.status, "unique_id": unique_id, "trigger": job.trigger}


@router.get("/history")
def get_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(TrainingJob).filter(
        TrainingJob.user_id == current_user.id
    ).order_by(TrainingJob.created_at.desc()).all()


@router.get("/should-retrain")
def should_retrain(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return check_retrain_triggers(current_user.id, db)


def run_pipeline(user_id: int, unique_id: str, optimization_objective: str = "revenue"):
    import time
    db = SessionLocal()
    try:
        job = db.query(TrainingJob).filter(TrainingJob.unique_id == unique_id).first()
        job.status = "training"
        db.commit()

        file_path, record_count = export_training_csv(user_id, unique_id, db)

        column_mapping = {
            "pricing_column": "price",
            "demand_column": "units_sold",
            "date_column": "date",
            "other_columns": [
                "product_id", "is_promotion", "inventory_level", "channel",
                "day_of_week", "is_weekend", "month", "quarter", "week_of_year", "hour"
            ]
        }

        initial_state = {
            "unique_id": unique_id,
            "file_path": file_path,
            "column_mapping": column_mapping,
            "iteration_count": 0,
            "status": "load_data",
            "error": None,
            "eda_code": None,
            "feature_engineering_code": None,
            "training_code": None,
            "execution_result": None,
            "model_metrics": None,
            "best_metrics": None,
            "engineered_file_path": None,
            "model_file_path": None,
            "best_model_file_path": None,
            "best_feature_importance": None,
            "critic_approved": None,
            "eda_feedback": None,
            "feature_engineering_feedback": None,
            "model_training_feedback": None,
            "mlflow_run_id": None,
            "mlflow_model_uri": None,
            "previous_metrics": None,
            "previous_feature_code": None,
            "feature_importance": None,
            "critic_rejection_count": 0
        }

        result = None
        for retry in range(3):
            try:
                result = pipeline.invoke(initial_state)
                break
            except Exception as e:
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(30)
                else:
                    raise

        if result and result.get("status") == "completed" and result.get("mlflow_run_id"):
            compute_predictions(
                unique_id=unique_id,
                mlflow_run_id=result.get("mlflow_run_id"),
                file_path=file_path,
                column_mapping=column_mapping,
                db=db,
                local_model_path=result.get("best_model_file_path"),
                user_id=user_id,
                optimization_objective=optimization_objective
            )
            job.status = "completed"
            job.mlflow_run_id = result.get("mlflow_run_id")
            job.training_record_count = record_count
        else:
            job.status = "failed"

        db.commit()
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        job = db.query(TrainingJob).filter(TrainingJob.unique_id == unique_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()
