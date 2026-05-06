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


def update_po(db: Session, shop_domain: str, po_id, payload):
    po = get_po_by_id(db, shop_domain, po_id)
    fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))

    if "supplier_name" in fields_set:
        supplier_name = (payload.supplier_name or "").strip()
        if not supplier_name:
            raise HTTPException(status_code=400, detail="Supplier name is required")
        po.supplier_name = supplier_name

    if "status" in fields_set:
        if payload.status not in ALLOWED_PO_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid PO status")
        po.status = payload.status

    if "due_date" in fields_set:
        po.due_date = payload.due_date

    if "currency" in fields_set and payload.currency is not None:
        po.currency = payload.currency

    if "items" in fields_set:
        if payload.items is None:
            raise HTTPException(status_code=400, detail="Items cannot be null")

        existing_items_by_id = {item.id: item for item in po.items}
        retained_item_ids = set()
        next_items = []
        total_cost = Decimal("0.00")

        for item_payload in payload.items:
            if item_payload.id is not None:
                if item_payload.id in retained_item_ids:
                    raise HTTPException(status_code=400, detail="Duplicate PO item id in payload")

                existing_item = existing_items_by_id.get(item_payload.id)
                if existing_item is None:
                    raise HTTPException(status_code=400, detail="PO item does not belong to this purchase order")

                if item_payload.sku is not None:
                    existing_item.sku = item_payload.sku
                if item_payload.title is not None:
                    existing_item.title = item_payload.title
                existing_item.quantity = item_payload.quantity
                existing_item.unit_price = item_payload.unit_price
                existing_item.total_price = Decimal(item_payload.quantity) * item_payload.unit_price
                total_cost += existing_item.total_price
                retained_item_ids.add(existing_item.id)
                continue

            if not item_payload.sku or not item_payload.title:
                raise HTTPException(status_code=400, detail="New PO items require sku and title")

            line_total = Decimal(item_payload.quantity) * item_payload.unit_price
            next_items.append(
                POItem(
                    sku=item_payload.sku,
                    title=item_payload.title,
                    quantity=item_payload.quantity,
                    unit_price=item_payload.unit_price,
                    total_price=line_total,
                )
            )
            total_cost += line_total

        for existing_item in list(po.items):
            if existing_item.id not in retained_item_ids:
                db.delete(existing_item)

        for next_item in next_items:
            po.items.append(next_item)

        po.total_cost = total_cost
        db.flush()

    db.flush()

    db.commit()
    db.refresh(po)
    return get_po_by_id(db, shop_domain, po_id)


def delete_po(db: Session, shop_domain: str, po_id):
    po = get_po_by_id(db, shop_domain, po_id)
    db.delete(po)
    db.commit()
