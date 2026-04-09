from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from core.session_token import get_session_shop_domain
from db import SessionLocal
from models import Shop


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_installed_shop(
    shop_domain: str = Depends(get_session_shop_domain),
    db: Session = Depends(get_db),
) -> Shop:
    store = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")
    if not store.is_active:
        raise HTTPException(status_code=403, detail="Shop is not active")
    return store


def get_active_shop(
    store: Shop = Depends(get_installed_shop),
) -> Shop:
    now = datetime.now(timezone.utc)

    in_trial = (
        store.trial_ends_at is not None and
        store.trial_ends_at.replace(tzinfo=timezone.utc) > now
    )

    has_access = store.subscription_status == "ACTIVE" or in_trial

    if not has_access:
        raise HTTPException(status_code=402, detail="Active subscription required")

    return store
