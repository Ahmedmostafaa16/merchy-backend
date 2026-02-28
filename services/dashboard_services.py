
from sqlalchemy import func
from models import Inventory, Sales
from sqlalchemy.orm import Session
from .inventory_repo import get_sales_period


class DashboardServices:
    def __init__(self,data_base: Session, shop_id: int):
        self.data_base = data_base
        self.shop_id = shop_id 

    @staticmethod
    def _to_number(value) -> float:
        if value is None:
            return 0.0

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, dict):
            for key in ("days", "total_days", "value"):
                if key in value and isinstance(value[key], (int, float)):
                    return float(value[key])
            return 0.0

        for attr in ("days", "total_days", "value"):
            attr_value = getattr(value, attr, None)
            if isinstance(attr_value, (int, float)):
                return float(attr_value)

        return 0.0
        
    def total_sku_count(self) -> int:
        return self.data_base.query(func.count(Inventory.sku)).filter(Inventory.shop_id == self.shop_id).filter(Inventory.sku.isnot(None)).scalar()
    
    
    def average_sales_per_day(self) -> float:
        total_sales_row = (
            self.data_base.query(func.sum(Sales.quantity_sold))
            .filter(Sales.shop_id == self.shop_id)
            .first()
        )
        total_sales = self._to_number(total_sales_row[0] if total_sales_row else 0)

        total_days_raw = get_sales_period(self.data_base, self.shop_id)
        total_days = self._to_number(total_days_raw)
        if not total_days or total_days == 0:
            return 0.0

        return round(total_sales / total_days, 2)
    
    def coverage_days(self) -> float:
        total_inventory_row = (
            self.data_base.query(func.sum(Inventory.inventory))
            .filter(Inventory.shop_id == self.shop_id)
            .first()
        )
        total_inventory = self._to_number(total_inventory_row[0] if total_inventory_row else 0)

        avg_sales_per_day = self._to_number(self.average_sales_per_day())
        if not avg_sales_per_day or avg_sales_per_day == 0:
            return 0.0

        return round(total_inventory / avg_sales_per_day, 2)
    
    def stock_risk(self) -> float:
        coverage = self._to_number(self.coverage_days())
        if not coverage or coverage == 0:
            return 0.0

        return round((coverage * 60) / 100, 2)
