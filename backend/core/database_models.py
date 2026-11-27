from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, ForeignKey, Boolean, Text, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    profile_picture = Column(String, nullable=True)
    auth_provider = Column(String, default="local")
    hashed_password = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    reference_data_path = Column(String, nullable=True)
    optimization_objective = Column(String, default="revenue", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product"),
        Index("ix_products_user_id", "user_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    base_price = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    stock_on_hand = Column(Integer, nullable=True, default=0)
    lead_time_days = Column(Integer, nullable=False, default=7)
    service_level = Column(Float, nullable=False, default=0.95)
    holding_cost_per_unit = Column(Float, nullable=True)
    reorder_cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_date", "user_id", "date"),
        Index("ix_orders_user_time", "user_id", "order_time"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(String, unique=True, index=True, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    order_time = Column(DateTime, nullable=False)
    date = Column(String, nullable=False)
    channel = Column(String, nullable=True)
    is_promotion = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    total_revenue = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    total_profit = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderLineItem(Base):
    __tablename__ = "order_line_items"
    __table_args__ = (
        Index("ix_line_items_user_product", "user_id", "product_id"),
        Index("ix_line_items_order_id", "order_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=True)
    inventory_level = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BusinessCalendar(Base):
    __tablename__ = "business_calendar"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_calendar_date"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String, nullable=False)
    is_closed = Column(Boolean, default=False)
    is_holiday = Column(Boolean, default=False)
    is_festival = Column(Boolean, default=False)
    note = Column(String, nullable=True)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    __table_args__ = (
        Index("ix_training_jobs_user_created", "user_id", "created_at"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    unique_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="pending")
    trigger = Column(String, default="manual")
    training_record_count = Column(Integer, nullable=True)
    mlflow_run_id = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    metrics = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_user_created", "user_id", "created_at"),
        Index("ix_predictions_job_id", "training_job_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    training_job_id = Column(String, nullable=False)
    optimal_price = Column(Float)
    predicted_demand = Column(Float)
    expected_revenue = Column(Float)
    price_demand_curve = Column(JSON)
    product_results = Column(JSON, nullable=True)
    demand_forecast = Column(JSON, nullable=True)
    inventory_recommendations = Column(JSON, nullable=True)
    model_summary = Column(JSON, nullable=True)
    optimization_objective = Column(String, default="revenue")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyEvaluation(Base):
    __tablename__ = "daily_evaluations"
    __table_args__ = (
        Index("ix_daily_eval_user_date", "user_id", "date"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String, nullable=False)
    training_job_id = Column(String, nullable=False)
    predicted_units = Column(Float, nullable=True)
    actual_units = Column(Float, nullable=True)
    error = Column(Float, nullable=True)
    skipped = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceHealth(Base):
    __tablename__ = "workspace_health"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    should_retrain = Column(Boolean, default=False)
    triggers = Column(JSON, nullable=True)
    details = Column(JSON, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)
