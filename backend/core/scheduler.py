from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from core.logger import get_logger
from core.config import DATABASE_URL, SCHEDULER_TIMEZONE
from core.database import SessionLocal
from core.database_models import User, Order, OrderLineItem, TrainingJob, DailyEvaluation, Prediction, BusinessCalendar
import uuid
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text

logger = get_logger(__name__)
scheduler = BackgroundScheduler()


def _acquire_scheduler_lock(db) -> bool:
    """Ensure only one scheduler instance runs the nightly evaluation on Postgres."""
    if not DATABASE_URL.startswith("postgres"):
        return True
    return bool(db.execute(text("SELECT pg_try_advisory_lock(827164)")).scalar())


def _release_scheduler_lock(db) -> None:
    if DATABASE_URL.startswith("postgres"):
        db.execute(text("SELECT pg_advisory_unlock(827164)"))


def nightly_evaluation():
    logger.info("Running nightly evaluation")
    db = SessionLocal()
    try:
        if not _acquire_scheduler_lock(db):
            logger.warning("Nightly evaluation skipped because another scheduler holds the lock")
            return
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        for user in db.query(User).all():
            try:
                _evaluate_user(user, yesterday, db)
            except Exception as e:
                logger.error(f"Evaluation failed for user {user.id}: {e}")
    finally:
        _release_scheduler_lock(db)
        db.close()


def _evaluate_user(user, date_str: str, db):
    from api.training import check_retrain_triggers, run_pipeline

    calendar = db.query(BusinessCalendar).filter(
        BusinessCalendar.user_id == user.id,
        BusinessCalendar.date == date_str
    ).first()

    if calendar and calendar.is_closed:
        db.add(DailyEvaluation(user_id=user.id, date=date_str, training_job_id="N/A", skipped=True))
        db.commit()
        return

    evaluation_date = datetime.strptime(date_str, "%Y-%m-%d")
    forecast_start = evaluation_date - timedelta(days=1)
    latest = db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.created_at >= forecast_start,
        Prediction.created_at < evaluation_date,
    ).order_by(Prediction.created_at.desc()).first()
    if not latest or not latest.demand_forecast:
        return

    orders = db.query(Order).filter(Order.user_id == user.id, Order.date == date_str).all()
    if not orders:
        return

    items = db.query(OrderLineItem).filter(
        OrderLineItem.user_id == user.id,
        OrderLineItem.order_id.in_([o.order_id for o in orders])
    ).all()
    actual_units = sum(i.quantity for i in items)
    predicted_units = latest.demand_forecast.get("total", {}).get("day1")
    error = abs(actual_units - predicted_units) / max(actual_units, 1) if predicted_units else None

    db.add(DailyEvaluation(
        user_id=user.id,
        date=date_str,
        training_job_id=latest.training_job_id,
        predicted_units=predicted_units,
        actual_units=actual_units,
        error=error,
        skipped=False
    ))
    db.commit()

    triggers = check_retrain_triggers(user.id, db)
    if triggers["should_retrain"]:
        active_job = db.query(TrainingJob).filter(
            TrainingJob.user_id == user.id,
            TrainingJob.status.in_(["pending", "training"])
        ).first()
        if active_job:
            logger.info(f"Auto-retraining skipped for user {user.id}; job {active_job.unique_id} is already active")
            return
        logger.info(f"Auto-retraining for user {user.id}: {triggers['triggers']}")
        unique_id = str(uuid.uuid4())
        job = TrainingJob(user_id=user.id, unique_id=unique_id, status="pending", trigger=",".join(triggers["triggers"]))
        db.add(job)
        db.commit()
        import threading
        t = threading.Thread(target=run_pipeline, args=(user.id, unique_id, user.optimization_objective or "revenue"))
        t.daemon = True
        t.start()


def start_scheduler():
    scheduler.add_job(
        nightly_evaluation,
        CronTrigger(hour=23, minute=30, timezone=SCHEDULER_TIMEZONE),
        id="nightly",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(f"Scheduler started in timezone {SCHEDULER_TIMEZONE}")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
