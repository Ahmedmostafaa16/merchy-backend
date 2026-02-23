
from sqlalchemy import func
from models import Inventory, Sales
from sqlalchemy.orm import Session
from .inventory_repo import get_sales_time_range


class DashboardServices:
    def __init__(self,data_base: Session, shop_id: int):
        self.data_base = data_base
        self.shop_id = shop_id 
        
    def total_sku_count(self) -> int:
        return self.data_base.query(func.count(Inventory.sku)).filter(Inventory.shop_id == self.shop_id).filter(Inventory.sku.isnot(None)).scalar()
    
    
    def average_sales_per_day(self) -> float:
        total_sales = self.data_base.query(func.sum(Sales.quantity_sold)).filter(Sales.shop_id == self.shop_id).scalar() or 0
        total_days = get_sales_time_range(self.data_base, self.shop_id) or 1  # Avoid division by zero
        return round(total_sales / total_days,2)
    
    def coverage_days(self) -> float:
        total_inventory = self.data_base.query(func.sum(Inventory.inventory)).filter(Inventory.shop_id == self.shop_id).scalar() or 0
        avg_sales_per_day = self.average_sales_per_day() or 1  # Avoid division by zero
        return round(total_inventory / avg_sales_per_day,2)
    
    def stock_risk(self) -> str:
        
        coverage = self.coverage_days() 
        return round((coverage*60)/100,2)  # Stock risk as a percentage