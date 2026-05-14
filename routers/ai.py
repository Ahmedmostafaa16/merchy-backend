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

    print(
        "[forecast-debug][router] forecast request",
        {
            "shop": shop.shop_domain,
            "sku_count": len(skus),
            "skus": skus,
        },
    )

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

    print(
        "[forecast-debug][router] sales_data received",
        {
            "sku_count": len(sales_data),
            "shape": {
                sku: {
                    "date_count": len(date_quantities),
                    "total_qty": sum(date_quantities.values()),
                    "first_date": min(date_quantities) if date_quantities else None,
                    "last_date": max(date_quantities) if date_quantities else None,
                }
                for sku, date_quantities in sales_data.items()
            },
        },
    )

    if not sales_data:
        return {
            "status": "error",
            "message": "No sales data found"
        }

    forecast_results = forecast_all_skus(sales_data)

    print(
        "[forecast-debug][router] forecast_results",
        {
            "sku_count": len(forecast_results),
            "payload": forecast_results,
            "contains_daily_series": {
                sku: any(
                    key in result
                    for key in ("series", "forecast_series", "daily_forecast", "points")
                )
                for sku, result in forecast_results.items()
                if isinstance(result, dict)
            },
        },
    )

    return {
        "status": "success",
        "shop": shop.shop_domain,
        "forecast": forecast_results
    }
