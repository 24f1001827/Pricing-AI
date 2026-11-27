from collections import defaultdict
import csv
from datetime import datetime
from io import BytesIO, StringIO
from typing import List, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from core.database_models import BusinessCalendar, Order, OrderLineItem, Product, User
from core.dependencies import get_current_user
from core.logger import get_logger

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
    product_id: str = Field(min_length=1)
    quantity: int = Field(default=1, gt=0, le=1000000)
    unit_price: float = Field(ge=0)
    unit_cost: Optional[float] = Field(default=None, ge=0)
    inventory_level: Optional[int] = Field(default=None, ge=0)


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
    current_user: User = Depends(get_current_user),
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

    try:
        order_time = (
            datetime.fromisoformat(order.order_time.replace("Z", "+00:00")).replace(tzinfo=None)
            if order.order_time
            else datetime.utcnow()
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_time ISO format")

    order_id = str(uuid.uuid4())
    total_revenue = sum(i.quantity * i.unit_price for i in order.line_items)
    total_cost = sum(
        i.quantity * (i.unit_cost if i.unit_cost is not None else (product_map[i.product_id].cost or 0.0))
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
        total_profit=round(total_profit, 2),
    )
    db.add(db_order)

    for item in order.line_items:
        product = product_map[item.product_id]
        unit_cost = item.unit_cost if item.unit_cost is not None else product.cost
        if item.inventory_level is not None:
            product.stock_on_hand = item.inventory_level
        elif product.stock_on_hand is not None and product.stock_on_hand > 0:
            product.stock_on_hand = max(0, product.stock_on_hand - item.quantity)

        db.add(
            OrderLineItem(
                order_id=order_id,
                user_id=current_user.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                unit_cost=unit_cost,
                inventory_level=item.inventory_level if item.inventory_level is not None else product.stock_on_hand,
            )
        )

    db.commit()
    db.refresh(db_order)
    logger.info(f"Order {order_id} created for user {current_user.id}")
    return {"order_id": order_id, "total_revenue": round(total_revenue, 2), "total_profit": round(total_profit, 2)}


@router.get("/")
def get_orders(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orders = (
        db.query(Order)
        .filter(Order.user_id == current_user.id)
        .order_by(Order.order_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    if not orders:
        return []

    order_ids = [o.order_id for o in orders]
    all_items = (
        db.query(OrderLineItem)
        .filter(OrderLineItem.user_id == current_user.id, OrderLineItem.order_id.in_(order_ids))
        .all()
    )
    items_by_order: dict[str, list] = defaultdict(list)
    for item in all_items:
        items_by_order[item.order_id].append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        })

    return [
        {
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
            "items": items_by_order.get(o.order_id, []),
        }
        for o in orders
    ]


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agg = (
        db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_revenue), 0.0),
            func.coalesce(func.sum(Order.total_profit), 0.0),
            func.count(func.distinct(Order.customer_email)),
            func.min(Order.date),
            func.max(Order.date),
        )
        .filter(Order.user_id == current_user.id)
        .one()
    )
    total_orders, total_revenue, total_profit, unique_customers, start_date, end_date = agg
    line_item_count = (
        db.query(func.count(OrderLineItem.id))
        .filter(OrderLineItem.user_id == current_user.id)
        .scalar()
        or 0
    )
    product_rows = (
        db.query(Product.product_id)
        .filter(Product.user_id == current_user.id)
        .all()
    )
    products = [r[0] for r in product_rows]

    if not total_orders:
        return {
            "total_orders": 0,
            "total_line_items": 0,
            "total_revenue": 0.0,
            "total_profit": 0.0,
            "unique_customers": 0,
            "date_range": None,
            "products": products,
        }

    return {
        "total_orders": int(total_orders),
        "total_line_items": int(line_item_count),
        "total_revenue": round(float(total_revenue), 2),
        "total_profit": round(float(total_profit), 2),
        "unique_customers": int(unique_customers or 0),
        "date_range": {"start": start_date, "end": end_date},
        "products": products,
    }


