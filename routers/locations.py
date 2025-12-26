# routers/locations.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deps import get_db
from models import Location

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationCreate(BaseModel):
    name: str


class LocationUpdate(BaseModel):
    name: Optional[str] = None


@router.get("")
def list_locations(db: Session = Depends(get_db)):
    rows = db.query(Location).order_by(Location.id.asc()).all()
    return [{"id": r.id, "name": r.name} for r in rows]


@router.post("")
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name cannot be empty")

    exists = db.query(Location).filter(Location.name == name).first()
    if exists:
        raise HTTPException(status_code=400, detail="Location already exists")

    loc = Location(name=name)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return {"id": loc.id, "name": loc.name}


@router.patch("/{location_id}")
def update_location(location_id: int, payload: LocationUpdate, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    if payload.name is not None:
        loc.name = payload.name.strip()

    db.commit()
    db.refresh(loc)
    return {"id": loc.id, "name": loc.name}
