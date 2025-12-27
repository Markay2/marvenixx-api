from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    String, Integer, Numeric, Text, Boolean, ForeignKey, Date, DateTime, Float, func
)
from db import Base




class Product(Base):
    __tablename__ = "product"   # ✅ MUST be "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str] = mapped_column(String, default="piece", nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    is_perishable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selling_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # ✅ KEEP IT


class Location(Base):
    __tablename__ = "location"  # ✅ MUST be "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Lot(Base):
    __tablename__ = "lot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)  # ✅ product.id
    lot_code: Mapped[str] = mapped_column(String, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class StockMove(Base):
    __tablename__ = "stock_move"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)  # ✅ product.id
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lot.id"), nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)  # ✅ location.id
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    move_type: Mapped[str] = mapped_column(String, nullable=False)
    ref: Mapped[str | None] = mapped_column(String, nullable=True)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sale(Base):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)

    receipt_no: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ✅ ADD THIS

    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)    




class SaleLine(Base):
    __tablename__ = "sale_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sale.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)

    # ✅ NO location_id HERE (your DB sale_line has no column)
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)



class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    company_name: Mapped[str] = mapped_column(String, nullable=False, default="Marvenixx")
    address: Mapped[str] = mapped_column(String, nullable=False, default="")
    phone: Mapped[str] = mapped_column(String, nullable=False, default="")
    website: Mapped[str] = mapped_column(String, nullable=False, default="")
    footer: Mapped[str] = mapped_column(String, nullable=False, default="")
    logo_base64: Mapped[str] = mapped_column(String, nullable=False, default="")

    currency_symbol: Mapped[str] = mapped_column(String, nullable=False, default="₵")

    # Optional extra columns you added in DB
    receipt_footer: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

