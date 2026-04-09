# routers/billing.py

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.deps import get_db
from routers.auth import get_valid_shopify_access_token, normalize_shop

SHOPIFY_API_VERSION = "2026-04"

# ─── GraphQL Mutation ────────────────────────────────────────────────────────

CREATE_SUBSCRIPTION_MUTATION = """
mutation CreateSubscription($name: String!, $price: Decimal!, $returnUrl: String!, $trialDays: Int!) {
  appSubscriptionCreate(
    name: $name
    returnUrl: $returnUrl
    trialDays: $trialDays
    test: true
    lineItems: [
      {
        plan: {
          appRecurringPricingDetails: {
            price: { amount: $price, currencyCode: USD }
            interval: EVERY_30_DAYS
          }
        }
      }
    ]
  ) {
    appSubscription {
      id
      status
      trialDays
    }
    confirmationUrl
    userErrors {
      field
      message
    }
  }
}
"""

# ─── Plan Config ─────────────────────────────────────────────────────────────

PLAN_CONFIG = {
    "basic": {
        "name": "Basic",
        "price": "20.00",
        "trial_days": 30,
        "return_url": "https://merchyapp-backend.up.railway.app/billing/callback"
    }
}

# ─── Reusable GraphQL Runner ─────────────────────────────────────────────────

async def run_graphql(shop_domain: str, access_token: str, query: str, variables: dict):
    url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    async with httpx.AsyncClient() as client:
        res = await client.post(
            url,
            json={"query": query, "variables": variables},
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json"
            }
        )

    res.raise_for_status()
    return res.json()

# ─── Create Subscription ─────────────────────────────────────────────────────

async def create_subscription(shop_domain: str, access_token: str, plan: str):
    config = PLAN_CONFIG.get(plan)
    if not config:
        raise HTTPException(status_code=400, detail="Invalid plan")

    result = await run_graphql(
        shop_domain=shop_domain,
        access_token=access_token,
        query=CREATE_SUBSCRIPTION_MUTATION,
        variables={
            "name": config["name"],
            "price": config["price"],
            "returnUrl": config["return_url"],
            "trialDays": config["trial_days"]
        }
    )

    data = result["data"]["appSubscriptionCreate"]

    if data["userErrors"]:
        raise HTTPException(status_code=400, detail=data["userErrors"])

    return {
        "confirmation_url": data["confirmationUrl"],
        "subscription": data["appSubscription"]
    }

# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/billing", tags=["billing"])

@router.get("/subscribe/{plan}")
async def subscribe(
    plan: str,
    shop: str = Query(..., description="mystore.myshopify.com"),
    db: Session = Depends(get_db)
):
    # 1. Normalize shop domain
    shop = normalize_shop(shop)

    # 2. Get valid access token (handles refresh automatically)
    access_token = get_valid_shopify_access_token(db, shop)

    # 3. Create subscription via Shopify GraphQL
    subscription = await create_subscription(
        shop_domain=shop,
        access_token=access_token,
        plan=plan
    )

    # 4. Redirect merchant to Shopify billing approval page
    return RedirectResponse(subscription["confirmation_url"])

# routers/billing.py (add at the bottom)

from models import Shop
from datetime import datetime, timezone, timedelta

ACTIVATE_SUBSCRIPTION_MUTATION = """
mutation ActivateSubscription($id: ID!) {
  appSubscriptionActivate(id: $id) {
    appSubscription {
      id
      status
      trialDays
      currentPeriodEnd
    }
    userErrors {
      field
      message
    }
  }
}
"""

GET_SUBSCRIPTION_QUERY = """
query GetSubscription($id: ID!) {
  node(id: $id) {
    ... on AppSubscription {
      id
      status
      trialDays
      currentPeriodEnd
      createdAt
    }
  }
}
"""

@router.get("/callback")
async def billing_callback(
    shop: str = Query(...),
    charge_id: str = Query(...),  # Shopify appends this automatically
    db: Session = Depends(get_db)
):
    shop = normalize_shop(shop)

    # 1. Get valid access token
    access_token = get_valid_shopify_access_token(db, shop)

    # 2. Fetch the subscription details from Shopify
    # charge_id here is the GID e.g. gid://shopify/AppSubscription/123
    result = await run_graphql(
        shop_domain=shop,
        access_token=access_token,
        query=GET_SUBSCRIPTION_QUERY,
        variables={"id": charge_id}
    )

    subscription = result["data"]["node"]

    if not subscription:
        raise HTTPException(status_code=400, detail="Subscription not found")

    status = subscription["status"]  # PENDING, ACTIVE, DECLINED etc.

    # 3. Save to DB regardless of status
    store = db.query(Shop).filter(Shop.shop_domain == shop).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")

    store.subscription_id = subscription["id"]
    store.subscription_status = status

    # 4. Calculate trial_ends_at if applicable
    if status == "ACTIVE" and subscription.get("trialDays"):
        store.trial_ends_at = datetime.now(timezone.utc) + timedelta(
            days=subscription["trialDays"]
        )

    db.commit()

    # 5. Redirect to frontend with result
    if status in ("ACTIVE", "PENDING"):
        return RedirectResponse(
            f"https://merchy-frontend-nwbb.vercel.app/dashboard?billing=success"
        )
    else:
        # DECLINED or other
        return RedirectResponse(
            f"https://merchy-frontend-nwbb.vercel.app/dashboard?billing=declined"
        )
        
# routers/billing.py (add at the bottom)

@router.get("/status")
def billing_status(
    shop: str = Query(...),
    db: Session = Depends(get_db)
):
    shop = normalize_shop(shop)

    store = db.query(Shop).filter(Shop.shop_domain == shop).first()
    if not store:
        raise HTTPException(status_code=404, detail="Shop not found")

    now = datetime.now(timezone.utc)

    # Check if still in trial
    in_trial = (
        store.trial_ends_at is not None and
        store.trial_ends_at.replace(tzinfo=timezone.utc) > now
    )

    # Days remaining in trial
    trial_days_left = None
    if in_trial:
        trial_days_left = (store.trial_ends_at.replace(tzinfo=timezone.utc) - now).days

    is_active = store.subscription_status == "ACTIVE"

    return {
        "shop": store.shop_domain,
        "subscription_status": store.subscription_status,  # ACTIVE / PENDING / DECLINED / None
        "is_active": is_active,
        "in_trial": in_trial,
        "trial_days_left": trial_days_left,
        "has_access": is_active or in_trial,  # ← use this to gate features
    }