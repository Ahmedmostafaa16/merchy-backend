from sqlalchemy import Column, Date, ForeignKey, Numeric, String, Boolean, DateTime,Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from db import Base
import uuid

class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_domain = Column(String, unique=True, nullable=False)
    access_token = Column(String, nullable=False)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    
class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    title = Column(String(200))
    size = Column(String(30))
    color = Column(String, nullable=True)
    sku = Column(String(30), nullable=True)
    inventory = Column(Integer)
    price = Column(Numeric(10, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    
class Sales(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    title = Column(String(200))
    size = Column(String(30))
    color = Column(String, nullable=True)
    sku = Column(String(30), nullable=True)
    quantity_sold = Column(Integer)
    created_at = Column(Date, nullable=False, index=True)
    



