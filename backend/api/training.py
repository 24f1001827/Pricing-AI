from datetime import datetime, timedelta
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import pandas as pd
from sqlalchemy.orm import Session

from core.config import (
    DATA_DIR,
    MIN_RECORDS_TO_TRAIN,
    RETRAIN_DRIFT_THRESHOLD,
    RETRAIN_ERROR_THRESHOLD,
    RETRAIN_NEW_DATA_THRESHOLD,
    TRAINING_STALE_MINUTES,
)
from core.database import SessionLocal, get_db
from core.database_models import (
    BusinessCalendar,
    DailyEvaluation,
    Order,
    OrderLineItem,
    Product,
    TrainingJob,
    User,
    WorkspaceHealth,
)
from core.dependencies import get_current_user
from core.logger import get_logger
from ml.optimizer import compute_and_store_predictions
from ml.profiler import aggregate_daily_sku_demand, profile_dataset
from ml.strategist import build_training_plan
from ml.trainer import train_best_pipeline
from scipy.stats import ks_2samp

router = APIRouter()
logger = get_logger(__name__)


def build_raw_line_items_dataframe(user_id: int, db: Session) -> pd.DataFrame:
    """Load line-item records joined with order metadata without derived target leakage columns."""
    orders = db.query(Order).filter(Order.user_id == user_id).all()
    items = db.query(OrderLineItem).filter(OrderLineItem.user_id == user_id).all()
    if not orders or not items:
        return pd.DataFrame()

    order_map = {o.order_id: o for o in orders}
    products = db.query(Product).filter(Product.user_id == user_id).all()
    product_cost_map = {p.product_id: p.cost or 0.0 for p in products}

    rows = []
    for item in items:
        order = order_map.get(item.order_id)
        if not order:
            continue
        rows.append({
            "date": order.date,
            "product_id": item.product_id,
            "units_sold": item.quantity,
            "price": item.unit_price,
            "cost": item.unit_cost if item.unit_cost is not None else product_cost_map.get(item.product_id, 0.0),
            "is_promotion": 1 if order.is_promotion else 0,
            "inventory_level": item.inventory_level,
            "channel": order.channel or "unknown",
        })

    return pd.DataFrame(rows)


def build_calendar_dataframe(user_id: int, db: Session) -> pd.DataFrame:
    rows = db.query(BusinessCalendar).filter(BusinessCalendar.user_id == user_id).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "date": r.date,
            "is_closed": 1 if r.is_closed else 0,
            "is_holiday": 1 if r.is_holiday else 0,
            "is_festival": 1 if r.is_festival else 0,
        }
        for r in rows
    ])


def export_training_csv(user_id: int, unique_id: str, db: Session, enable_lags: bool = True):
    raw_df = build_raw_line_items_dataframe(user_id, db)
    cal_df = build_calendar_dataframe(user_id, db)
    daily_df = aggregate_daily_sku_demand(raw_df, cal_df, enable_lags=enable_lags)
    training_dir = os.path.join(DATA_DIR, "training")
    os.makedirs(training_dir, exist_ok=True)
    file_path = os.path.join(training_dir, f"{unique_id}.csv")
    daily_df.to_csv(file_path, index=False)
    return file_path, daily_df, len(raw_df)


def recover_stale_jobs(db: Session | None = None) -> int:
    """Mark orphaned pending/training jobs as failed after timeout or worker restart."""
    own_session = db is None
    session = db or SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=TRAINING_STALE_MINUTES)
        stale_jobs = (
            session.query(TrainingJob)
            .filter(
                TrainingJob.status.in_(["pending", "training"]),
                TrainingJob.created_at < cutoff,
            )
            .all()
        )
        for job in stale_jobs:
            job.status = "failed"
            job.error_message = "Training job exceeded timeout or worker restarted before completion."
        if stale_jobs:
            session.commit()
            logger.warning(f"Recovered {len(stale_jobs)} stale training job(s)")
        return len(stale_jobs)
    finally:
        if own_session:
            session.close()


def check_retrain_triggers(user_id: int, db: Session, persist: bool = True) -> dict:
    result = {"should_retrain": False, "triggers": [], "details": {}}

    last_job = (
        db.query(TrainingJob)
        .filter(TrainingJob.user_id == user_id, TrainingJob.status == "completed")
        .order_by(TrainingJob.created_at.desc())
        .first()
    )
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

    if last_job:
        reference_path = os.path.join(DATA_DIR, "training", f"{last_job.unique_id}.csv")
        if os.path.exists(reference_path):
            try:
                reference_df = pd.read_csv(reference_path)
                raw_df = build_raw_line_items_dataframe(user_id, db)
                cal_df = build_calendar_dataframe(user_id, db)
                current_df = aggregate_daily_sku_demand(raw_df, cal_df, enable_lags=True)
                drift_cols = [
                    c for c in ["price", "units_sold", "is_promotion", "day_of_week", "is_weekend"]
                    if c in reference_df.columns and c in current_df.columns
                ]
                if not reference_df.empty and not current_df.empty and drift_cols:
                    drifted = []
                    for col in drift_cols:
                        try:
                            _, p = ks_2samp(reference_df[col].dropna(), current_df[col].dropna())
                            if p < 0.05:
                                drifted.append(col)
                        except Exception:
                            pass
                    drift = {
                        "drift_detected": len(drifted) > 0,
                        "drift_share": round(len(drifted) / len(drift_cols), 3),
                        "drifted_columns": drifted,
                    }
                    result["details"]["drift"] = drift
                    if drift.get("drift_share", 0) >= RETRAIN_DRIFT_THRESHOLD:
                        result["triggers"].append("data_drift")
                        result["should_retrain"] = True
            except Exception as e:
                logger.error(f"Drift detection failed for user {user_id}: {e}")
                result["details"]["drift_error"] = str(e)

    recent_evals = (
        db.query(DailyEvaluation)
        .filter(
            DailyEvaluation.user_id == user_id,
            DailyEvaluation.skipped == False,
            DailyEvaluation.error.isnot(None),
        )
        .order_by(DailyEvaluation.date.desc())
        .limit(7)
        .all()
    )
    if len(recent_evals) >= 3:
        avg_error = sum(e.error for e in recent_evals) / len(recent_evals)
        result["details"]["recent_avg_error"] = round(avg_error, 3)
        if avg_error > RETRAIN_ERROR_THRESHOLD:
            result["triggers"].append("performance_degradation")
            result["should_retrain"] = True

    if persist:
        health = db.query(WorkspaceHealth).filter(WorkspaceHealth.user_id == user_id).first()
        if health:
            health.should_retrain = result["should_retrain"]
            health.triggers = result["triggers"]
            health.details = result["details"]
            health.checked_at = datetime.utcnow()
        else:
            db.add(
                WorkspaceHealth(
                    user_id=user_id,
                    should_retrain=result["should_retrain"],
                    triggers=result["triggers"],
                    details=result["details"],
                    checked_at=datetime.utcnow(),
                )
            )
        db.commit()

    return result


