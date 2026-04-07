import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import requests
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.config import (
    BACKEND_PUBLIC_URL,
    FRONTEND_APP_URL,
    SHOPIFY_API_KEY,
    SHOPIFY_API_SECRET,
    SHOPIFY_API_VERSION,
    SCOPES,
    REDIRECT_URI,
)
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "shopify_oauth_state"
HOST_COOKIE = "shopify_host"
STATE_COOKIE_MAX_AGE = 1800  # 30 minutes
TOKEN_REFRESH_BUFFER_SECONDS = 60


# ----------------------------
# Helpers
# ----------------------------

def normalize_shop(shop: str) -> str:
    return shop.replace("https://", "").replace("http://", "").strip().strip("/")


def build_frontend_success_url() -> str:
    return f"{FRONTEND_APP_URL}/install/success"


def require_backend_public_url() -> str:
    if not BACKEND_PUBLIC_URL:
        raise RuntimeError("Missing APP_URL or REDIRECT_URI base URL for webhook registration")
    return BACKEND_PUBLIC_URL


def _expiry_datetime_from_seconds(seconds: int | None) -> datetime | None:
    if not seconds:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))


def exchange_oauth_code_for_token(shop: str, code: str) -> dict:
    token_response = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        data={
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code,
            "expiring": "1",
        },
        timeout=30,
    )
    token_response.raise_for_status()
    return token_response.json()


def refresh_shopify_access_token(shop: str, refresh_token: str) -> dict:
    token_response = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    return token_response.json()


def save_shop_token_payload(store: Shop, token_payload: dict) -> None:
    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_payload}")

    store.access_token = access_token
    store.access_token_expires_at = _expiry_datetime_from_seconds(token_payload.get("expires_in"))
    store.refresh_token = token_payload.get("refresh_token")
    store.refresh_token_expires_at = _expiry_datetime_from_seconds(token_payload.get("refresh_token_expires_in"))


def get_valid_shopify_access_token(db: Session, shop_domain: str) -> str:
    shop = db.query(Shop).filter(Shop.shop_domain == normalize_shop(shop_domain)).first()

    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    if not shop.access_token_expires_at:
        return shop.access_token

    now = datetime.now(timezone.utc)
    expires_at = shop.access_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at - timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS) > now:
        return shop.access_token

    if not shop.refresh_token:
        raise HTTPException(status_code=401, detail="Shopify refresh token missing")

    if shop.refresh_token_expires_at:
        refresh_expires_at = shop.refresh_token_expires_at
        if refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=timezone.utc)
        if refresh_expires_at <= now:
            raise HTTPException(status_code=401, detail="Shopify refresh token expired")

    refreshed_payload = refresh_shopify_access_token(shop.shop_domain, shop.refresh_token)
    save_shop_token_payload(shop, refreshed_payload)
    db.commit()
    db.refresh(shop)
    return shop.access_token


def verify_hmac(params: dict, received_hmac: str) -> bool:
    sorted_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, received_hmac)


