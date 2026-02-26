import base64
import hashlib
import hmac

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from core.config import SHOPIFY_API_SECRET
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ----------------------------
# Helpers
# ----------------------------

def normalize_shop(shop: str | None) -> str | None:
    if not shop:
        return None
    return shop.replace("https://", "").replace("http://", "").strip().strip("/")


def verify_webhook(data: bytes, hmac_header: str | None) -> bool:
    if not hmac_header:
        return False

    digest = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        data,
        hashlib.sha256
    ).digest()

    computed_hmac = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed_hmac, hmac_header)


# ----------------------------
# App uninstall webhook
# ----------------------------

@router.post("/uninstalled")
async def app_uninstalled(request: Request, db: Session = Depends(get_db)):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    shop = normalize_shop(request.headers.get("X-Shopify-Shop-Domain"))

    if shop:
        store = db.query(Shop).filter(Shop.shop_domain == shop).first()
        if store:
            db.delete(store)
            db.commit()

    return {"status": "uninstalled processed"}


# ----------------------------
# GDPR / Privacy webhooks
# REQUIRED for Shopify public apps
# ----------------------------

@router.post("/customers/data_request")
async def customers_data_request(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    # If you store customer data, you must return it here.
    # If not, simply acknowledge.

    return {"status": "ok"}


@router.post("/customers/redact")
async def customers_redact(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    # Delete/redact customer data here if you store any.

    return {"status": "ok"}


@router.post("/shop/redact")
async def shop_redact(request: Request, db: Session = Depends(get_db)):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    shop = normalize_shop(request.headers.get("X-Shopify-Shop-Domain"))

    if shop:
        store = db.query(Shop).filter(Shop.shop_domain == shop).first()
        if store:
            store.is_active = False
            db.commit()

    return {"status": "ok"}


# ----------------------------
# Optional example webhook
# Keep only if needed
# ----------------------------

@router.post("/orders_create")
async def orders_create(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Webhook HMAC failed")

    data = await request.json()
    print("New order webhook:", data)

    return {"status": "order received"}