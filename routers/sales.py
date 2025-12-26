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

    """
    Create a sale (POST /sales)
    IMPORTANT:
      - sale_line table has NO location_id column
      - stock_move DOES use location_id
    """
    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines provided")

    sale = Sale(
        customer_name=payload.customer_name,
        location_id=int(payload.location_id),
        total_amount=0,
    )
    db.add(sale)
    db.flush()

    
    
    low_stock = []

    for line in payload.lines:
        product = db.query(Product).filter(Product.sku == line.sku).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {line.sku}")

        qty = float(line.qty)
        unit_price = float(line.unit_price)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="qty must be > 0")

        # check stock at the line's location_id
        available = get_available_qty(db, product.id, int(line.location_id))
        if qty > available:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock for {product.name} at location {line.location_id}. Available: {available}",
            )

        line_total = qty * unit_price
        total += line_total

        # ✅ DO NOT include location_id in SaleLine (DB has no such column)
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
            location_id=payload.location_id,  # ✅ from header
            qty=-qty,
            unit_cost=None,
            move_type="SALE",
            ref=f"SALE#{sale.id}",
        )
        db.add(sm)

        remaining = available - qty
        if remaining <= ALERT_THRESHOLD:
            low_stock.append(
                {
                    "sku": product.sku,
                    "name": product.name,
                    "remaining": float(remaining),
                }
            )

    # store total if your Sale table has total_amount (it does)
    sale.total_amount = total

    db.commit()

    return {"sale_id": sale.id, "total": float(total), "low_stock": low_stock}



    


@router.post("/{sale_id}/add_lines")
def add_lines_to_sale(sale_id: int, payload: SaleAddLinesPayload, db: Session = Depends(get_db)):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines provided")

    # If Sale table has no location_id column, payload must send it
    location_id = payload.location_id or getattr(sale, "location_id", None)
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required")

    for ln in payload.lines:
        product = db.query(Product).filter(Product.sku == ln.sku).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product SKU not found: {ln.sku}")

        qty = float(ln.qty)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="qty must be > 0")

        # stock guard
        available = get_available_qty(db, product.id, int(location_id))
        if qty > available:
            raise HTTPException(status_code=400, detail=f"Not enough stock for {ln.sku}. Available: {available}")

        unit_price = float(ln.unit_price)
        line_total = qty * unit_price

        db.add(SaleLine(
            sale_id=sale.id,
            product_id=product.id,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
        ))

        db.add(StockMove(
            product_id=product.id,
            lot_id=None,
            location_id=int(location_id),
            qty=-qty,
            unit_cost=None,
            move_type="SALE_ADJUST",
            ref=f"SALE#{sale.id}",
        ))

    # recompute total
    total_now = (
        db.query(func.coalesce(func.sum(SaleLine.line_total), 0))
        .filter(SaleLine.sale_id == sale.id)
        .scalar()
        or 0
    )
    sale.total_amount = total_now
    db.commit()

    return {"status": "ok", "sale_id": sale.id, "new_total": float(total_now)}







@router.get("/history")
def sales_history(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """
    Returns one row per sale with total computed from SaleLine.line_total.
    Path: /sales/history
    We accept dates as strings and parse them ourselves, to avoid 422 errors.
    """
    # Parse dates safely
    try:
        start_d = date.fromisoformat(start_date)   # "2025-11-01" → date(2025, 11, 1)
        end_d = date.fromisoformat(end_date)
    except ValueError:
        # If the format is wrong, just return empty result instead of throwing 422
        return []

    # Ensure start <= end
    if end_d < start_d:
        start_d, end_d = end_d, start_d

    rows = (
        db.query(
            Sale.id,
            Sale.created_at,
            Sale.customer_name,
            func.coalesce(func.sum(SaleLine.line_total), 0).label("total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .filter(func.date(Sale.created_at) >= start_d)
        .filter(func.date(Sale.created_at) <= end_d)
        .group_by(Sale.id, Sale.created_at, Sale.customer_name)
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "customer_name": r.customer_name,
                "total": float(r.total or 0),
            }
        )
    return result

       


@router.get("/{sale_id}")
def get_sale(
    sale_id: int,
    db: Session = Depends(get_db),
):
    """
    Return a single sale with its line items.
    Shape is designed for the Invoice / Pro Forma page:
    {
      "sale": {...},
      "lines": [...]
    }
    """
    # ---- Load the sale header ----
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # ---- Load line items ----
    lines = (
        db.query(SaleLine, Product.name.label("product_name"))
        .join(Product, Product.id == SaleLine.product_id)
        .filter(SaleLine.sale_id == sale_id)
        .all()
    )

    # Compute total from line totals
    total = 0.0
    line_list = []
    for line, product_name in lines:
        line_total = float(line.line_total or 0.0)
        total += line_total
        line_list.append(
            {
                "product_id": line.product_id,
                "product_name": product_name,
                "qty": float(line.qty or 0.0),
                "unit_price": float(line.unit_price or 0.0),
                "line_total": line_total,
            }
        )

    sale_dict = {
        "id": sale.id,
        "created_at": sale.created_at.isoformat() if sale.created_at else None,
        "customer_name": sale.customer_name,
        "total": total,  # we recompute, ignore total_amount column
    }

    return {
        "sale": sale_dict,
        "lines": line_list,
    }
