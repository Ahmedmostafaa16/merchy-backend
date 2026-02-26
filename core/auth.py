import hashlib
import hmac
import requests
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.config import SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SCOPES, REDIRECT_URI
from core.deps import get_db
from models import Shop

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND_SUCCESS_URL = "https://merchy-frontend-nwbb.vercel.app/install/success"


def normalize_shop(shop: str) -> str:
    """Ensure shop domain is always stored consistently"""
    return shop.replace("https://", "").replace("http://", "").strip().strip("/")


# 🔹 Step 1 — Redirect merchant to Shopify install screen
@router.get("/install")
def install(shop: str):
    shop = normalize_shop(shop)

    params = {
        "client_id": SHOPIFY_API_KEY,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": "randomstring",
    }

    url = f"https://{shop}/admin/oauth/authorize?" + urlencode(params)
    return RedirectResponse(url)


# 🔹 Step 2 — Shopify redirects here after install
@router.get("/callback")
def shopify_callback(request: Request, db: Session = Depends(get_db)):
    import traceback

    try:
        params = dict(request.query_params)

        hmac_received = params.pop("hmac", None)
        code = params.get("code")
        shop = params.get("shop")

        if not shop or not code or not hmac_received:
            raise HTTPException(status_code=400, detail="Missing shop/code/hmac")

        shop = normalize_shop(shop)
        print("OAuth callback: received shop:", shop)

        # --- Verify HMAC ---
        sorted_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        digest = hmac.new(
            SHOPIFY_API_SECRET.encode(),
            sorted_params.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(digest, hmac_received):
            raise HTTPException(status_code=400, detail="HMAC validation failed")
        print("OAuth callback: HMAC verified")

        # --- Exchange code for token ---
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
            print("Token exchange response:", token_json)
            raise HTTPException(status_code=400, detail="Token exchange failed")
        print("OAuth callback: token received")

        # --- Save or update shop in DB ---
        print("OAuth callback: DB upsert started")

        store = db.query(Shop).filter(Shop.shop_domain == shop).first()

        if store:
            store.access_token = access_token
            store.is_active = True
            print("OAuth callback: updating existing shop")
        else:
            store = Shop(
                shop_domain=shop,
                access_token=access_token,
                is_active=True
            )
            db.add(store)
            print("OAuth callback: creating new shop")

        # flush ensures INSERT executed before commit
        db.flush()
        db.commit()
        db.refresh(store)

        print("OAuth callback: DB commit success, shop_id:", getattr(store, "id", None))

        # 🔹 Webhooks disabled temporarily for debugging
        # register_webhook(...)

        # --- Redirect to React success page ---
        return RedirectResponse(f"{FRONTEND_SUCCESS_URL}?shop={shop}")

    except HTTPException:
        raise
    except Exception as exc:
        print("OAuth callback error:", str(exc))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="OAuth callback failed")


# 🔹 Step 3 — Endpoint for frontend to verify shop install
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