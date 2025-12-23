# api/routers/products.py

from typing import Optional

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
    # NOTE: removed is_active because DB column does not exist


# ---------- Helpers ----------

def generate_sku(db: Session, name: str) -> str:
    prefix = "".join(ch for ch in name.upper() if ch.isalnum())[:4] or "PRD"
    max_id = db.query(func.coalesce(func.max(Product.id), 0)).scalar() or 0
    counter = max_id + 1
    sku = f"{prefix}{counter:04d}"
    while db.query(Product).filter(Product.sku == sku).first():
        counter += 1
        sku = f"{prefix}{counter:04d}"
    return sku


# ---------- Routes ----------

@router.get("")
def list_products(db: Session = Depends(get_db)):
    """
    List products.
    IMPORTANT: we do NOT filter by is_active because the Render DB table does not have that column.
    """
    rows = db.query(Product).order_by(Product.name.asc()).all()
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "barcode": p.barcode,
            "unit": p.unit,
            "tax_rate": float(p.tax_rate or 0.0),
            "selling_price": float(p.selling_price or 0.0),
        }
        for p in rows
    ]


@router.get("/with_stock")
def products_with_stock(
    location_id: int = Query(1),
    db: Session = Depends(get_db),
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
        .outerjoin(
            StockMove,
            (StockMove.product_id == Product.id) & (StockMove.location_id == location_id),
        )
        # IMPORTANT: removed Product.is_active filter
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
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    incoming_sku = payload.sku.strip().upper() if payload.sku else None
    if not incoming_sku:
        incoming_sku = generate_sku(db, name)

    if db.query(Product).filter(Product.sku == incoming_sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists.")

    # IMPORTANT: do NOT pass is_active because DB column does not exist
    p = Product(
        sku=incoming_sku,
        name=name,
        barcode=payload.barcode,
        unit=payload.unit,
        tax_rate=payload.tax_rate,
        selling_price=payload.selling_price,
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
    }


@router.patch("/{product_id}")
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found.")

    data = payload.dict(exclude_unset=True)

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
    }


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """
    HARD delete (since is_active column doesn't exist).
    If you want soft-delete later, we will add is_active safely with ALTER TABLE.
    """
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found.")
    db.delete(p)
    db.commit()
    return {"status": "ok", "message": "Product deleted."}
