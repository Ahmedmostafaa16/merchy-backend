from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from core.deps import get_active_shop, get_db
from services.dashboard_services import DashboardServices
from models import Shop

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/total-skus", status_code=status.HTTP_200_OK)
def get_total_skus(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.total_sku_count()


@router.get("/average-sales-per-day", status_code=status.HTTP_200_OK)
def get_average_sales_per_day(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.average_sales_per_day()


@router.get("/coverage-days", status_code=status.HTTP_200_OK)
def get_coverage_days(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.coverage_days()


@router.get("/stock-risk", status_code=status.HTTP_200_OK)
def get_stock_risk(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.stock_risk()

@router.get("/inventory-value", status_code=status.HTTP_200_OK)
def get_inventory_value(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.inventory_value()

@router.get("/units-in-stock", status_code=status.HTTP_200_OK)
def get_units_in_stock(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.units_in_stock()


