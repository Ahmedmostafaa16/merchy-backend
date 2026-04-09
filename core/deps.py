from db import SessionLocal
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from models import Shop

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_active_shop(
    shop: str = Query(...),
    db: Session = Depends(get_db)
) -> Shop:
    from core.auth import normalize_shop
    shop = normalize_shop(shop)

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")

    now = datetime.now(timezone.utc)
    in_trial = (
        store.trial_ends_at is not None and
        store.trial_ends_at.replace(tzinfo=timezone.utc) > now
    )
    has_access = store.subscription_status == "ACTIVE" or in_trial

    if not has_access:
        raise HTTPException(status_code=402, detail="Active subscription required")

    return store  # ← returns the full shop object