@router.post("/start")
async def start_training(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recover_stale_jobs(db)
    record_count = db.query(OrderLineItem).filter(OrderLineItem.user_id == current_user.id).count()
    if record_count < MIN_RECORDS_TO_TRAIN:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {MIN_RECORDS_TO_TRAIN} order line items. You have {record_count}.",
        )

    active_job = (
        db.query(TrainingJob)
        .filter(
            TrainingJob.user_id == current_user.id,
            TrainingJob.status.in_(["pending", "training"]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(status_code=409, detail="A training job is already running for this workspace.")

    unique_id = str(uuid.uuid4())
    job = TrainingJob(
        user_id=current_user.id,
        unique_id=unique_id,
        status="pending",
        trigger="manual",
        training_record_count=record_count,
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(
        run_pipeline,
        current_user.id,
        unique_id,
        current_user.optimization_objective or "revenue",
    )
    return {"message": "Training started", "unique_id": unique_id}


@router.get("/status/{unique_id}")
def get_status(
    unique_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recover_stale_jobs(db)
    job = (
        db.query(TrainingJob)
        .filter(TrainingJob.unique_id == unique_id, TrainingJob.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": job.status,
        "unique_id": unique_id,
        "trigger": job.trigger,
        "model_name": job.model_name,
        "metrics": job.metrics,
        "error_message": job.error_message,
    }


@router.get("/history")
def get_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(TrainingJob)
        .filter(TrainingJob.user_id == current_user.id)
        .order_by(TrainingJob.created_at.desc())
        .all()
    )


@router.get("/evaluations")
def get_evaluations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(DailyEvaluation)
        .filter(DailyEvaluation.user_id == current_user.id)
        .order_by(DailyEvaluation.date.desc())
        .limit(30)
        .all()
    )


@router.get("/should-retrain")
def should_retrain(
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not refresh:
        cached = db.query(WorkspaceHealth).filter(WorkspaceHealth.user_id == current_user.id).first()
        if cached and cached.checked_at and (datetime.utcnow() - cached.checked_at) < timedelta(hours=6):
            return {
                "should_retrain": cached.should_retrain,
                "triggers": cached.triggers or [],
                "details": cached.details or {},
                "checked_at": cached.checked_at,
            }
    return check_retrain_triggers(current_user.id, db, persist=True)


def run_pipeline(user_id: int, unique_id: str, optimization_objective: str = "revenue"):
    db = SessionLocal()
    try:
        job = db.query(TrainingJob).filter(TrainingJob.unique_id == unique_id).first()
        if not job:
            return
        job.status = "training"
        db.commit()

        _, daily_df, raw_count = export_training_csv(user_id, unique_id, db, enable_lags=True)
        if daily_df.empty or len(daily_df) < 10:
            raise ValueError(
                f"Training requires at least 10 daily SKU observations after aggregation (found {len(daily_df)})."
            )

        profile = profile_dataset(daily_df)
        plan = build_training_plan(profile)
        if not plan.enable_lags:
            _, daily_df, raw_count = export_training_csv(user_id, unique_id, db, enable_lags=False)

        train_res = train_best_pipeline(
            daily_df=daily_df,
            unique_id=unique_id,
            plan=plan,
            profile=profile,
        )

        compute_and_store_predictions(
            unique_id=unique_id,
            daily_df=daily_df,
            training_result=train_res,
            db=db,
            user_id=user_id,
            optimization_objective=optimization_objective,
        )

        job.status = "completed"
        job.model_name = train_res["model_name"]
        job.metrics = train_res["metrics"]
        job.mlflow_run_id = train_res.get("mlflow_run_id")
        job.training_record_count = raw_count
        job.error_message = None
        db.commit()

        check_retrain_triggers(user_id, db, persist=True)
        logger.info(f"Training pipeline completed for job {unique_id} using {train_res['model_name']}")
    except Exception as e:
        logger.error(f"Pipeline failed for job {unique_id}: {e}")
        job = db.query(TrainingJob).filter(TrainingJob.unique_id == unique_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
    finally:
        db.close()
