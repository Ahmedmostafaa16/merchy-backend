
from sqlalchemy import func
from models import Inventory, Sales
from sqlalchemy.orm import Session


def get_last_inventory_update(data_base : Session, shop_id: int):
    return (
        data_base.query(func.max(Inventory.created_at))
        .filter(Inventory.shop_id == shop_id)
        .scalar()
    
    )
    
def get_sales_time_range(database: Session, shop_id: int):
    result = (
        database.query(
            func.min(Sales.created_at),
            func.max(Sales.created_at)
        )
        .filter(Sales.shop_id == shop_id)
        .first()
    )

    first_sale, last_sale = result

    return {
        "min_sales_date": first_sale if first_sale else None,
        "max_sales_date": last_sale if last_sale else None
    }
def get_sales_period(data_base : Session, shop_id: int):
    last_sale = (
        data_base.query(func.max(Sales.created_at))
        .filter(Sales.shop_id == shop_id)
        .scalar()
    )
    first_sale = (
        data_base.query(func.min(Sales.created_at))
        .filter(Sales.shop_id == shop_id)
        .scalar()
    )
    if first_sale is None or last_sale is None:
        return 0
    dif = last_sale - first_sale
    return dif.days if dif else 0
