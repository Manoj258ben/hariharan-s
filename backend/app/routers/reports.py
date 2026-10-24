from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.reports import (
    export_inventory_csv,
    export_reorder_csv,
    export_full_excel_report,
    export_forecast_accuracy_excel
)
from ..services.reorder import get_all_reorder_recommendations
from ..services.forecasting import get_product_daily_sales_series, backtest_product_models
from ..services.accuracy import calculate_portfolio_metrics
from ..models import Product
from ..config import DEFAULT_AS_OF_DATE
import io
import csv

router = APIRouter(prefix="/api/reports", tags=["Reports & Export"])

@router.get("/inventory.csv")
def download_inventory_csv(db: Session = Depends(get_db)):
    content = export_inventory_csv(db)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Inventory_{DEFAULT_AS_OF_DATE}.csv"}
    )


@router.get("/inventory.xlsx")
def download_inventory_xlsx(as_of_date: str = DEFAULT_AS_OF_DATE, db: Session = Depends(get_db)):
    excel_bytes = export_full_excel_report(db, as_of_date=as_of_date)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Inventory_{as_of_date}.xlsx"}
    )


@router.get("/reorder.csv")
def download_reorder_csv(as_of_date: str = DEFAULT_AS_OF_DATE, db: Session = Depends(get_db)):
    content = export_reorder_csv(db, as_of_date=as_of_date)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Reorder_Plan_{as_of_date}.csv"}
    )


@router.get("/reorder.xlsx")
def download_reorder_xlsx(as_of_date: str = DEFAULT_AS_OF_DATE, db: Session = Depends(get_db)):
    excel_bytes = export_full_excel_report(db, as_of_date=as_of_date)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Master_Report_{as_of_date}.xlsx"}
    )


@router.get("/forecast-accuracy.csv")
def download_accuracy_csv(as_of_date: str = DEFAULT_AS_OF_DATE, db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_archived == False).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Product ID", "Product Name", "Category", "Evaluation Observations",
        "Total Actual Units", "Baseline MAE", "Baseline WAPE (%)", "Winning Model"
    ])

    for p in products:
        series = get_product_daily_sales_series(db, p.product_id, as_of_date=as_of_date, days_back=90)
        bt = backtest_product_models(series, holdout_days=14)
        if bt:
            writer.writerow([
                p.product_id, p.product_name, p.category, bt["n_observations"],
                sum(bt["actuals"]), bt["baseline_mae"], bt["baseline_wape"] or "N/A", bt["winning_model"]
            ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Forecast_Accuracy_{as_of_date}.csv"}
    )


@router.get("/forecast-accuracy.xlsx")
def download_accuracy_xlsx(as_of_date: str = DEFAULT_AS_OF_DATE, db: Session = Depends(get_db)):
    excel_bytes = export_forecast_accuracy_excel(db, as_of_date=as_of_date)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=StockSense_Forecast_Accuracy_{as_of_date}.xlsx"}
    )
