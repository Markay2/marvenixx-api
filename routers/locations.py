from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import Location
from deps import get_db

router = APIRouter(prefix="/locations", tags=["locations"])

class LocationIn(BaseModel):
    name: str

@router.get("")
def list_locations(db: Session = Depends(get_db)):
    return db.query(Location).all()

@router.post("")
def add_location(loc: LocationIn, db: Session = Depends(get_db)):
    new = Location(name=loc.name)
    db.add(new)
    db.commit()
    db.refresh(new)
    return new
