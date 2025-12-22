# api/routers/products.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from deps import get_db
from models import Product, StockMove

router = APIRouter(prefix="/products", tags=["products"])


# ---------- Pydantic Schemas ----------

class ProductCreate(BaseModel):
    sku: Optional[str] = None
    name: str
    barcode: Optional[str] = None
    unit: str = "piece"
    tax_rate: float = 0.0
    selling_price: float = 0.0


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    barcode: Optional[str] = None
    unit: Optional[str] = None
    tax_rate: Optional[float] = None
    selling_price: Optional[float] = None
    is_active: Optional[bool] = None


# ---------- Helpers ----------

def generate_sku(db: Session, name: str) -> str:
    """
    Generate a simple SKU like RICE0001, RICE0002, etc.
    Uses product name prefix + next numeric counter.
    """
    prefix = "".join(ch for ch in name.upper() if ch.isalnum())[:4] or "PRD"

    # get max id and use as counter
    max_id = db.query(func.coalesce(func.max(Product.id), 0)).scalar() or 0
    counter = max_id + 1

    sku = f"{prefix}{counter:04d}"

    # ensure uniqueness (very unlikely we loop many times)
    while db.query(Product).filter(Product.sku == sku).first():
        counter += 1
        sku = f"{prefix}{counter:04d}"

    return sku


def get_available_stock(db: Session, product_id: int) -> float:
    """
    Net stock across ALL locations, used for /products/with_stock.
    POS uses this to show 'Available: xx unit'.
    """
    qty = (
        db.query(func.coalesce(func.sum(StockMove.qty), 0.0))
        .filter(StockMove.product_id == product_id)
        .scalar()
        or 0.0
    )
    return float(qty)


# ---------- Routes ----------

@router.get("")
def list_products(db: Session = Depends(get_db)):
    """
    List all ACTIVE products (is_active = true).
    """
    rows = (
        db.query(Product)
        .filter(Product.is_active == True)  # noqa: E712
        .order_by(Product.name.asc())
        .all()
    )
    result = []
    for p in rows:
        result.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "barcode": p.barcode,
                "unit": p.unit,
                "tax_rate": float(p.tax_rate or 0.0),
                "selling_price": float(p.selling_price or 0.0),
                "is_active": bool(p.is_active),
            }
        )
    return result



@router.get("/with_stock")
def products_with_stock(
    location_id: int = Query(1),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Product.selling_price,
            Product.tax_rate,
            func.coalesce(func.sum(StockMove.qty), 0).label("available_qty"),
        )
        .outerjoin(StockMove, (StockMove.product_id == Product.id) & (StockMove.location_id == location_id))
        .filter(Product.is_active == True)
        .group_by(Product.id)
        .order_by(Product.name.asc())
        .all()
    )

    return [
        {
            "id": r.id,
            "sku": r.sku,
            "name": r.name,
            "unit": r.unit,
            "selling_price": float(r.selling_price or 0),
            "tax_rate": float(r.tax_rate or 0),
            "available_qty": float(r.available_qty or 0),
        }
        for r in rows
    ]



@router.post("")
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a new product.
    If SKU is empty, we auto-generate one from the name.
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    incoming_sku = payload.sku.strip().upper() if payload.sku else None
    if not incoming_sku:
        incoming_sku = generate_sku(db, name)

    # ensure uniqueness if user provided SKU
    if db.query(Product).filter(Product.sku == incoming_sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists.")

    p = Product(
        sku=incoming_sku,
        name=name,
        barcode=payload.barcode,
        unit=payload.unit,
        tax_rate=payload.tax_rate,
        selling_price=payload.selling_price,
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)

    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "barcode": p.barcode,
        "unit": p.unit,
        "tax_rate": float(p.tax_rate or 0.0),
        "selling_price": float(p.selling_price or 0.0),
        "is_active": bool(p.is_active),
    }


@router.patch("/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
):
    """
    Update product fields (name, unit, selling_price, tax_rate, barcode, is_active).
    Used by admin edit form.
    """
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found.")

    data = payload.dict(exclude_unset=True)

    # Don't allow editing SKU here to keep it stable
    if "name" in data and data["name"]:
        p.name = data["name"].strip()
    if "barcode" in data:
        p.barcode = data["barcode"]
    if "unit" in data and data["unit"]:
        p.unit = data["unit"]
    if "tax_rate" in data and data["tax_rate"] is not None:
        p.tax_rate = data["tax_rate"]
    if "selling_price" in data and data["selling_price"] is not None:
        p.selling_price = data["selling_price"]
    if "is_active" in data and data["is_active"] is not None:
        p.is_active = data["is_active"]

    db.commit()
    db.refresh(p)

    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "barcode": p.barcode,
        "unit": p.unit,
        "tax_rate": float(p.tax_rate or 0.0),
        "selling_price": float(p.selling_price or 0.0),
        "is_active": bool(p.is_active),
    }


@router.delete("/{product_id}")
def deactivate_product(product_id: int, db: Session = Depends(get_db)):
    """
    Soft-delete: mark product as inactive.
    POS and Receive Stock will NOT show it anymore,
    but your past sales history is preserved.
    """
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found.")

    p.is_active = False
    db.commit()
    return {"status": "ok", "message": "Product deactivated."}
