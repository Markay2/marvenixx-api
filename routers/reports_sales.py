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
    """
    today = date.today()

    # If frontend does not send dates → default to last 7 days
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = end_date - timedelta(days=6)

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

    # ---- KPIs from the daily list ----
    today_str = today.isoformat()

    today_total = sum(row["total"] for row in daily if row["date"] == today_str)
    this_month_total = sum(
        row["total"]
        for row in daily
        if row["date"][:7] == today_str[:7]  # YYYY-MM
    )
    this_year_total = sum(
        row["total"]
        for row in daily
        if row["date"][:4] == today_str[:4]  # YYYY
    )

    # IMPORTANT: keys now match what Streamlit expects
    return {
        "sales_today": today_total,
        "sales_this_month": this_month_total,
        "sales_this_year": this_year_total,
        "daily": daily,
    }
