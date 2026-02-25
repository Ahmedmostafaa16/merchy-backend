import base64
import hashlib
import hmac
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from core.config import SHOPIFY_API_SECRET
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_webhook(data: bytes, hmac_header: str):
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        data,
        hashlib.sha256
    ).digest()

    computed_hmac = base64.b64encode(digest).decode()

    return hmac.compare_digest(computed_hmac, hmac_header)


@router.post("/uninstalled")
async def app_uninstalled(request: Request, db: Session = Depends(get_db)):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    data = await request.json()
    shop = request.headers.get("X-Shopify-Shop-Domain")

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if store:
        store.is_active = False
        db.commit()

    return {"status": "uninstalled processed"}


@router.post("/orders_create")
async def orders_create(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    data = await request.json()
    print("New order webhook:", data)

    return {"status": "order received"}