def register_webhook_graphql(shop: str, access_token: str, topic: str, callback_url: str):
    endpoint = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    query = """
    mutation webhookSubscriptionCreate($topic: WebhookSubscriptionTopic!, $callbackUrl: URL!) {
      webhookSubscriptionCreate(
        topic: $topic,
        webhookSubscription: { callbackUrl: $callbackUrl, format: JSON }
      ) {
        webhookSubscription { id }
        userErrors { field message }
      }
    }
    """

    variables = {"topic": topic, "callbackUrl": callback_url}

    print(f"[WEBHOOK] Registering {topic}")

    resp = requests.post(
        endpoint,
        json={"query": query, "variables": variables},
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    print(f"[WEBHOOK] {topic} -> {resp.status_code}")

    data = resp.json()
    errors = data.get("data", {}).get("webhookSubscriptionCreate", {}).get("userErrors")

    if errors:
        raise RuntimeError(f"Webhook create failed for {topic}: {errors}")


def register_webhook_rest(shop: str, access_token: str, topic: str, callback_url: str):
    endpoint = f"https://{shop}/admin/api/2024-01/webhooks.json"

    print(f"[WEBHOOK] Registering {topic}")

    resp = requests.post(
        endpoint,
        json={
            "webhook": {
                "topic": topic,
                "address": callback_url,
                "format": "json",
            }
        },
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    print(f"[WEBHOOK] {topic} -> {resp.status_code}")

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Webhook create failed for {topic}: {resp.text}")


def register_webhooks(shop: str, access_token: str):
    print("[WEBHOOK] Starting registration")
    backend_base_url = require_backend_public_url()
    register_uninstall_webhook(shop, access_token, backend_base_url)

    register_webhook_rest(
        shop, access_token, "customers/data_request",
        f"{backend_base_url}/webhooks/customers_data_request"
    )

    register_webhook_rest(
        shop, access_token, "customers/redact",
        f"{backend_base_url}/webhooks/customers_redact"
    )

    register_webhook_rest(
        shop, access_token, "shop/redact",
        f"{backend_base_url}/webhooks/shop_redact"
    )


def register_uninstall_webhook(shop: str, access_token: str, backend_base_url: str):
    register_webhook_graphql(
        shop,
        access_token,
        "APP_UNINSTALLED",
        f"{backend_base_url}/webhooks/uninstalled",
    )


# ----------------------------
# Step 1 - Install redirect
# ----------------------------

@router.get("/install")
def install(shop: str, host: str | None = None):
    shop = normalize_shop(shop)

    state = secrets.token_urlsafe(24)

    params = {
        "client_id": SHOPIFY_API_KEY,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }

    url = f"https://{shop}/admin/oauth/authorize?" + urlencode(params)
    response = RedirectResponse(url)

    response.set_cookie(
        key=STATE_COOKIE,
        value=state,
        max_age=STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="none",
    )
    if host:
        response.set_cookie(
            key=HOST_COOKIE,
            value=host,
            max_age=STATE_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="none",
        )

    return response


# ----------------------------
# Step 2 - OAuth callback
# ----------------------------

@router.get("/callback")
def shopify_callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)

    hmac_received = params.pop("hmac", None)
    code = params.get("code")
    shop = params.get("shop")
    state = params.get("state")
    host = params.get("host") or request.cookies.get(HOST_COOKIE)

    if not shop or not code or not hmac_received or not state:
        raise HTTPException(status_code=400, detail="Missing shop/code/hmac/state")

    shop = normalize_shop(shop)

    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    if not verify_hmac(params, hmac_received):
        raise HTTPException(status_code=400, detail="HMAC validation failed")

    token_json = exchange_oauth_code_for_token(shop, code)
    access_token = token_json.get("access_token")
    print("FULL TOKEN RESPONSE:", token_json)
    print("ACCESS TOKEN:", access_token)

    if not access_token:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_json}")

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if store:
        print("Updating existing token")
        save_shop_token_payload(store, token_json)
        store.is_active = True
    else:
        print("Creating new store")
        store = Shop(
            shop_domain=shop,
            access_token=access_token,
            access_token_expires_at=_expiry_datetime_from_seconds(token_json.get("expires_in")),
            refresh_token=token_json.get("refresh_token"),
            refresh_token_expires_at=_expiry_datetime_from_seconds(token_json.get("refresh_token_expires_in")),
            is_active=True
        )
        db.add(store)

    db.commit()
    print("TOKEN SAVED TO DB:", access_token)
    db.refresh(store)

    print("CALLBACK REACHED")
    register_webhooks(shop, access_token)
    print("WEBHOOK FUNCTION CALLED")

    query = {"shop": shop}
    if host:
        query["host"] = host
    response = RedirectResponse(f"{build_frontend_success_url()}?{urlencode(query)}")
    response.delete_cookie(STATE_COOKIE)
    response.delete_cookie(HOST_COOKIE)

    return response


# ----------------------------
# Step 3 - Verify install from frontend
# ----------------------------

@router.get("/shops/{shop}")
def get_shop(shop: str, db: Session = Depends(get_db)):
    shop = normalize_shop(shop)

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")

    return {
        "shop": store.shop_domain,
        "installed": store.is_active
    }
