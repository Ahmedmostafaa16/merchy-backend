import datetime
from datetime import date, datetime, timedelta, timezone
import io
now = datetime.now(timezone.utc)

from fastapi import APIRouter, Depends, Request, HTTPException,Query,status
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from models import Inventory, Shop, Sales
from core.deps import get_db
from services.shopify import Operations
from services.inventory_repo import get_last_inventory_update,get_sales_time_range,get_sales_period
from services.transformation import forecast_all_items, forecast_items, items_breakdown,csv_maker
from services.search import search_inventory
from typing import Annotated

router = APIRouter(prefix="/requests", tags=["requests"])




@router.post("/sync/inventory/{shop_domain}")
def sync_inventory(shop_domain: str, db: Session = Depends(get_db)):

    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    last_update = get_last_inventory_update(db, shop.id) 
    if last_update and datetime.now(timezone.utc) - last_update <= timedelta(hours=12):
        return {
        "status": "skipped",
        "reason": "Inventory already available",
        "last_updated_at": last_update.isoformat()
    }
    try :     
        ops = Operations(shop.shop_domain, shop.access_token)
        
        ops.delete_inventory(shop.id,db)
        
        rows = ops.get_inventory() 
        inventory_rows = [{"shop_id": shop.id, **row} for row in rows]
        db.bulk_insert_mappings(Inventory, inventory_rows)
        db.commit()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


    return {"status": "success", "message": f"Inventory synced for shop {shop.shop_domain}"} 

@router.post("/sync/sales/{shop_domain}") 

def sync_sales(shop_domain: str, 
               db: Session = Depends(get_db),
               start_date: date = Query(...), 
               end_date: date = Query(...)):
     
        shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        sales_period = get_sales_time_range(db, shop.id)
        if sales_period["min_sales_date"] == start_date and sales_period["max_sales_date"] == end_date:
            return {
                "status": "skipped",
                "reason": "Sales data already available for the specified period",
                "sales_period": sales_period
            }
            
        ops = Operations(shop.shop_domain, shop.access_token)
        ops.delete_sales(shop.id,db)
        rows = ops.get_sales(start_date, end_date)
        sales_rows = [{"shop_id": shop.id, **row} for row in rows]
        db.bulk_insert_mappings(Sales, sales_rows)
        db.commit()
        return {"status": "success", "message": f"Sales synced for shop {shop.shop_domain} for the period {start_date} to {end_date}"}
        
        
@router.get("/inventory/search", status_code=status.HTTP_200_OK)
def inventory_search(
    shop_domain: str,
    search_query: str,
    db: Session = Depends(get_db) 
                                    ):
    
        shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        if not search_query or len(search_query) < 2:
            return []

        results = search_inventory(
            db,
            shop.id,
            search_query
        )

        return results  # [] if no matches



        
@router.post("/report",status_code  =status.HTTP_200_OK)

def forecast_all(shop_domain : str, db: Session = Depends(get_db), number_of_days : int = Query(..., gt=0)):
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop:
        raise HTTPException(
            status_code=404,
            detail="shop not found"
        )
        
    try :
        
        time_diff = get_sales_period(db,shop.id) 
        csv = csv_maker(forecast_all_items(db,number_of_days,time_diff,shop.id))
        buffer = io.StringIO(csv)
        return StreamingResponse(
            buffer,media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=restock_report.csv"}) 
    except Exception as e :
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )
        
        
@router.post("/customized/report", status_code=status.HTTP_200_OK)
def customized_report(
    items: Annotated[list[str], Query(...)],
    number_of_days: int,
    shop_domain: str,
    db: Session = Depends(get_db),
):
    try:
        # get shop id from domain
        shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        # get time range
        time_diff = get_sales_period(db, shop.id)

        # build forecast
        csv_text = csv_maker(
            forecast_items(
                db,
                list(items),
                shop.id,
                number_of_days,
                time_diff
            )
        )

        buffer = io.StringIO(csv_text)

        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=customized_restock_report.csv"
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )
    
    
@router.get("/breakdown", status_code=status.HTTP_200_OK)
def export_items_breakdown(
    shop_domain : str,
    db: Session = Depends(get_db),
    number_of_days: int = Query(..., gt=0),
):
    
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Shop not found"
        )

    try:
        sales_duration = get_sales_period(db, shop.id)

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

    
  