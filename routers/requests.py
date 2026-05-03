import datetime
from datetime import date, datetime, timedelta, timezone
import io
now = datetime.now(timezone.utc)

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
    import traceback
    from datetime import datetime, timezone, timedelta

    try:
        last_update = get_last_inventory_update(db, shop.id)
        if last_update and datetime.now(timezone.utc) - last_update <= timedelta(hours=12):
            return {
                "status": "skipped",
                "reason": "Inventory already available",
                "last_updated_at": last_update.isoformat()
            }
    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Inventory sync failed"}

    try:
        ops = Operations.from_shop(
            db,
            shop.shop_domain,
            required_scopes=(PRODUCTS_SCOPE,),
            host=request.headers.get("X-Shopify-Host") if request else None,
        )

        rows = ops.get_inventory() or []
    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Inventory sync failed"}

    try:
        if not rows:
            return {"status": "empty", "message": "No inventory data found"}

        inventory_rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            variant_gid = row.get("variant_id")
            location_id = row.get("location_id")

            # 🔥 convert Shopify GID → int
            try:
                variant_id = int(variant_gid.split("/")[-1])
            except Exception:
                continue

            try:
                location_id = int(location_id.split("/")[-1])
            except Exception:
                continue

            try:
                inventory_quantity = int(row.get("inventory") or 0)
            except (TypeError, ValueError):
                inventory_quantity = 0

            inventory_rows.append({
                "shop_id": shop.id,
                "variant_id": variant_id,
                "location_id": location_id,
                "title": (row.get("product_title") or "")[:200],
                "variant_title": (row.get("variant_title") or "")[:100],
                "sku": (row.get("sku") or "")[:50],
                "inventory": inventory_quantity,
                "price": row.get("price"),
            })

        if not inventory_rows:
            return {"status": "empty", "message": "No inventory data found"}

        # 🔥 delete old data (safe for now)
        ops.delete_inventory(shop.id, db)

        # ⚡ bulk insert (fast)
        db.bulk_insert_mappings(Inventory, inventory_rows)
        db.commit()

    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Inventory sync failed"}

    return {
        "status": "success",
        "message": f"Inventory synced for shop {shop.shop_domain}"
    }

@router.post("/sync/sales")
def sync_sales(
    shop: Shop = Depends(get_valid_shop((ORDERS_SCOPE,))),
    db: Session = Depends(get_db),
    request: Request = None,
    start_date: date = Query(...),
    end_date: date = Query(...)
):
    import traceback

    # ✅ Skip if same range already exists
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
            "sales_period": sales_period
        }

    try:
        ops = Operations.from_shop(
            db,
            shop.shop_domain,
            required_scopes=(ORDERS_SCOPE,),
            host=request.headers.get("X-Shopify-Host") if request else None,
        )

        rows = ops.get_sales(start_date, end_date)

    except Exception as exc:
        error_message = str(exc)

        if (
            "ACCESS_DENIED" in error_message
            or "not approved to access the Order object" in error_message
        ):
            return {
                "status": "no_orders_access",
                "message": "Orders access not approved yet",
                "data": []
            }

        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Sales sync failed"}

    try:
        if not rows:
            return {"status": "empty", "message": "No sales data found"}

        sales_rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            variant_gid = row.get("variant_id")

            # 🔥 Convert Shopify GID → int
            try:
                variant_id = int(variant_gid.split("/")[-1])
            except Exception:
                continue

            try:
                quantity = int(row.get("quantity_sold") or 0)
            except (TypeError, ValueError):
                quantity = 0

            created_at = row.get("created_at")
            if not created_at:
                continue

            sales_rows.append({
                "shop_id": shop.id,
                "variant_id": variant_id,
                "title": (row.get("product_title") or "")[:200],
                "variant_title": (row.get("variant_title") or "")[:100],
                "sku": (row.get("sku") or "")[:50],
                "quantity_sold": quantity,
                "created_at": created_at,
            })

        if not sales_rows:
            return {"status": "empty", "message": "No valid sales data"}

        # 🔥 Delete old period (better than full delete)
        ops.delete_sales(shop.id, db)

        # ⚡ Bulk insert
        db.bulk_insert_mappings(Sales, sales_rows)
        db.commit()

    except Exception:
        traceback.print_exc()
        db.rollback()
        return {"status": "error", "message": "Sales sync failed"}

    return {
        "status": "success",
        "message": f"Sales synced for shop {shop.shop_domain} for {start_date} → {end_date}"
    }
        
        
@router.get("/inventory/search", status_code=status.HTTP_200_OK)
def inventory_search(
    search_query: str,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
                                    ):
        if not search_query or len(search_query) < 2:
            return []

        results = search_inventory(
            db,
            shop.id,
            search_query
        )

        return results  # [] if no matches



        
@router.post("/report", status_code=status.HTTP_200_OK)
def forecast_all(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
    number_of_days: int = Query(..., gt=0),
    minimum_value: int = Query(..., gt=0),
):
    try:
        # ✅ Get sales duration
        sales_duration = get_sales_period(db, shop.id)

        if not _shop_has_sales_data(db, shop.id, sales_duration):
            return _no_sales_data_response()

        # ✅ Get user-selected locations
        location_ids = get_shop_locations(db, shop.id)

        # ⚠️ Fallback: if user didn’t select anything → use all locations
        if not location_ids:
            location_ids = db.query(Location.id).filter(
                Location.shop_id == shop.id
            ).all()
            location_ids = [l[0] for l in location_ids]

        # 🚨 Safety check (important)
        if not location_ids:
            raise HTTPException(status_code=400, detail="No locations available for this shop")

        # ✅ Call forecast with location filtering
        rows = forecast_all_items(
            database=db,
            restock_days=number_of_days,
            sales_duration=sales_duration,
            minimum_value=minimum_value,
            shop_id=shop.id,
            location_ids=location_ids   # 🔥 THIS WAS MISSING
        )

        return rows

    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Forecast failed")
        
@router.post("/customized/report", status_code=status.HTTP_200_OK)
def customized_report(
    items: Annotated[list[str], Query(...)],
    number_of_days: int,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),minimum_value: int = Query(..., gt=0),
):
    try:
        # get time range
        time_diff = get_sales_period(db, shop.id)
        if not _shop_has_sales_data(db, shop.id, time_diff):
            return _no_sales_data_response()

        # build forecast
        rows = forecast_items(
                db,
                list(items),
                shop.id,
                number_of_days,
                time_diff,minimum_value
            )
        
        

        return rows

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise
    
    
@router.get("/breakdown", status_code=status.HTTP_200_OK)
def export_items_breakdown(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
    number_of_days: int = Query(..., gt=0),
):
    try:
        sales_duration = get_sales_period(db, shop.id)
        if sales_duration <= 0:
            return []

        breakdown_rows = items_breakdown(
            db,
            shop.id,
            number_of_days,
            sales_duration
        )

        return breakdown_rows

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Breakdown generation failed: {str(e)}"
        )

    
  
