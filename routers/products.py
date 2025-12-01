from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import Product
from deps import get_db

router = APIRouter(prefix="/products", tags=["products"])


class ProductIn(BaseModel):
    sku: str
    name: str
    barcode: str | None = None
    unit: str = "unit"
    tax_rate: float = 0.0
    is_perishable: bool = True
    selling_price: float = 0.0 


@router.get("")
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    # Manually convert SQLAlchemy objects to plain dicts
    result = []
    for p in products:
        result.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "barcode": p.barcode,
                "unit": p.unit,
                "tax_rate": float(p.tax_rate) if p.tax_rate is not None else 0.0,
                "is_perishable": bool(p.is_perishable),
                "selling_price": float(p.selling_price) if p.selling_price is not None else 0.0,
            }
        )
    return result


@router.post("")
def create_product(p: ProductIn, db: Session = Depends(get_db)):
    # Prevent duplicate SKU
    existing = db.query(Product).filter_by(sku=p.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    obj = Product(
        sku=p.sku,
        name=p.name,
        barcode=p.barcode,
        unit=p.unit,
        tax_rate=p.tax_rate,
        is_perishable=p.is_perishable,
        selling_price=p.selling_price,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)

    return {
        "id": obj.id,
        "sku": obj.sku,
        "name": obj.name,
        "barcode": obj.barcode,
        "unit": obj.unit,
        "tax_rate": float(obj.tax_rate) if obj.tax_rate is not None else 0.0,
        "is_perishable": bool(obj.is_perishable),
        "selling_price": float(obj.selling_price) if obj.selling_price is not None else 0.0,

    }
