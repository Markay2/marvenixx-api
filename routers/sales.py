from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from sqlalchemy import text
from sqlalchemy import func
from deps import get_db
from models import Product, StockMove, Sale, SaleLine



router = APIRouter(prefix="/sales", tags=["sales"])

ALERT_THRESHOLD = 5  # alert when remaining stock <= 5


def get_stock_for_product(db: Session, product_id: int, location_id: int) -> float:
    """
    Returns total available stock for a product at a location
    from the StockMove table.
    """
    qty = (
        db.query(func.coalesce(func.sum(StockMove.qty), 0))
        .filter(StockMove.product_id == product_id)
        .filter(StockMove.location_id == location_id)
        .scalar()
    )
    return float(qty or 0.0)


def get_available_qty(db: Session, product_id: int, location_id: int) -> float:
    """
    Total stock on hand for a given product at a given location.
    Uses StockMove.qty (positive for in, negative for out).
    """
    q = (
        db.query(func.coalesce(func.sum(StockMove.qty), 0.0))
        .filter(StockMove.product_id == product_id)
        .filter(StockMove.location_id == location_id)
    )
    return float(q.scalar() or 0.0)


class SaleAddLine(BaseModel):
    sku: str
    qty: float
    unit_price: float

class SaleAddLinesPayload(BaseModel):
    location_id: Optional[int] = None   # optional override; else use sale header location if you have it
    lines: List[SaleAddLine]

    
class SaleLineIn(BaseModel):
    sku: str
    qty: float
    unit_price: float



class SaleIn(BaseModel):
    customer_name: Optional[str] = None
    location_id: int                  # ✅ sale header location
    payment_method: Optional[str] = None
    lines: List[SaleLineIn]




@router.post("")
def create_sale(payload: SaleIn, db: Session = Depends(get_db)):

    if not payload.location_id:
        raise HTTPException(status_code=400, detail="location_id is required")

    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines provided")

    sale = Sale(
        customer_name=payload.customer_name,
        location_id=int(payload.location_id),  # ✅ required by DB
        total_amount=0,
    )
    db.add(sale)
    db.flush()  # gets sale.id

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

        # ✅ Stock check at SALE HEADER location
        available = get_available_qty(db, product.id, int(payload.location_id))
        if qty > available:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock for {product.name} at location {payload.location_id}. Available: {available}",
            )

        line_total = qty * unit_price
        total += line_total

        # ✅ sale_line has no location_id
        sl = SaleLine(
            sale_id=sale.id,
            product_id=product.id,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
        )
        db.add(sl)

        # ✅ StockMove uses location_id
        sm = StockMove(
            product_id=product.id,
            lot_id=None,
            location_id=int(payload.location_id),
            qty=-qty,
            unit_cost=None,
            move_type="SALE",
            ref=f"SALE#{sale.id}",
        )
        db.add(sm)

        remaining = available - qty
        if remaining <= ALERT_THRESHOLD:
            low_stock.append(
                {"sku": product.sku, "name": product.name, "remaining": float(remaining)}
            )

    sale.total_amount = total
    db.commit()

    return {"sale_id": sale.id, "total": float(total), "low_stock": low_stock}
