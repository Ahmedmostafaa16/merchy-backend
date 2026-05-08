from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.deps import get_active_shop, get_db
from models import Shop

from services.graphql import fetch_sales_data
from ml.forecast import forecast_all_skus


router = APIRouter(prefix="/ai", tags=["AI"])


class ForecastRequest(BaseModel):
    skus: List[str]


@router.post("/forecast")
def forecast_demand(
    payload: ForecastRequest,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):

    skus = payload.skus

    if not skus:
        return {
            "status": "error",
            "message": "No SKUs provided"
        }

    sales_data = fetch_sales_data(
        shop_domain=shop.shop_domain,
        access_token=shop.access_token,
        skus=skus,
    )

    if not sales_data:
        return {
            "status": "error",
            "message": "No sales data found"
        }

    forecast_results = forecast_all_skus(sales_data)

    return {
        "status": "success",
        "shop": shop.shop_domain,
        "forecast": forecast_results
    }