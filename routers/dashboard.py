from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from core.deps import get_db
from services.dashboard_services import DashboardServices
from models import Shop

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_shop_or_404(db: Session, shop_domain: str) -> Shop:
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.get("/total-skus", status_code=status.HTTP_200_OK)
def get_total_skus(shop_domain: str, db: Session = Depends(get_db)):
    shop = get_shop_or_404(db, shop_domain)
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.total_sku_count()


@router.get("/average-sales-per-day", status_code=status.HTTP_200_OK)
def get_average_sales_per_day(shop_domain: str, db: Session = Depends(get_db)):
    shop = get_shop_or_404(db, shop_domain)
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.average_sales_per_day()


@router.get("/coverage-days", status_code=status.HTTP_200_OK)
def get_coverage_days(shop_domain: str, db: Session = Depends(get_db)):
    shop = get_shop_or_404(db, shop_domain)
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.coverage_days()


@router.get("/stock-risk", status_code=status.HTTP_200_OK)
def get_stock_risk(shop_domain: str, db: Session = Depends(get_db)):
    shop = get_shop_or_404(db, shop_domain)
    dashboard_service = DashboardServices(db, shop.id)
    return dashboard_service.stock_risk()




