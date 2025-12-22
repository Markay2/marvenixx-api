# api/routers/stock_transfer.py

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from deps import get_db
from models import Product, StockMove, Location  # Location is optional but nice for messages

router = APIRouter(tags=["stock_transfer"])


class TransferLineIn(BaseModel):
    product_sku: str
    qty: float


class StockTransferIn(BaseModel):
    from_location_id: int
    to_location_id: int
    lines: List[TransferLineIn]


def get_available_stock(
    db: Session,
    product_id: int,
    location_id: int,
) -> float:
    """
    Net stock at a given location = sum of all StockMove.qty there.
    Positive = stock in, negative = stock out.
    """
    qty = (
        db.query(func.coalesce(func.sum(StockMove.qty), 0.0))
        .filter(
            StockMove.product_id == product_id,
            StockMove.location_id == location_id,
        )
        .scalar()
        or 0.0
    )
    return float(qty)


@router.post("/stock_transfer")
def create_stock_transfer(payload: StockTransferIn, db: Session = Depends(get_db)):
    # 1. Basic checks
    if payload.from_location_id == payload.to_location_id:
        raise HTTPException(
            status_code=400,
            detail="From and To locations must be different.",
        )

    if not payload.lines:
        raise HTTPException(status_code=400, detail="No lines in transfer.")

    # Optional: load locations for nicer error messages
    from_loc = db.query(Location).filter(Location.id == payload.from_location_id).first()
    to_loc = db.query(Location).filter(Location.id == payload.to_location_id).first()

    if not from_loc or not to_loc:
        raise HTTPException(status_code=400, detail="Invalid location ID(s).")

    # 2. Resolve SKUs → products and validate stock
    sku_to_product = {}

    for line in payload.lines:
        if line.qty <= 0:
            raise HTTPException(
                status_code=400,
                detail="All quantities must be > 0.",
            )

        product = db.query(Product).filter(Product.sku == line.product_sku).first()
        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown SKU: {line.product_sku}",
            )

        sku_to_product[line.product_sku] = product

        # 🧮 check available stock at FROM location
        available = get_available_stock(
            db=db,
            product_id=product.id,
            location_id=payload.from_location_id,
        )

        if float(line.qty) > available:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Not enough stock for {product.name} (SKU {product.sku}) at "
                    f"{from_loc.name}. Available: {available:.2f}, "
                    f"requested: {float(line.qty):.2f}"
                ),
            )

    # 3. If all lines are valid → create stock moves
    ref = f"TRANSFER-{payload.from_location_id}->{payload.to_location_id}"

    for line in payload.lines:
        product = sku_to_product[line.product_sku]
        qty = float(line.qty)

        # OUT from FROM location
        move_out = StockMove(
            product_id=product.id,
            lot_id=None,
            location_id=payload.from_location_id,
            qty=-qty,
            unit_cost=None,  # optional: later we can track cost
            move_type="TRANSFER_OUT",
            ref=ref,
        )
        db.add(move_out)

        # IN to TO location
        move_in = StockMove(
            product_id=product.id,
            lot_id=None,
            location_id=payload.to_location_id,
            qty=qty,
            unit_cost=None,
            move_type="TRANSFER_IN",
            ref=ref,
        )
        db.add(move_in)

    db.commit()

    # 4. Build a friendly response with remaining stock at FROM location
    result_lines = []
    for line in payload.lines:
        product = sku_to_product[line.product_sku]
        remaining = get_available_stock(
            db=db,
            product_id=product.id,
            location_id=payload.from_location_id,
        )
        result_lines.append(
            {
                "sku": product.sku,
                "name": product.name,
                "qty_transferred": float(line.qty),
                "remaining_at_from_location": remaining,
            }
        )

    return {
        "status": "ok",
        "from_location": from_loc.name,
        "to_location": to_loc.name,
        "lines": result_lines,
    }
