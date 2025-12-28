# routers/sales.py
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from sqlalchemy import func

from deps import get_db
from models import Product, StockMove, Sale, SaleLine

router = APIRouter(prefix="/sales", tags=["sales"])
ALERT_THRESHOLD = 5  # alert when remaining stock <= 5


def get_available_qty(db: Session, product_id: int, location_id: int) -> float:
    q = (
        db.query(func.coalesce(func.sum(StockMove.qty), 0.0))
        .filter(StockMove.product_id == product_id)
        .filter(StockMove.location_id == location_id)
    )
    return float(q.scalar() or 0.0)


class SaleLineIn(BaseModel):
    sku: str
    qty: float
    unit_price: float


class SaleIn(BaseModel):
    customer_name: Optional[str] = None
    location_id: int
    payment_method: Optional[str] = None
    lines: List[SaleLineIn]


@router.post("")
@router.post("/")
def create_sale(payload: SaleIn, db: Session = Depends(get_db)):
    if not payload.location_id:
     raise HTTPException(status_code=400, detail="location_id is required")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines provided")

    try:
        sale = Sale(
            customer_name=payload.customer_name,
            location_id=int(payload.location_id),
            total_amount=0,
        )
        db.add(sale)
        db.flush()  # sale.id exists now

        # ✅ receipt_no: only set if column exists on model
        year = sale.created_at.year if getattr(sale, "created_at", None) else date.today().year
        receipt_no = f"MX-{year}-{sale.id:06d}"
        if hasattr(sale, "receipt_no"):
            sale.receipt_no = receipt_no
            db.flush()
        else:
            receipt_no = None  # local model/db might not have it yet

        total = 0.0
        low_stock = []

        for line in payload.lines:
            product = db.query(Product).filter(Product.sku == line.sku).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product not found: {line.sku}")

            qty = float(line.qty)
            unit_price = float(line.unit_price)

            if qty <= 0:
                raise HTTPException(status_code=400, detail="qty must be > 0")

            available = get_available_qty(db, product.id, int(payload.location_id))
            if qty > available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough stock for {product.name} at location {payload.location_id}. Available: {available}",
                )

            line_total = qty * unit_price
            total += line_total

            db.add(
                SaleLine(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

            db.add(
                StockMove(
                    product_id=product.id,
                    lot_id=None,
                    location_id=int(payload.location_id),
                    qty=-qty,
                    unit_cost=None,
                    move_type="SALE",
                    ref=f"SALE#{sale.id}",
                )
            )

            remaining = available - qty
            if remaining <= ALERT_THRESHOLD:
                low_stock.append({"sku": product.sku, "name": product.name, "remaining": float(remaining)})

        sale.total_amount = total
        db.commit()

        return {
            "sale_id": sale.id,
            "receipt_no": getattr(sale, "receipt_no", None) or receipt_no,
            "total": float(total),
            "low_stock": low_stock,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/history")
def sales_history(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    try:
        start_d = date.fromisoformat(start_date)
        end_d = date.fromisoformat(end_date)
    except ValueError:
        return []

    if end_d < start_d:
        start_d, end_d = end_d, start_d

    rows = (
        db.query(
            Sale.id,
            Sale.created_at,
            Sale.customer_name,
            Sale.location_id,
            Sale.receipt_no,
            func.coalesce(func.sum(SaleLine.line_total), 0).label("total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .filter(func.date(Sale.created_at) >= start_d)
        .filter(func.date(Sale.created_at) <= end_d)
        .group_by(Sale.id, Sale.created_at, Sale.customer_name, Sale.location_id, Sale.receipt_no)
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "customer_name": r.customer_name,
            "location_id": r.location_id,
            "receipt_no": r.receipt_no,
            "total": float(r.total or 0),
        }
        for r in rows
    ]


@router.get("/{sale_id}")
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    lines = (
        db.query(SaleLine, Product.name.label("product_name"), Product.sku.label("sku"))
        .join(Product, Product.id == SaleLine.product_id)
        .filter(SaleLine.sale_id == sale_id)
        .all()
    )

    total = 0.0
    line_list = []
    for line, product_name, sku in lines:
        line_total = float(line.line_total or 0.0)
        total += line_total
        line_list.append(
            {
                "sku": sku,
                "product_name": product_name,
                "qty": float(line.qty or 0.0),
                "unit_price": float(line.unit_price or 0.0),
                "line_total": line_total,
            }
        )

    return {
        "sale": {
            "id": sale.id,
            "created_at": sale.created_at.isoformat() if sale.created_at else None,
            "customer_name": sale.customer_name,
            "location_id": sale.location_id,
            "receipt_no": getattr(sale, "receipt_no", None),
            "total": float(total),
        },
        "lines": line_list,
    }
