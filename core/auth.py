import hashlib
import hmac
import requests
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode
from sqlalchemy.orm import Session

from core.config import SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SCOPES, REDIRECT_URI
from core.deps import get_db
from models import Shop

router = APIRouter()

FRONTEND_SUCCESS_URL = "https://merchy-frontend-nwbb.vercel.app/install/success"


# 🔹 Step 1 — Redirect merchant to Shopify install screen
@router.get("/auth/install")
def install(shop: str):
    params = {
        "client_id": SHOPIFY_API_KEY,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": "randomstring",
    }

    url = f"https://{shop}/admin/oauth/authorize?" + urlencode(params)
    return RedirectResponse(url)


# 🔹 Step 2 — Shopify redirects here after install
@router.get("/auth/callback")
def shopify_callback(request: Request, db: Session = Depends(get_db)):

    params = dict(request.query_params)

    # Extract values
    hmac_received = params.pop("hmac", None)
    code = params.get("code")
    shop = params.get("shop")

    # --- Verify HMAC ---
    sorted_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

    digest = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(digest, hmac_received):
        raise HTTPException(status_code=400, detail="HMAC validation failed")

    # --- Exchange code for token ---
    token_response = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code,
        },
    )

    token_json = token_response.json()
    access_token = token_json.get("access_token")
    print("TOKEN RESPONSE:", token_json)
    print("SHOP:", shop)

    if not access_token:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    # --- Save or update shop in DB ---
    existing_shop = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if existing_shop:
        existing_shop.access_token = access_token
        existing_shop.is_active = True
    else:
        new_shop = Shop(
            shop_domain=shop,
            access_token=access_token,
            is_active=True
        )
        db.add(new_shop)

    db.commit()

    # --- Redirect to React success page ---
    return RedirectResponse(f"{FRONTEND_SUCCESS_URL}?shop={shop}")


# 🔹 Step 3 — Endpoint for frontend to verify shop install
@router.get("/shops/{shop}")
def get_shop(shop: str, db: Session = Depends(get_db)):

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()

    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")

    return {
        "shop": store.shop_domain,
        "installed": store.is_active
    }