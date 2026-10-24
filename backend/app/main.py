from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import (
    engine,
    Base,
    SessionLocal,
    CustomerSessionLocal,
    UserSessionLocal,
    customer_engine,
    user_engine,
    get_db,
    migrate_customer_user_data,
)
from .services.seed import seed_database_if_empty
from .services.auth import ensure_initial_admin
from .models import Customer, CustomerPurchase, UserPurchase
from .routers import (
    dashboard,
    products,
    inventory,
    sales,
    forecasts,
    forecast_accuracy,
    reorder,
    purchase_orders,
    imports,
    reports,
    auth,
    users,
    audit,
    backup,
    rural,
    sync,
    customer_user_db,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    print("[Startup] Initializing SQLite database schema...")
    separate_tables = {Customer.__table__, CustomerPurchase.__table__, UserPurchase.__table__}
    core_tables = [table for table in Base.metadata.sorted_tables if table not in separate_tables]
    Base.metadata.create_all(bind=engine, tables=core_tables)
    Base.metadata.create_all(bind=customer_engine, tables=[Customer.__table__, CustomerPurchase.__table__])
    Base.metadata.create_all(bind=user_engine, tables=[UserPurchase.__table__])
    migrate_customer_user_data()

    # Seed with authentic retail sales data if empty
    db = SessionLocal()
    customer_db = CustomerSessionLocal()
    user_db = UserSessionLocal()
    try:
        seed_database_if_empty(db, force=False)
        ensure_initial_admin(db)
        customer_user_db.ensure_seed_data(db, customer_db, user_db)
    finally:
        db.close()
        customer_db.close()
        user_db.close()

    yield
    print("[Shutdown] Cleaning up...")

app = FastAPI(
    title="StockSense API — Small-Retail Reorder Planner",
    description="Backend API for retail inventory analytics, deterministic reorder planning, rural kirana data collection, and secure administrator management.",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": "StockSense Retail Analytics & Rural Management",
        "version": "2.0.0",
        "engine": "FastAPI + SQLite WAL",
        "forecasting": "14-Day MA Baseline & Random Forest Holdout Evaluation",
        "modules": [
            "Rural Kirana Data Collection",
            "Offline Idempotent Sync",
            "Secure Role-Based Admin Panel",
            "Automated Database Backups"
        ]
    }

# Reset Demo Database Endpoint
@app.post("/api/settings/reset-demo")
def reset_demo_database(db: Session = Depends(get_db)):
    seed_database_if_empty(db, force=True)
    ensure_initial_admin(db)
    return {"status": "success", "message": "SQLite database restored to initial Excel demo state."}

# Register all Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(backup.router)
app.include_router(rural.router)
app.include_router(sync.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(forecasts.router)
app.include_router(forecast_accuracy.router)
app.include_router(reorder.router)
app.include_router(purchase_orders.router)
app.include_router(imports.router)
app.include_router(reports.router)
app.include_router(customer_user_db.router, prefix="/api/database")
app.include_router(customer_user_db.router, prefix="/api/customer-user-db")

# --- Mount Frontend Single-Page App (SPA) ---
# Unifies Frontend and Backend onto a single server and port
DIST_DIR = Path(__file__).resolve().parent.parent.parent / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str):
        if (
            full_path.startswith("api/")
            or full_path == "api"
            or full_path.startswith("docs")
            or full_path.startswith("openapi.json")
        ):
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = DIST_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
