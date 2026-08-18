from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    profile_picture = Column(String)
    auth_provider = Column(String)
    hashed_password = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    reference_data_path = Column(String, nullable=True)
    optimization_objective = Column(String, default="revenue")
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    base_price = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(String, unique=True, index=True)
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
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, ForeignKey("orders.order_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=True)
    inventory_level = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BusinessCalendar(Base):
    __tablename__ = "business_calendar"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String, nullable=False)
    is_closed = Column(Boolean, default=False)
    is_holiday = Column(Boolean, default=False)
    is_festival = Column(Boolean, default=False)
    note = Column(String, nullable=True)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    unique_id = Column(String, unique=True, index=True)
    status = Column(String, default="pending")
    trigger = Column(String, default="manual")
    training_record_count = Column(Integer, nullable=True)
    mlflow_run_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    training_job_id = Column(String, nullable=False)
    optimal_price = Column(Float)
    predicted_demand = Column(Float)
    expected_revenue = Column(Float)
    price_demand_curve = Column(JSON)
    product_results = Column(JSON, nullable=True)
    demand_forecast = Column(JSON, nullable=True)
    optimization_objective = Column(String, default="revenue")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyEvaluation(Base):
    __tablename__ = "daily_evaluations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String, nullable=False)
    training_job_id = Column(String, nullable=False)
    predicted_units = Column(Float, nullable=True)
    actual_units = Column(Float, nullable=True)
    error = Column(Float, nullable=True)
    skipped = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
