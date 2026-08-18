from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.database import get_db
from core.database_models import Order, OrderLineItem, Product, User, BusinessCalendar
from core.dependencies import get_current_user
from core.logger import get_logger
from pydantic import BaseModel
from typing import Optional, List, Literal
import pandas as pd
from io import BytesIO, StringIO
from datetime import datetime
import uuid
import csv

router = APIRouter()
logger = get_logger(__name__)


def _parse_promotion(value) -> bool:
    """Parse CSV booleans explicitly; bool('0') is True in Python."""
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


class LineItemInput(BaseModel):
    product_id: str
    quantity: int = 1
    unit_price: float
    unit_cost: Optional[float] = None
    inventory_level: Optional[int] = None


class OrderCreate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    order_time: Optional[str] = None
    channel: Optional[str] = None
    is_promotion: Optional[bool] = False
    notes: Optional[str] = None
    line_items: List[LineItemInput]


@router.post("/")
def create_order(
    order: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not order.line_items:
        raise HTTPException(status_code=400, detail="Order must have at least one item")

    product_map = {
        p.product_id: p
        for p in db.query(Product).filter(Product.user_id == current_user.id).all()
    }

    for item in order.line_items:
        if item.product_id not in product_map:
            raise HTTPException(status_code=400, detail=f"Product '{item.product_id}' not found")

    order_time = datetime.fromisoformat(order.order_time) if order.order_time else datetime.utcnow()
    order_id = str(uuid.uuid4())

    total_revenue = sum(i.quantity * i.unit_price for i in order.line_items)
    total_cost = sum(
        i.quantity * (i.unit_cost or product_map[i.product_id].cost or 0)
        for i in order.line_items
    )
    total_profit = total_revenue - total_cost

    db_order = Order(
        user_id=current_user.id,
        order_id=order_id,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        order_time=order_time,
        date=order_time.strftime("%Y-%m-%d"),
        channel=order.channel,
        is_promotion=order.is_promotion or False,
        notes=order.notes,
        total_revenue=round(total_revenue, 2),
        total_cost=round(total_cost, 2),
        total_profit=round(total_profit, 2)
    )
    db.add(db_order)

    for item in order.line_items:
        product = product_map[item.product_id]
        db.add(OrderLineItem(
            order_id=order_id,
            user_id=current_user.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            unit_cost=item.unit_cost or product.cost,
            inventory_level=item.inventory_level
        ))

    db.commit()
    db.refresh(db_order)
    logger.info(f"Order {order_id} created for user {current_user.id}")
    return {"order_id": order_id, "total_revenue": total_revenue, "total_profit": total_profit}


@router.get("/")
def get_orders(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders = db.query(Order).filter(
        Order.user_id == current_user.id
    ).order_by(Order.order_time.desc()).limit(limit).all()

    result = []
    for o in orders:
        items = db.query(OrderLineItem).filter(OrderLineItem.order_id == o.order_id).all()
        result.append({
            "order_id": o.order_id,
            "customer_name": o.customer_name,
            "customer_email": o.customer_email,
            "order_time": o.order_time,
            "date": o.date,
            "channel": o.channel,
            "is_promotion": o.is_promotion,
            "total_revenue": o.total_revenue,
            "total_cost": o.total_cost,
            "total_profit": o.total_profit,
            "items": [{"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price} for i in items]
        })
    return result


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders = db.query(Order).filter(Order.user_id == current_user.id).all()
    if not orders:
        return {
            "total_orders": 0, "total_revenue": 0, "total_profit": 0,
            "unique_customers": 0, "date_range": None, "products": []
        }

    df = pd.DataFrame([{
        "order_id": o.order_id,
        "customer_email": o.customer_email,
        "date": o.date,
        "total_revenue": o.total_revenue or 0,
        "total_profit": o.total_profit or 0
    } for o in orders])

    items = db.query(OrderLineItem).filter(OrderLineItem.user_id == current_user.id).all()
    products = list({i.product_id for i in items})

    return {
        "total_orders": len(orders),
        "total_revenue": round(float(df["total_revenue"].sum()), 2),
        "total_profit": round(float(df["total_profit"].sum()), 2),
        "unique_customers": int(df["customer_email"].nunique()),
        "date_range": {"start": df["date"].min(), "end": df["date"].max()},
        "products": products
    }


@router.get("/aggregated")
def get_aggregated(
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders = db.query(Order).filter(Order.user_id == current_user.id).all()
    if not orders:
        return []

    df = pd.DataFrame([{
        "order_time": o.order_time,
        "total_revenue": o.total_revenue or 0,
        "total_profit": o.total_profit or 0
    } for o in orders])

    df["order_time"] = pd.to_datetime(df["order_time"])

    if granularity == "daily":
        df["period"] = df["order_time"].dt.strftime("%Y-%m-%d")
    elif granularity == "weekly":
        df["period"] = df["order_time"].dt.to_period("W").astype(str)
    else:
        df["period"] = df["order_time"].dt.to_period("M").astype(str)

    grouped = df.groupby("period").agg(
        orders=("total_revenue", "count"),
        revenue=("total_revenue", "sum"),
        profit=("total_profit", "sum")
    ).reset_index()

    return grouped.to_dict("records")


@router.get("/by-product")
def get_by_product(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items = db.query(OrderLineItem).filter(OrderLineItem.user_id == current_user.id).all()
    if not items:
        return []

    df = pd.DataFrame([{
        "product_id": i.product_id,
        "quantity": i.quantity,
        "unit_price": i.unit_price,
        "revenue": i.quantity * i.unit_price,
        "profit": i.quantity * ((i.unit_price or 0) - (i.unit_cost or 0))
    } for i in items])

    grouped = df.groupby("product_id").agg(
        total_quantity=("quantity", "sum"),
        total_revenue=("revenue", "sum"),
        total_profit=("profit", "sum"),
        avg_price=("unit_price", "mean"),
        orders=("quantity", "count")
    ).reset_index()

    return grouped.to_dict("records")


@router.get("/customers")
def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders = db.query(Order).filter(
        Order.user_id == current_user.id,
        Order.customer_email.isnot(None)
    ).all()
    if not orders:
        return []

    df = pd.DataFrame([{
        "customer_email": o.customer_email,
        "customer_name": o.customer_name,
        "date": o.date,
        "total_revenue": o.total_revenue or 0,
        "total_profit": o.total_profit or 0
    } for o in orders])

    grouped = df.groupby("customer_email").agg(
        customer_name=("customer_name", "first"),
        total_orders=("total_revenue", "count"),
        total_spent=("total_revenue", "sum"),
        total_profit=("total_profit", "sum"),
        first_order=("date", "min"),
        last_order=("date", "max")
    ).reset_index()

    grouped = grouped.sort_values("total_spent", ascending=False)
    return grouped.to_dict("records")


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(
        Order.order_id == order_id,
        Order.user_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.query(OrderLineItem).filter(OrderLineItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"message": "Order deleted"}


@router.get("/template")
def download_template(current_user: User = Depends(get_current_user)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "customer_name", "customer_email", "order_time", "channel",
        "is_promotion", "product_id", "quantity", "unit_price", "unit_cost", "inventory_level"
    ])
    writer.writerow(["John Doe", "john@example.com", "2024-01-15 10:30:00", "in-store", "0", "P001", "2", "29.99", "15.00", "200"])
    writer.writerow(["John Doe", "john@example.com", "2024-01-15 10:30:00", "in-store", "0", "P002", "1", "49.99", "25.00", "150"])
    writer.writerow(["Jane Smith", "jane@example.com", "2024-01-15 14:00:00", "online", "1", "P001", "3", "24.99", "15.00", "198"])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_template.csv"}
    )


@router.post("/import")
async def import_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    contents = await file.read()
    try:
        df = pd.read_csv(BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read CSV")

    required = {"product_id", "quantity", "unit_price"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    product_map = {
        p.product_id: p
        for p in db.query(Product).filter(Product.user_id == current_user.id).all()
    }

    # Group rows by order (same customer + same order_time = same order)
    if "order_time" in df.columns and "customer_email" in df.columns:
        df["_order_key"] = df["customer_email"].fillna("guest") + "|" + df["order_time"].astype(str)
    else:
        df["_order_key"] = df.index.astype(str)

    errors = []
    orders_created = 0

    for order_key, group in df.groupby("_order_key"):
        order_time_str = group["order_time"].iloc[0] if "order_time" in group.columns else None
        try:
            order_time = datetime.fromisoformat(str(order_time_str)) if order_time_str and pd.notna(order_time_str) else datetime.utcnow()
        except ValueError:
            errors.append(f"Invalid order_time for order group '{order_key}'")
            continue
        order_id = str(uuid.uuid4())
        customer_email = group["customer_email"].iloc[0] if "customer_email" in group.columns and pd.notna(group["customer_email"].iloc[0]) else None
        customer_name = group["customer_name"].iloc[0] if "customer_name" in group.columns and pd.notna(group["customer_name"].iloc[0]) else None
        channel = group["channel"].iloc[0] if "channel" in group.columns and pd.notna(group["channel"].iloc[0]) else None
        is_promotion = _parse_promotion(group["is_promotion"].iloc[0]) if "is_promotion" in group.columns else False

        line_items = []
        total_revenue = 0
        total_cost = 0

        for _, row in group.iterrows():
            pid = str(row["product_id"])
            if pid not in product_map:
                errors.append(f"Product '{pid}' not found")
                continue
            product = product_map[pid]
            try:
                qty = int(row["quantity"])
                price = float(row["unit_price"])
                cost = float(row["unit_cost"]) if "unit_cost" in row and pd.notna(row.get("unit_cost")) else (product.cost or 0)
                inventory_level = int(row["inventory_level"]) if "inventory_level" in row and pd.notna(row.get("inventory_level")) else None
            except (TypeError, ValueError):
                errors.append(f"Invalid quantity, price, cost, or inventory for product '{pid}'")
                continue
            if qty <= 0 or price < 0 or cost < 0 or (inventory_level is not None and inventory_level < 0):
                errors.append(f"Quantity, price, cost, and inventory must be non-negative for product '{pid}'")
                continue
            total_revenue += qty * price
            total_cost += qty * cost
            line_items.append(OrderLineItem(
                order_id=order_id,
                user_id=current_user.id,
                product_id=pid,
                quantity=qty,
                unit_price=price,
                unit_cost=cost,
                inventory_level=inventory_level,
            ))

        if not line_items:
            continue

        db.add(Order(
            user_id=current_user.id,
            order_id=order_id,
            customer_name=customer_name,
            customer_email=customer_email,
            order_time=order_time,
            date=order_time.strftime("%Y-%m-%d"),
            channel=channel,
            is_promotion=is_promotion,
            total_revenue=round(total_revenue, 2),
            total_cost=round(total_cost, 2),
            total_profit=round(total_revenue - total_cost, 2)
        ))
        db.add_all(line_items)
        orders_created += 1

    db.commit()
    return {"orders_created": orders_created, "errors": errors or None}


# Calendar
class CalendarEntry(BaseModel):
    date: str
    is_closed: Optional[bool] = False
    is_holiday: Optional[bool] = False
    is_festival: Optional[bool] = False
    note: Optional[str] = None


@router.post("/calendar")
def set_calendar(entry: CalendarEntry, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(BusinessCalendar).filter(
        BusinessCalendar.user_id == current_user.id,
        BusinessCalendar.date == entry.date
    ).first()
    if existing:
        for k, v in entry.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        db.commit()
        return existing
    cal = BusinessCalendar(user_id=current_user.id, **entry.model_dump())
    db.add(cal)
    db.commit()
    db.refresh(cal)
    return cal


@router.get("/calendar")
def get_calendar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(BusinessCalendar).filter(BusinessCalendar.user_id == current_user.id).all()
