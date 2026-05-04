import datetime
from datetime import date, datetime, timedelta, timezone
import io
now = datetime.now(timezone.utc)
import traceback
from dateutil.parser import isoparse
from fastapi import APIRouter, Depends, HTTPException,Query,status, Request
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from models import Inventory, Shop, Sales, Location
from core.auth import ORDERS_SCOPE, PRODUCTS_SCOPE, get_valid_shop
from core.deps import get_active_shop, get_db
from services.shopify import Operations
from services.inventory_repo import get_last_inventory_update,get_sales_time_range,get_sales_period
from services.transformation import forecast_all_items, forecast_items, items_breakdown,csv_maker
from services.search import search_inventory
from services.location_service import get_shop_locations
from typing import Annotated

router = APIRouter(prefix="/requests", tags=["requests"])
report_router = APIRouter(tags=["requests"])


def _no_sales_data_response():
    return {
        "error": "NO_SALES_DATA",
        "message": "No sales data available for the selected period.",
    }


def _shop_has_sales_data(db: Session, shop_id: int, sales_duration: int) -> bool:
    if sales_duration <= 0:
        return False

    total_sales = (
        db.query(func.coalesce(func.sum(Sales.quantity_sold), 0))
        .filter(Sales.shop_id == shop_id)
        .scalar()
    )

    return float(total_sales or 0) > 0




@router.post("/sync/inventory")
def sync_inventory(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
    request: Request = None,
    ):


    # Temporary: inventory guard disabled so existing rows can be refreshed with titles.
    # try:
    #     last_update = get_last_inventory_update(db, shop.id)
    #     if last_update and datetime.now(timezone.utc) - last_update <= timedelta(hours=24):
    #         return {
    #             "status": "skipped",
    #             "reason": "Inventory already available",
    #             "last_updated_at": last_update.isoformat(),
    #         }
    # except Exception:
    #     traceback.print_exc()
    #     db.rollback()
    #     return {"status": "error", "message": "Inventory sync failed"}

    try:
        ops = Operations.from_shop(
            db,
            shop.shop_domain,
            required_scopes=(PRODUCTS_SCOPE,),
            host=request.headers.get("X-Shopify-Host") if request else None,
        )

        inventory_rows = ops.get_inventory() or []

    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Inventory sync failed"}

    if not inventory_rows:
        return {"status": "empty"}

    try:
        ops.delete_inventory(shop.id, db)
        db.bulk_insert_mappings(Inventory, inventory_rows)
        db.commit()

    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Inventory sync failed"}

    return {
        "status": "success",
        "message": f"Inventory synced for shop {shop.shop_domain}",
    }
    
    
@router.post("/sync/sales")
def sync_sales(
    shop: Shop = Depends(get_valid_shop((ORDERS_SCOPE,))),
    db: Session = Depends(get_db),
    request: Request = None,
    start_date: date = Query(...),
    end_date: date = Query(...),
):

    sales_period = get_sales_time_range(db, shop.id)

    if (
        sales_period["min_sales_date"]
        and sales_period["max_sales_date"]
        and sales_period["min_sales_date"] == start_date
        and sales_period["max_sales_date"] == end_date
    ):
        return {
            "status": "skipped",
            "reason": "Sales data already available for the specified period",
            "sales_period": sales_period,
        }

    try:
        ops = Operations.from_shop(
            db,
            shop.shop_domain,
            required_scopes=(ORDERS_SCOPE,),
            host=request.headers.get("X-Shopify-Host") if request else None,
        )

        sales_rows = ops.get_sales(start_date, end_date) or []

    except Exception as exc:
        error_message = str(exc)

        if (
            "ACCESS_DENIED" in error_message
            or "not approved to access the Order object" in error_message
        ):
            return {
                "status": "no_orders_access",
                "message": "Orders access not approved yet",
                "data": [],
            }

        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Sales sync failed"}

    if not sales_rows:
        return {"status": "empty"}

    try:
        ops.delete_sales(shop.id, db)
        db.bulk_insert_mappings(Sales, sales_rows)
        db.commit()

    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Sales sync failed"}

    return {
        "status": "success",
        "message": f"Sales synced for shop {shop.shop_domain} for {start_date} → {end_date}",
    }




        
@router.post("/report", status_code=status.HTTP_200_OK)
def forecast_all(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
    number_of_days: int = Query(..., gt=0),
    minimum_value: int = Query(..., gt=0),
):
    try:
        sales_duration = get_sales_period(db, shop.id)

        if sales_duration <= 0:
            return {"status": "no_sales_duration"}

        if not _shop_has_sales_data(db, shop.id, sales_duration):
            return _no_sales_data_response()

        location_ids = get_shop_locations(db, shop.id)

        if not location_ids:
            location_ids = [
                l[0]
                for l in db.query(Location.id)
                .filter(Location.shop_id == shop.id)
                .all()
            ]

        if not location_ids:
            raise HTTPException(
                status_code=400,
                detail="No locations available for this shop"
            )

        rows = forecast_all_items(
            database=db,
            restock_days=number_of_days,
            sales_duration=sales_duration,
            minimum_value=minimum_value,
            shop_id=shop.id,
            location_ids=location_ids,
        )

        if not rows:
            return {
                "status": "empty",
                "message": "No forecast data generated",
                "debug": {
                    "sales_duration": sales_duration,
                    "locations": location_ids,
                },
            }

        return rows

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Forecast failed")

    

    
  
