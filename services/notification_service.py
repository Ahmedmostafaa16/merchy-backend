from sqlalchemy.orm import Session

from models import Notification, Shop


def upsert_notification(db: Session, shop_domain: str, email: str, threshold_days: int):
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()

    if not shop:
        raise Exception("Shop not found")

    notification = db.query(Notification).filter(Notification.shop_id == shop.id).first()

    if notification:
        notification.email = email
        notification.threshold_days = threshold_days
        notification.is_active = True
    else:
        notification = Notification(
            shop_id=shop.id,
            email=email,
            threshold_days=threshold_days,
            is_active=True,
        )
        db.add(notification)

    db.commit()
    db.refresh(notification)

    return notification
