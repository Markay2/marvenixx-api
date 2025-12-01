from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    String,
    Integer,
    Numeric,
    Boolean,
    ForeignKey,
    Date,
    DateTime,
    Float,
    func,
)

from db import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String, unique=False)
    unit: Mapped[str] = mapped_column(String, default="unit", nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    is_perishable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selling_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)




class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Lot(Base):
    __tablename__ = "lot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    lot_code: Mapped[str] = mapped_column(String, nullable=False)
    # 👉 Notice: Python type `date` in the annotation, SQLAlchemy `Date` in the column
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class StockMove(Base):
    __tablename__ = "stock_move"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lot.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)  # +in, -out
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 4))
    move_type: Mapped[str] = mapped_column(String, nullable=False)  # RECEIPT, SALE, etc.
    ref: Mapped[str | None] = mapped_column(String)
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Sale(Base):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class SaleLine(Base):
    __tablename__ = "sale_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sale.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
