import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from core.config import SHOPIFY_API_SECRET
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def normalize_shop(shop: str | None) -> str | None:
    if not shop:
        return None
    return shop.replace("https://", "").replace("http://", "").strip().strip("/").lower()


def verify_webhook(raw_body: bytes, hmac_header: str | None) -> bool:
    if not hmac_header or not SHOPIFY_API_SECRET:
        return False

    computed_hmac = base64.b64encode(
        hmac.new(
            SHOPIFY_API_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(computed_hmac, hmac_header)


async def read_verified_webhook(request: Request) -> tuple[bytes, dict, str | None, str | None]:
    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

    if not verify_webhook(raw_body, hmac_header):
        raise HTTPException(status_code=400, detail="Invalid webhook HMAC")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    topic = request.headers.get("X-Shopify-Topic")
    shop_domain = normalize_shop(
        request.headers.get("X-Shopify-Shop-Domain")
        or payload.get("shop_domain")
        or payload.get("myshopify_domain")
    )

    return raw_body, payload, topic, shop_domain


def delete_shop_data(db: Session, shop_domain: str | None) -> None:
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first() if shop_domain else None
    if shop:
        db.delete(shop)
        db.commit()


def mark_shop_uninstalled(db: Session, shop_domain: str | None) -> None:
    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first() if shop_domain else None
    if not shop:
        return

    shop.is_active = False
    shop.subscription_status = "INACTIVE"
    shop.access_token = None
    db.commit()


def handle_subscription_update(db: Session, payload: dict, shop_domain: str | None) -> None:
    if not shop_domain:
        raise HTTPException(status_code=400, detail="Missing shop domain")

    shop = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop:
        return

    subscription = payload.get("app_subscription") or payload
    status = subscription.get("status")
    subscription_id = subscription.get("admin_graphql_api_id") or subscription.get("id")

    if status:
        shop.subscription_status = status.upper()

    if subscription_id:
        shop.subscription_id = subscription_id

    db.commit()


async def process_webhook(request: Request, db: Session) -> Response:
    _, payload, topic, shop_domain = await read_verified_webhook(request)
    normalized_topic = (topic or "").lower()

    if normalized_topic == "app/uninstalled":
        mark_shop_uninstalled(db, shop_domain)
        return Response(status_code=200)

    if normalized_topic == "app_subscriptions/update":
        handle_subscription_update(db, payload, shop_domain)
        return Response(status_code=200)

    if normalized_topic == "customers/data_request":
        return Response(status_code=200)

    if normalized_topic == "customers/redact":
        return Response(status_code=200)

    if normalized_topic == "shop/redact":
        delete_shop_data(db, shop_domain)
        return Response(status_code=200)

    return Response(status_code=200)


@router.post("")
async def webhooks(request: Request, db: Session = Depends(get_db)):
    return await process_webhook(request, db)


@router.post("/")
async def webhooks_slash(request: Request, db: Session = Depends(get_db)):
    return await process_webhook(request, db)


@router.post("/app-uninstalled")
async def app_uninstalled(request: Request, db: Session = Depends(get_db)):
    _, payload, _, shop_domain = await read_verified_webhook(request)
    mark_shop_uninstalled(
        db,
        shop_domain or normalize_shop(payload.get("myshopify_domain")),
    )
    return Response(status_code=200)


@router.post("/uninstalled")
async def app_uninstalled_legacy(request: Request, db: Session = Depends(get_db)):
    return await app_uninstalled(request, db)


@router.post("/app_subscriptions_update")
async def app_subscriptions_update(request: Request, db: Session = Depends(get_db)):
    _, payload, _, shop_domain = await read_verified_webhook(request)
    handle_subscription_update(db, payload, shop_domain)
    return Response(status_code=200)


@router.post("/customers/data_request")
async def customers_data_request(request: Request):
    await read_verified_webhook(request)
    return Response(status_code=200)


@router.post("/customers_data_request")
async def customers_data_request_rest(request: Request):
    return await customers_data_request(request)


@router.post("/customers/redact")
async def customers_redact(request: Request):
    await read_verified_webhook(request)
    return Response(status_code=200)


@router.post("/customers_redact")
async def customers_redact_rest(request: Request):
    return await customers_redact(request)


@router.post("/shop/redact")
async def shop_redact(request: Request, db: Session = Depends(get_db)):
    _, payload, _, shop_domain = await read_verified_webhook(request)
    delete_shop_data(db, shop_domain or normalize_shop(payload.get("shop_domain")))
    return Response(status_code=200)


@router.post("/shop_redact")
async def shop_redact_rest(request: Request, db: Session = Depends(get_db)):
    return await shop_redact(request, db)
