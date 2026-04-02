from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, conint, condecimal
from typing import List, Optional
from uuid import UUID


class POItemCreate(BaseModel):
    sku: str
    title: str
    quantity: conint (gt=0)
    unit_price: condecimal(ge=0, max_digits=12, decimal_places=2) 


class POCreate(BaseModel):
    supplier_name: str
    status: str = "draft"
    due_date: Optional[datetime] = None
    currency: str = "EGP"
    items: List[POItemCreate]


class POStatusUpdate(BaseModel):
    status: str


class POItemResponse(BaseModel):
    id: UUID
    sku: str
    title: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal

    class Config:
        from_attributes = True


class POResponse(BaseModel):
    id: UUID
    supplier_name: str
    status: str
    currency: str
    total_cost: Decimal
    created_at: datetime
    due_date: Optional[datetime]
    items: List[POItemResponse]

    class Config:
        from_attributes = True