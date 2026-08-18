from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.database_models import Product, User
from core.dependencies import get_current_user
from core.logger import get_logger
from pydantic import BaseModel
from typing import Optional, Literal

router = APIRouter()
logger = get_logger(__name__)


class ProductCreate(BaseModel):
    product_id: str
    product_name: str
    category: Optional[str] = None
    base_price: Optional[float] = None
    cost: Optional[float] = None


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    base_price: Optional[float] = None
    cost: Optional[float] = None


class OptimizationObjective(BaseModel):
    objective: Literal["revenue", "profit", "units"]


@router.post("/")
def create_product(product: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(Product).filter(Product.user_id == current_user.id, Product.product_id == product.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Product ID already exists")
    db_product = Product(user_id=current_user.id, **product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/")
def get_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Product).filter(Product.user_id == current_user.id).all()


@router.put("/{product_id}")
def update_product(product_id: str, product: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_product = db.query(Product).filter(Product.user_id == current_user.id, Product.product_id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.model_dump(exclude_none=True).items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_product = db.query(Product).filter(Product.user_id == current_user.id, Product.product_id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return {"message": "Product deleted"}


@router.put("/settings/objective")
def set_objective(payload: OptimizationObjective, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.optimization_objective = payload.objective
    db.commit()
    return {"objective": payload.objective}