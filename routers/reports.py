from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from deps import get_db
from models import Product, StockMove, Lot, Location

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    q = (
        db.query(
            Product.sku,
            Product.name,
            Location.name.label("location"),
            Lot.lot_code,
            Lot.expiry_date,
            func.coalesce(func.sum(StockMove.qty), 0).label("qty"),
        )
        .join(StockMove, StockMove.product_id == Product.id)
        .join(Location, Location.id == StockMove.location_id)
        .outerjoin(Lot, Lot.id == StockMove.lot_id)
        .group_by(Product.sku, Product.name, Location.name, Lot.lot_code, Lot.expiry_date)
        .having(func.coalesce(func.sum(StockMove.qty), 0) != 0)
        .order_by(Product.name, Location.name, Lot.expiry_date.asc().nullslast())
    )

    rows = [
        {
            "sku": r[0],
            "product": r[1],
            "location": r[2],
            "lot": r[3],
            "expiry": r[4].isoformat() if r[4] else None,
            "qty": float(r[5]),
        }
        for r in q.all()
    ]
    return {"items": rows}
