from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.deps import get_db
from core.session_token import get_current_shop
from schemas.notification_schema import NotificationCreate
from services.notification_service import upsert_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("")
def save_notification(
    payload: NotificationCreate,
    shop_domain: str = Depends(get_current_shop),
    db: Session = Depends(get_db),
):
    try:
        notification = upsert_notification(
            db,
            shop_domain,
            payload.email,
            payload.threshold_days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Notification saved successfully",
        "data": {
            "email": notification.email,
            "threshold_days": notification.threshold_days,
        },
    }
