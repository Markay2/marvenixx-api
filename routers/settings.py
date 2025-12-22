from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db import get_db
from models import CompanySettings

router = APIRouter(prefix="/settings", tags=["settings"])

def get_or_create_settings(db: Session) -> CompanySettings:
    s = db.query(CompanySettings).first()
    if not s:
        s = CompanySettings()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s



@router.get("/company")
def get_company_settings(db: Session = Depends(get_db)):
    settings = db.query(CompanySettings).first()
    if not settings:
        settings = CompanySettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.post("/company")
def update_company_settings(
    payload: dict,
    db: Session = Depends(get_db)
):
    settings = db.query(CompanySettings).first()
    if not settings:
        settings = CompanySettings()
        db.add(settings)

    for k, v in payload.items():
        if hasattr(settings, k):
            setattr(settings, k, v)

    db.commit()
    db.refresh(settings)
    return settings