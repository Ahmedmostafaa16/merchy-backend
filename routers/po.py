from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.deps import get_active_shop, get_db
from models import Shop
from schemas.po_schema import POCreate, POResponse, POStatusUpdate, POUpdate
from services.po_service import (
    create_po,
    list_pos,
    get_po_by_id,
    update_po,
    update_po_status,
    delete_po,
)

router = APIRouter(prefix="/po", tags=["Purchase Orders"])


@router.post("", response_model=POResponse)
def create_purchase_order(
    payload: POCreate,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    return create_po(db, shop.shop_domain, payload)


@router.get("", response_model=list[POResponse])
def get_purchase_orders(
    status: str | None = Query(default=None),
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    return list_pos(db, shop.shop_domain, status)


@router.get("/{po_id}", response_model=POResponse)
def get_purchase_order(
    po_id: UUID,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    return get_po_by_id(db, shop.shop_domain, po_id)


@router.patch("/{po_id}/status", response_model=POResponse)
def patch_purchase_order_status(
    po_id: UUID,
    payload: POStatusUpdate,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    return update_po_status(db, shop.shop_domain, po_id, payload.status)


@router.patch("/{po_id}", response_model=POResponse)
def patch_purchase_order(
    po_id: UUID,
    payload: POUpdate,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    return update_po(db, shop.shop_domain, po_id, payload)


@router.delete("/{po_id}")
def remove_purchase_order(
    po_id: UUID,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    delete_po(db, shop.shop_domain, po_id)
    return {"message": "PO deleted successfully"}
