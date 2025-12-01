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


class SaleLineIn(BaseModel):
    sku: str
    qty: float
    unit_price: float


class SaleIn(BaseModel):
    customer_name: str | None = None
    location_id: int = 1
    lines: List[SaleLineIn]


@router.post("")
def create_sale(payload: SaleIn, db: Session = Depends(get_db)):
    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines in sale")

    # Find products and calculate total
    total = 0.0
    product_map: dict[str, Product] = {}

    for line in payload.lines:
        if line.qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be > 0")
        if line.unit_price < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")

        product = db.query(Product).filter_by(sku=line.sku).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Unknown SKU {line.sku}")

        product_map[line.sku] = product
        total += float(line.qty) * float(line.unit_price)

    # Create sale header
    sale = Sale(
        customer_name=payload.customer_name,
        total_amount=total,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)

    # Create sale lines + stock moves
    for line in payload.lines:
        product = product_map[line.sku]
        line_total = float(line.qty) * float(line.unit_price)

        sl = SaleLine(
            sale_id=sale.id,
            product_id=product.id,
            qty=line.qty,
            unit_price=line.unit_price,
            line_total=line_total,
        )
        db.add(sl)

        # Negative stock move for sale
        move = StockMove(
            product_id=product.id,
            lot_id=None,  # later we can do FEFO by lot
            location_id=payload.location_id,
            qty=-float(line.qty),
            unit_cost=None,  # cost vs price we can refine later
            move_type="SALE",
            ref=f"SALE-{sale.id}",
        )
        db.add(move)

    db.commit()
    return {
        "sale_id": sale.id,
        "total": total,
        "lines": len(payload.lines),
    }





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
