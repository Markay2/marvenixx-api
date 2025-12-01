from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session
from models import Product, Lot, StockMove
from deps import get_db

router = APIRouter(prefix="/receipts", tags=["receipts"])

class ReceiptLine(BaseModel):
    product_sku: str
    qty: float
    unit_cost: float
    lot_code: str | None = None
    expiry_date: date | None = None
    to_location_id: int = 1  # default location

class ReceiptIn(BaseModel):
    supplier: str | None = None
    lines: list[ReceiptLine]

@router.post("")
def post_receipt(payload: ReceiptIn, db: Session = Depends(get_db)):
    created = 0
    for line in payload.lines:
        product = db.query(Product).filter_by(sku=line.product_sku).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Unknown product SKU {line.product_sku}")

        lot_id = None
        if line.lot_code:
            # find or create lot
            lot = db.query(Lot).filter_by(product_id=product.id, lot_code=line.lot_code).first()
            if not lot:
                lot = Lot(product_id=product.id, lot_code=line.lot_code, expiry_date=line.expiry_date)
                db.add(lot)
                db.commit()
                db.refresh(lot)
            lot_id = lot.id

        move = StockMove(
            product_id=product.id,
            lot_id=lot_id,
            location_id=line.to_location_id,
            qty=line.qty,
            unit_cost=line.unit_cost,
            move_type="RECEIPT",
            ref="GRN"
        )
        db.add(move)
        created += 1

    db.commit()
    return {"status": "ok", "lines": created}