@router.get("/aggregated")
def get_aggregated(
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    daily_rows = (
        db.query(
            Order.date.label("date"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_revenue), 0.0).label("revenue"),
            func.coalesce(func.sum(Order.total_profit), 0.0).label("profit"),
        )
        .filter(Order.user_id == current_user.id)
        .group_by(Order.date)
        .order_by(Order.date.asc())
        .all()
    )
    if not daily_rows:
        return []

    if granularity == "daily":
        return [
            {
                "period": r.date,
                "orders": int(r.orders),
                "revenue": round(float(r.revenue), 2),
                "profit": round(float(r.profit), 2),
            }
            for r in daily_rows
        ]

    df = pd.DataFrame([
        {
            "date": r.date,
            "orders": int(r.orders),
            "revenue": float(r.revenue),
            "profit": float(r.profit),
        }
        for r in daily_rows
    ])
    df["dt"] = pd.to_datetime(df["date"])
    df["period"] = (
        df["dt"].dt.to_period("W").astype(str)
        if granularity == "weekly"
        else df["dt"].dt.to_period("M").astype(str)
    )
    grouped = (
        df.groupby("period", sort=True)
        .agg(orders=("orders", "sum"), revenue=("revenue", "sum"), profit=("profit", "sum"))
        .reset_index()
    )
    return [
        {
            "period": row["period"],
            "orders": int(row["orders"]),
            "revenue": round(float(row["revenue"]), 2),
            "profit": round(float(row["profit"]), 2),
        }
        for row in grouped.to_dict("records")
    ]


@router.get("/by-product")
def get_by_product(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(
            OrderLineItem.product_id,
            func.coalesce(func.sum(OrderLineItem.quantity), 0).label("total_quantity"),
            func.coalesce(func.sum(OrderLineItem.quantity * OrderLineItem.unit_price), 0.0).label("total_revenue"),
            func.coalesce(
                func.sum(OrderLineItem.quantity * (OrderLineItem.unit_price - func.coalesce(OrderLineItem.unit_cost, 0.0))),
                0.0,
            ).label("total_profit"),
            func.coalesce(func.avg(OrderLineItem.unit_price), 0.0).label("avg_price"),
            func.count(OrderLineItem.id).label("orders"),
        )
        .filter(OrderLineItem.user_id == current_user.id)
        .group_by(OrderLineItem.product_id)
        .all()
    )
    return [
        {
            "product_id": r.product_id,
            "total_quantity": int(r.total_quantity),
            "total_revenue": round(float(r.total_revenue), 2),
            "total_profit": round(float(r.total_profit), 2),
            "avg_price": round(float(r.avg_price), 2),
            "orders": int(r.orders),
        }
        for r in rows
    ]


@router.get("/customers")
def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(
            Order.customer_email,
            func.max(Order.customer_name).label("customer_name"),
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.total_revenue), 0.0).label("total_spent"),
            func.coalesce(func.sum(Order.total_profit), 0.0).label("total_profit"),
            func.min(Order.date).label("first_order"),
            func.max(Order.date).label("last_order"),
        )
        .filter(Order.user_id == current_user.id, Order.customer_email.isnot(None))
        .group_by(Order.customer_email)
        .order_by(func.sum(Order.total_revenue).desc())
        .all()
    )
    return [
        {
            "customer_email": r.customer_email,
            "customer_name": r.customer_name,
            "total_orders": int(r.total_orders),
            "total_spent": round(float(r.total_spent), 2),
            "total_profit": round(float(r.total_profit), 2),
            "first_order": r.first_order,
            "last_order": r.last_order,
        }
        for r in rows
    ]


@router.get("/template")
def download_template(current_user: User = Depends(get_current_user)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "customer_name", "customer_email", "order_time", "channel",
        "is_promotion", "product_id", "quantity", "unit_price", "unit_cost", "inventory_level",
    ])
    writer.writerow(["John Doe", "john@example.com", "2024-01-15 10:30:00", "in-store", "0", "P001", "2", "29.99", "15.00", "200"])
    writer.writerow(["John Doe", "john@example.com", "2024-01-15 10:30:00", "in-store", "0", "P002", "1", "49.99", "25.00", "150"])
    writer.writerow(["Jane Smith", "jane@example.com", "2024-01-15 14:00:00", "online", "1", "P001", "3", "24.99", "15.00", "197"])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_template.csv"},
    )


