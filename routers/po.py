from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.deps import get_db
from core.session_token import get_current_shop
from schemas.po_schema import POCreate, POResponse, POStatusUpdate
from services.po_service import (
    create_po,
    list_pos,
    get_po_by_id,
    update_po_status,
    delete_po,
)

router = APIRouter(prefix="/po", tags=["Purchase Orders"])


@router.post("", response_model=POResponse)
def create_purchase_order(
    payload: POCreate,
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    return create_po(db, shop_domain, payload)


@router.get("", response_model=list[POResponse])
def get_purchase_orders(
    status: str | None = Query(default=None),
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    return list_pos(db, shop_domain, status)


@router.get("/{po_id}", response_model=POResponse)
def get_purchase_order(
    po_id: UUID,
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    return get_po_by_id(db, shop_domain, po_id)


@router.patch("/{po_id}/status", response_model=POResponse)
def patch_purchase_order_status(
    po_id: UUID,
    payload: POStatusUpdate,
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    return update_po_status(db, shop_domain, po_id, payload.status)


@router.delete("/{po_id}")
def remove_purchase_order(
    po_id: UUID,
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    delete_po(db, shop_domain, po_id)
    return {"message": "PO deleted successfully"}