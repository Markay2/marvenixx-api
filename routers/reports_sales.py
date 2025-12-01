# api/routers/reports_sales.py

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from deps import get_db
from models import Sale, SaleLine   # 👈 these match your models.py

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales_summary")
def sales_summary(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Aggregated daily sales between start_date and end_date.

    - If dates are not provided (like the Home page), defaults to last 7 days.
    - Returns keys expected by the Dashboard:
      sales_today, sales_this_month, sales_this_year, daily

    IMPORTANT CHANGE:
    KPIs are calculated based on the SELECTED end_date (To date),
    not the server's own today's date. So your numbers match the
    date range you choose on the dashboard.
    """
    today = date.today()

    # If frontend does not send dates → default to last 7 days
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = end_date - timedelta(days=6)

    # ---- Daily totals between start_date and end_date ----
    daily_rows = (
        db.query(
            func.date(Sale.created_at).label("day"),
            func.coalesce(func.sum(SaleLine.line_total), 0).label("total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .filter(func.date(Sale.created_at) >= start_date)
        .filter(func.date(Sale.created_at) <= end_date)
        .group_by(func.date(Sale.created_at))
        .order_by(func.date(Sale.created_at))
        .all()
    )

    daily = []
    for d, total in daily_rows:
        daily.append({"date": d.isoformat(), "total": float(total or 0)})

    # ---------- KPIs ----------
    # Use the selected end_date (the "To date" from the dashboard)
    ref = end_date
    ref_str = ref.isoformat()

    # "Sales Today" = sales on the selected To date
    today_total = sum(row["total"] for row in daily if row["date"] == ref_str)

    # "Sales This Month" = same year & month as selected To date
    ref_ym = ref_str[:7]  # "YYYY-MM"
    this_month_total = sum(
        row["total"]
        for row in daily
        if row["date"][:7] == ref_ym
    )

    # "Sales This Year" = same year as selected To date
    ref_y = ref_str[:4]  # "YYYY"
    this_year_total = sum(
        row["total"]
        for row in daily
        if row["date"][:4] == ref_y
    )

    # Keys match what your Streamlit dashboard expects
    return {
        "sales_today": today_total,
        "sales_this_month": this_month_total,
        "sales_this_year": this_year_total,
        "daily": daily,
    }


@router.get("/sales/history")
def sales_history(
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int = Query(500, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """
    Returns one row per sale, with TRUE total computed from SaleLine.line_total.
    Used by the Sales History page.
    """
    rows = (
        db.query(
            Sale.id,
            Sale.created_at,
            Sale.customer_name,
            func.coalesce(func.sum(SaleLine.line_total), 0).label("total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .filter(func.date(Sale.created_at) >= start_date)
        .filter(func.date(Sale.created_at) <= end_date)
        .group_by(Sale.id)
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
                "location_id": None,          # you don't have this on Sale
                "total": float(r.total or 0), # real total from lines
            }
        )
    return result