@router.post("/import")
async def import_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")

    contents = await file.read()
    try:
        df = pd.read_csv(BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read CSV")

    required = {"product_id", "quantity", "unit_price"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {sorted(missing)}")

    product_map = {
        p.product_id: p
        for p in db.query(Product).filter(Product.user_id == current_user.id).all()
    }

    if "order_time" in df.columns and "customer_email" in df.columns:
        df["_order_key"] = df["customer_email"].fillna("guest") + "|" + df["order_time"].astype(str)
    else:
        df["_order_key"] = df.index.astype(str)

    errors = []
    orders_created = 0

    for order_key, group in df.groupby("_order_key"):
        order_time_str = group["order_time"].iloc[0] if "order_time" in group.columns else None
        try:
            order_time = (
                datetime.fromisoformat(str(order_time_str))
                if order_time_str and pd.notna(order_time_str)
                else datetime.utcnow()
            )
        except ValueError:
            errors.append(f"Invalid order_time for order group '{order_key}'")
            continue

        order_id = str(uuid.uuid4())
        customer_email = (
            group["customer_email"].iloc[0]
            if "customer_email" in group.columns and pd.notna(group["customer_email"].iloc[0])
            else None
        )
        customer_name = (
            group["customer_name"].iloc[0]
            if "customer_name" in group.columns and pd.notna(group["customer_name"].iloc[0])
            else None
        )
        channel = (
            group["channel"].iloc[0]
            if "channel" in group.columns and pd.notna(group["channel"].iloc[0])
            else None
        )
        is_promotion = _parse_promotion(group["is_promotion"].iloc[0]) if "is_promotion" in group.columns else False

        line_items = []
        total_revenue = 0.0
        total_cost = 0.0

        for _, row in group.iterrows():
            pid = str(row["product_id"])
            if pid not in product_map:
                errors.append(f"Product '{pid}' not found")
                continue
            product = product_map[pid]
            try:
                qty = int(row["quantity"])
                price = float(row["unit_price"])
                cost = float(row["unit_cost"]) if "unit_cost" in row and pd.notna(row.get("unit_cost")) else (product.cost or 0.0)
                inventory_level = (
                    int(row["inventory_level"])
                    if "inventory_level" in row and pd.notna(row.get("inventory_level"))
                    else None
                )
            except (TypeError, ValueError):
                errors.append(f"Invalid quantity, price, cost, or inventory for product '{pid}'")
                continue
            if qty <= 0 or price < 0 or cost < 0 or (inventory_level is not None and inventory_level < 0):
                errors.append(f"Quantity, price, cost, and inventory must be valid non-negative values for product '{pid}'")
                continue

            if inventory_level is not None:
                product.stock_on_hand = inventory_level

            total_revenue += qty * price
            total_cost += qty * cost
            line_items.append(
                OrderLineItem(
                    order_id=order_id,
                    user_id=current_user.id,
                    product_id=pid,
                    quantity=qty,
                    unit_price=price,
                    unit_cost=cost,
                    inventory_level=inventory_level,
                )
            )

        if not line_items:
            continue

        db.add(
            Order(
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
                total_profit=round(total_revenue - total_cost, 2),
            )
        )
        db.add_all(line_items)
        orders_created += 1

    db.commit()
    return {"orders_created": orders_created, "errors": errors or None}


class CalendarEntry(BaseModel):
    date: str
    is_closed: Optional[bool] = False
    is_holiday: Optional[bool] = False
    is_festival: Optional[bool] = False
    note: Optional[str] = None


@router.post("/calendar")
def set_calendar(
    entry: CalendarEntry,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(BusinessCalendar)
        .filter(BusinessCalendar.user_id == current_user.id, BusinessCalendar.date == entry.date)
        .first()
    )
    if existing:
        for k, v in entry.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    cal = BusinessCalendar(user_id=current_user.id, **entry.model_dump())
    db.add(cal)
    db.commit()
    db.refresh(cal)
    return cal


@router.get("/calendar")
def get_calendar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(BusinessCalendar)
        .filter(BusinessCalendar.user_id == current_user.id)
        .order_by(BusinessCalendar.date.desc())
        .all()
    )


@router.delete("/calendar/{entry_id}")
def delete_calendar_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(BusinessCalendar)
        .filter(BusinessCalendar.id == entry_id, BusinessCalendar.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Calendar entry not found")
    db.delete(row)
    db.commit()
    return {"message": "Calendar entry deleted"}


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = (
        db.query(Order)
        .filter(Order.order_id == order_id, Order.user_id == current_user.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.query(OrderLineItem).filter(OrderLineItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"message": "Order deleted"}
