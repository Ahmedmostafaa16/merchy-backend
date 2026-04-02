from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from models import PurchaseOrder, POItem
from models import Shop


ALLOWED_PO_STATUSES = {"draft", "confirmed", "ordered", "delivered"}


def get_shop_by_domain(db: Session, shop_domain: str) -> Shop:
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


def create_po(db: Session, shop_domain: str, payload):
    shop = get_shop_by_domain(db, shop_domain)

    if payload.status not in ALLOWED_PO_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid PO status")

    if not payload.items:
        raise HTTPException(status_code=400, detail="PO must contain at least one item")

    po = PurchaseOrder(
        shop_id=shop.id,
        supplier_name=payload.supplier_name,
        status=payload.status,
        due_date=payload.due_date,
        currency=payload.currency,
        total_cost=Decimal("0.00"),
    )

    total_cost = Decimal("0.00")
    items = []

    for item in payload.items:
        line_total = Decimal(item.quantity) * item.unit_price
        total_cost += line_total

        items.append(
            POItem(
                sku=item.sku,
                title=item.title,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=line_total,
            )
        )

    po.total_cost = total_cost
    po.items = items

    db.add(po)
    db.commit()
    db.refresh(po)

    return po


def list_pos(db: Session, shop_domain: str, status: str | None = None):
    shop = get_shop_by_domain(db, shop_domain)

    query = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items))
        .filter(PurchaseOrder.shop_id == shop.id)
        .order_by(PurchaseOrder.created_at.desc())
    )

    if status:
        query = query.filter(PurchaseOrder.status == status)

    return query.all()


def get_po_by_id(db: Session, shop_domain: str, po_id):
    shop = get_shop_by_domain(db, shop_domain)

    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items))
        .filter(PurchaseOrder.id == po_id, PurchaseOrder.shop_id == shop.id)
        .first()
    )

    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    return po


def update_po_status(db: Session, shop_domain: str, po_id, new_status: str):
    if new_status not in ALLOWED_PO_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid PO status")

    po = get_po_by_id(db, shop_domain, po_id)
    po.status = new_status

    db.commit()
    db.refresh(po)
    return po


def delete_po(db: Session, shop_domain: str, po_id):
    po = get_po_by_id(db, shop_domain, po_id)
    db.delete(po)
    db.commit()