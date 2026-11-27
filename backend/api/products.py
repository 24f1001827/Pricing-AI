from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from core.database import get_db
from core.database_models import Prediction, Product, User
from core.dependencies import get_current_user
from core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ProductCreate(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=200)
    category: Optional[str] = None
    base_price: Optional[float] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    stock_on_hand: Optional[int] = Field(default=0, ge=0)
    lead_time_days: int = Field(default=7, ge=1, le=365)
    service_level: float = Field(default=0.95, ge=0.5, le=0.999)
    holding_cost_per_unit: Optional[float] = Field(default=None, ge=0)
    reorder_cost: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_price_bounds(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot exceed max_price")
        return self


class ProductUpdate(BaseModel):
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = None
    base_price: Optional[float] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    stock_on_hand: Optional[int] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    service_level: Optional[float] = Field(default=None, ge=0.5, le=0.999)
    holding_cost_per_unit: Optional[float] = Field(default=None, ge=0)
    reorder_cost: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_price_bounds(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot exceed max_price")
        return self


class OptimizationObjective(BaseModel):
    objective: Literal["revenue", "profit", "units"]


class RestockRequest(BaseModel):
    quantity: int = Field(gt=0, le=1000000)


class ApplyPriceRequest(BaseModel):
    price: float = Field(gt=0)


@router.post("/")
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(Product)
        .filter(Product.user_id == current_user.id, Product.product_id == product.product_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Product ID already exists")
    db_product = Product(user_id=current_user.id, **product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/")
def get_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Product)
        .filter(Product.user_id == current_user.id)
        .order_by(Product.product_id.asc())
        .all()
    )


@router.get("/inventory-summary")
def get_inventory_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    products = (
        db.query(Product)
        .filter(Product.user_id == current_user.id)
        .order_by(Product.product_id.asc())
        .all()
    )
    latest_pred = (
        db.query(Prediction)
        .filter(Prediction.user_id == current_user.id)
        .order_by(Prediction.created_at.desc())
        .first()
    )
    rec_map = {
        r["product_id"]: r
        for r in (latest_pred.inventory_recommendations or [])
    } if latest_pred else {}

    items = []
    for p in products:
        rec = rec_map.get(p.product_id, {})
        stock = p.stock_on_hand if p.stock_on_hand is not None else 0
        avg_daily = rec.get("avg_daily_demand", 0.0)
        rop = rec.get("reorder_point")
        lead = p.lead_time_days or 7
        days_of_cover = round(stock / avg_daily, 1) if avg_daily and avg_daily > 0 else None

        if rop is not None and avg_daily > 0:
            if stock <= 0 or (days_of_cover is not None and days_of_cover < lead):
                status = "stockout_risk"
            elif stock <= rop:
                status = "reorder_now"
            elif days_of_cover is not None and days_of_cover > max(60.0, lead * 6.0):
                status = "overstock"
            else:
                status = "healthy"
        else:
            status = "unforecasted"

        items.append({
            "product_id": p.product_id,
            "product_name": p.product_name,
            "category": p.category,
            "base_price": p.base_price,
            "cost": p.cost,
            "stock_on_hand": stock,
            "lead_time_days": lead,
            "service_level": p.service_level,
            "avg_daily_demand": avg_daily,
            "safety_stock": rec.get("safety_stock"),
            "reorder_point": rop,
            "days_of_cover": days_of_cover,
            "eoq": rec.get("eoq"),
            "recommended_order_qty": (
                max(rec.get("eoq") or 0, (rop or 0) - stock + int(round(avg_daily * lead)))
                if rop is not None and stock <= rop
                else 0
            ),
            "stock_status": status,
            "base_optimal_price": rec.get("base_optimal_price"),
            "inventory_adjusted_price": rec.get("inventory_adjusted_price"),
            "price_action_note": rec.get("price_action_note"),
        })

    return {
        "has_forecast": bool(latest_pred and latest_pred.inventory_recommendations),
        "training_job_id": latest_pred.training_job_id if latest_pred else None,
        "items": items,
    }


@router.put("/settings/objective")
def set_objective(
    payload: OptimizationObjective,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.optimization_objective = payload.objective
    db.commit()
    return {"objective": payload.objective}


@router.put("/{product_id}")
def update_product(
    product_id: str,
    product: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.user_id == current_user.id, Product.product_id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    updates = product.model_dump(exclude_none=True)
    new_min = updates.get("min_price", db_product.min_price)
    new_max = updates.get("max_price", db_product.max_price)
    if new_min is not None and new_max is not None and new_min > new_max:
        raise HTTPException(status_code=400, detail="min_price cannot exceed max_price")
    for key, value in updates.items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.post("/{product_id}/restock")
def restock_product(
    product_id: str,
    payload: RestockRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.user_id == current_user.id, Product.product_id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.stock_on_hand = (db_product.stock_on_hand or 0) + payload.quantity
    db.commit()
    db.refresh(db_product)
    return db_product


@router.post("/{product_id}/apply-price")
def apply_recommended_price(
    product_id: str,
    payload: ApplyPriceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.user_id == current_user.id, Product.product_id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    if db_product.min_price is not None and payload.price < db_product.min_price:
        raise HTTPException(status_code=400, detail="Price is below configured min_price guardrail")
    if db_product.max_price is not None and payload.price > db_product.max_price:
        raise HTTPException(status_code=400, detail="Price exceeds configured max_price guardrail")
    db_product.base_price = round(payload.price, 2)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.user_id == current_user.id, Product.product_id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return {"message": "Product deleted"}
