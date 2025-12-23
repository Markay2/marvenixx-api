import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db(Base):
    from models import Product, Location, Lot, StockMove, Sale, SaleLine

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    

    if os.getenv("ENV", "prod") == "dev":
        Base.metadata.create_all(bind=engine)

    # Seed a default location if none exists
    db = SessionLocal()
    try:
        has_loc = db.query(Location).count()
        if has_loc == 0:
            main = Location(name="Main Store")
            db.add(main)
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
