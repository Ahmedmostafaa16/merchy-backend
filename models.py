from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, Boolean, DateTime, Integer, UniqueConstraint,Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db import Base
import uuid


class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_domain = Column(String, unique=True, nullable=False)
    access_token = Column(String, nullable=False)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token = Column(String, nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    subscription_id = Column(String, nullable=True)        # gid://shopify/AppSubscription/123
    subscription_status = Column(String, nullable=True)    # ACTIVE, PENDING, DECLINED, EXPIRED, FROZEN
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    inventory_items = relationship(
        "Inventory",
        back_populates="shop",
        cascade="all, delete-orphan"
    )

    sales_records = relationship(
        "Sales",
        back_populates="shop",
        cascade="all, delete-orphan"
    )

    notifications = relationship(
        "Notification",
        back_populates="shop",
        cascade="all, delete-orphan"
    )

    purchase_orders = relationship(
        "PurchaseOrder",
        back_populates="shop",
        cascade="all, delete-orphan"
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    variant_id = Column(BigInteger, nullable=False)
    location_id = Column(BigInteger, nullable=False)
    title = Column(String(200))
    variant_title = Column(String(100))  # e.g. "S / Black"
    sku = Column(String(50), nullable=True)
    inventory = Column(Integer, default=0)
    price = Column(Numeric(10, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    shop = relationship("Shop", back_populates="inventory_items")

    __table_args__ = (
        UniqueConstraint("shop_id", "variant_id", "location_id", name="uq_inventory_variant_location"),
        Index("idx_inventory_shop_variant", "shop_id", "variant_id"),
    )


class Sales(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)

    variant_id = Column(BigInteger, nullable=False)

    title = Column(String(200))
    variant_title = Column(String(100))

    sku = Column(String(50), nullable=True)

    quantity_sold = Column(Integer, nullable=False)

    created_at = Column(Date, nullable=False, index=True)

    shop = relationship("Shop", back_populates="sales_records")

    __table_args__ = (
        Index("idx_sales_shop_variant_date", "shop_id", "variant_id", "created_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    shop_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )

    email = Column(String, nullable=False)
    threshold_days = Column(Integer, nullable=False)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    shop = relationship("Shop", back_populates="notifications")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )

    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    currency = Column(String, nullable=False, default="EGP")
    total_cost = Column(Numeric(12, 2), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    shop = relationship("Shop", back_populates="purchase_orders")
    items = relationship(
        "POItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan"
    )


class POItem(Base):
    __tablename__ = "po_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False
    )

    sku = Column(String, nullable=False)
    title = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    total_price = Column(Numeric(12, 2), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    
    
    
class Location(Base):
    __tablename__ = "locations"

    id = Column(BigInteger, primary_key=True)  # Shopify ID
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"))
    name = Column(String(100))
    
    
    
class ShopLocationPreference(Base):
    __tablename__ = "shop_location_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"))
    location_id = Column(BigInteger)
