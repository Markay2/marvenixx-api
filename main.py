from fastapi import FastAPI
from db import init_db
from routers import (
    health,
    products,
    locations,
    receipts,
    reports,
    sales,
    reports_sales,
    transfers,
    settings,   # ✅ include settings here
)

app = FastAPI(title="Ateasefuor Inventory API")

init_db()

app.include_router(health.router)
app.include_router(products.router)
app.include_router(locations.router)
app.include_router(receipts.router)
app.include_router(reports.router)
app.include_router(sales.router)
app.include_router(reports_sales.router)
app.include_router(transfers.router)
app.include_router(settings.router)   # ✅ include router AFTER app exists
