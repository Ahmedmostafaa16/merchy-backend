import hashlib
import hmac
import secrets
import requests
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.config import (
    SHOPIFY_API_KEY,
    SHOPIFY_API_SECRET,
    SCOPES,
    REDIRECT_URI, )
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND_SUCCESS_URL = "https://merchy-frontend-nwbb.vercel.app/install/success"

SHOPIFY_API_VERSION="2026-01"  # Update as needed, but keep consistent across all API calls

STATE_COOKIE = "shopify_oauth_state"
STATE_COOKIE_MAX_AGE = 1800  # 30 minutes


# ----------------------------
# Helpers
# ----------------------------

def normalize_shop(shop: str) -> str:
    return shop.replace("https://", "").replace("http://", "").strip().strip("/")


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

    resp = requests.post(
        endpoint,
        json={"query": query, "variables": variables},
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    data = resp.json()
    errors = data.get("data", {}).get("webhookSubscriptionCreate", {}).get("userErrors")

    if errors:
        raise RuntimeError(f"Webhook create failed for {topic}: {errors}")


def register_required_webhooks(shop: str, access_token: str, backend_base_url: str):
    register_webhook_graphql(
        shop, access_token, "APP_UNINSTALLED",
        f"{backend_base_url}/webhooks/uninstalled"
    )

    register_webhook_graphql(
        shop, access_token, "CUSTOMERS_DATA_REQUEST",
        f"{backend_base_url}/webhooks/customers/data_request"
    )

    register_webhook_graphql(
        shop, access_token, "CUSTOMERS_REDACT",
        f"{backend_base_url}/webhooks/customers/redact"
    )

    register_webhook_graphql(
        shop, access_token, "SHOP_REDACT",
        f"{backend_base_url}/webhooks/shop/redact"
    )


# ----------------------------
# Step 1 — Install redirect
# ----------------------------

@router.get("/install")
def install(shop: str):
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
        samesite="lax",
    )

    return response


# ----------------------------
# Step 2 — OAuth callback
# ----------------------------

@router.get("/callback")
def shopify_callback(request: Request, db: Session = Depends(get_db)):

    params = dict(request.query_params)

    hmac_received = params.pop("hmac", None)
    code = params.get("code")
    shop = params.get("shop")
    state = params.get("state")

    if not shop or not code or not hmac_received or not state:
        raise HTTPException(status_code=400, detail="Missing shop/code/hmac/state")

    shop = normalize_shop(shop)

    # Validate state (CSRF)
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # Verify HMAC
    if not verify_hmac(params, hmac_received):
        raise HTTPException(status_code=400, detail="HMAC validation failed")

    # Exchange code for token
    token_response = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code,
        },
        timeout=30,
    )

    token_json = token_response.json()
    access_token = token_json.get("access_token")

    if not access_token:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_json}")

    # Save or update shop
    store = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if store:
        store.access_token = access_token
        store.is_active = True
    else:
        store = Shop(
            shop_domain=shop,
            access_token=access_token,
            is_active=True
        )
        db.add(store)

    db.commit()

    # Register webhooks
    backend_base_url = str(request.base_url).rstrip("/")

    try:
        register_required_webhooks(shop, access_token, backend_base_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook registration failed: {e}")

    # Redirect to frontend
    response = RedirectResponse(f"{FRONTEND_SUCCESS_URL}?shop={shop}")
    response.delete_cookie(STATE_COOKIE)

    return response


# ----------------------------
# Step 3 — Verify install from frontend
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