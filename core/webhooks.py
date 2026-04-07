import base64
import hashlib
import hmac
import requests
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.orm import Session

from core.auth import get_valid_shopify_access_token
from core.config import SHOPIFY_API_SECRET
from core.deps import get_db
from db import SessionLocal
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
    if not hmac_header or not SHOPIFY_API_SECRET:
        return False

    computed_hmac = base64.b64encode(
        hmac.new(
            SHOPIFY_API_SECRET.encode("utf-8"),
            data,
            hashlib.sha256
        ).digest()
    ).decode()

    return hmac.compare_digest(computed_hmac, hmac_header)


async def validate_shopify_webhook(request: Request):
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not hmac_header:
        return Response(status_code=401)

    digest = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()

    computed_hmac = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(computed_hmac, hmac_header):
        return Response(status_code=401)

    return Response(status_code=200)


# ----------------------------
# App uninstall webhook
# ----------------------------

@router.post("/uninstalled")
async def app_uninstalled(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        return Response(status_code=401)

    print("Webhook received")

    shop = normalize_shop(request.headers.get("X-Shopify-Shop-Domain"))

    db = SessionLocal()
    try:
        if shop:
            store = db.query(Shop).filter(Shop.shop_domain == shop).first()
            if store:
                db.delete(store)
                db.commit()
    finally:
        db.close()

    return Response(status_code=200)


# ----------------------------
# GDPR / Privacy webhooks
# REQUIRED for Shopify public apps
# ----------------------------

@router.post("/customers/data_request")
async def customers_data_request(request: Request):
    return await validate_shopify_webhook(request)


@router.post("/customers_data_request")
async def customers_data_request_rest(request: Request):
    return await validate_shopify_webhook(request)


@router.post("/customers/redact")
async def customers_redact(request: Request):
    return await validate_shopify_webhook(request)


@router.post("/customers_redact")
async def customers_redact_rest(request: Request):
    return await validate_shopify_webhook(request)


@router.post("/shop/redact")
async def shop_redact(request: Request):
    return await validate_shopify_webhook(request)


@router.post("/shop_redact")
async def shop_redact_rest(request: Request):
    return await validate_shopify_webhook(request)


# ----------------------------
# Optional example webhook
# Keep only if needed
# ----------------------------

@router.post("/orders_create")
async def orders_create(request: Request):

    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        return Response(status_code=401)

    print("Webhook received")
    data = await request.json()
    print("New order webhook:", data)

    return Response(status_code=200)

@router.get("/debug/list-webhooks")
def list_webhooks(shop: str, db: Session = Depends(get_db)):
    access_token = get_valid_shopify_access_token(db, shop)

    res = requests.get(
        f"https://{shop}/admin/api/2024-01/webhooks.json",
        headers={
            "X-Shopify-Access-Token": access_token
        }
    )

    return res.json()
