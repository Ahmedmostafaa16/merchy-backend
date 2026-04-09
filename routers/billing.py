# routers/billing.py

from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.auth import get_valid_shopify_access_token, normalize_shop, verify_hmac
from core.config import FRONTEND_APP_URL, SHOPIFY_API_VERSION, SHOPIFY_BILLING_TEST
from core.deps import get_db, get_installed_shop
from models import Shop

PLAN_CONFIG = {
    "basic": {
        "name": "Basic",
        "price": "20.00",
        "trial_days": 30,
    }
}

CREATE_SUBSCRIPTION_MUTATION = """
mutation CreateSubscription(
  $name: String!,
  $price: Decimal!,
  $returnUrl: URL!,
  $trialDays: Int!,
  $test: Boolean!
) {
  appSubscriptionCreate(
    name: $name
    returnUrl: $returnUrl
    trialDays: $trialDays
    test: $test
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

GET_SUBSCRIPTION_QUERY = """
query GetSubscription($id: ID!) {
  node(id: $id) {
    ... on AppSubscription {
      id
      name
      status
      trialDays
      currentPeriodEnd
      createdAt
    }
  }
}
"""

router = APIRouter(prefix="/billing", tags=["billing"])


async def run_graphql(shop_domain: str, access_token: str, query: str, variables: dict):
    url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    async with httpx.AsyncClient() as client:
        res = await client.post(
            url,
            json={"query": query, "variables": variables},
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            },
        )

    res.raise_for_status()
    return res.json()


def _active_trial(store: Shop, now: datetime) -> bool:
    return (
        store.trial_ends_at is not None and
        store.trial_ends_at.replace(tzinfo=timezone.utc) > now
    )


def _billing_status_payload(store: Shop) -> dict:
    now = datetime.now(timezone.utc)
    in_trial = _active_trial(store, now)
    is_active = store.subscription_status == "ACTIVE"
    effective_status = "ACTIVE" if is_active else "TRIAL" if in_trial else "INACTIVE"

    trial_days_left = None
    trial_ends_at = None
    if store.trial_ends_at is not None:
        trial_ends_at = store.trial_ends_at.replace(tzinfo=timezone.utc).isoformat()
    if in_trial:
        trial_days_left = (store.trial_ends_at.replace(tzinfo=timezone.utc) - now).days

    return {
        "status": effective_status,
        "trial_ends_at": trial_ends_at,
        "plan": "basic",
        "shop": store.shop_domain,
        "subscription_status": store.subscription_status,
        "is_active": is_active,
        "in_trial": in_trial,
        "trial_days_left": trial_days_left,
        "has_access": is_active or in_trial,
    }


async def create_subscription(shop_domain: str, access_token: str, plan: str, host: str | None = None):
    config = PLAN_CONFIG.get(plan)
    if not config:
        raise HTTPException(status_code=400, detail="Invalid plan")

    return_params = {"shop": shop_domain}
    if host:
        return_params["host"] = host

    return_url = (
        f"https://merchyapp-backend.up.railway.app/billing/confirm?"
        f"{urlencode(return_params)}"
    )

    result = await run_graphql(
        shop_domain=shop_domain,
        access_token=access_token,
        query=CREATE_SUBSCRIPTION_MUTATION,
        variables={
            "name": config["name"],
            "price": config["price"],
            "returnUrl": return_url,
            "trialDays": config["trial_days"],
            "test": SHOPIFY_BILLING_TEST,
        },
    )

    data = result["data"]["appSubscriptionCreate"]

    if data["userErrors"]:
        raise HTTPException(status_code=400, detail=data["userErrors"])

    return {
        "confirmation_url": data["confirmationUrl"],
        "subscription": data["appSubscription"],
        "plan": plan,
    }


@router.post("/create")
async def create_billing(
    plan: str = Query(default="basic"),
    host: str | None = Query(default=None),
    shop: Shop = Depends(get_installed_shop),
    db: Session = Depends(get_db),
):
    if shop.subscription_status in {"ACTIVE", "PENDING"}:
        raise HTTPException(status_code=409, detail="Subscription already exists")

    access_token = get_valid_shopify_access_token(db, shop.shop_domain)
    subscription = await create_subscription(
        shop_domain=shop.shop_domain,
        access_token=access_token,
        plan=plan,
        host=host,
    )

    created_subscription = subscription["subscription"]
    shop.subscription_id = created_subscription.get("id")
    shop.subscription_status = created_subscription.get("status") or "PENDING"
    db.commit()

    return {
        "confirmation_url": subscription["confirmation_url"],
        "plan": subscription["plan"],
    }


@router.get("/subscribe/{plan}")
async def subscribe(
    plan: str,
    host: str | None = Query(default=None),
    shop: Shop = Depends(get_installed_shop),
    db: Session = Depends(get_db),
):
    if shop.subscription_status in {"ACTIVE", "PENDING"}:
        raise HTTPException(status_code=409, detail="Subscription already exists")

    access_token = get_valid_shopify_access_token(db, shop.shop_domain)
    subscription = await create_subscription(
        shop_domain=shop.shop_domain,
        access_token=access_token,
        plan=plan,
        host=host,
    )
    return RedirectResponse(subscription["confirmation_url"])


@router.get("/confirm")
async def billing_confirm(
    request: Request,
    shop: str = Query(...),
    charge_id: str = Query(...),
    host: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    params = dict(request.query_params)
    received_hmac = params.pop("hmac", None)
    params.pop("signature", None)
    if not received_hmac or not verify_hmac(params, received_hmac):
        raise HTTPException(status_code=403, detail="Invalid HMAC")

    shop_domain = normalize_shop(shop)
    access_token = get_valid_shopify_access_token(db, shop_domain)

    result = await run_graphql(
        shop_domain=shop_domain,
        access_token=access_token,
        query=GET_SUBSCRIPTION_QUERY,
        variables={"id": charge_id},
    )

    subscription = result["data"]["node"]
    if not subscription:
        raise HTTPException(status_code=400, detail="Subscription not found")

    shop_record = db.query(Shop).filter(Shop.shop_domain == shop_domain).first()
    if not shop_record:
        raise HTTPException(status_code=404, detail="Shop not found")

    external_status = subscription["status"]
    current_trial_active = _active_trial(shop_record, datetime.now(timezone.utc))

    shop_record.subscription_id = subscription["id"]

    if external_status == "ACTIVE":
        shop_record.subscription_status = "ACTIVE"
        if subscription.get("trialDays"):
            shop_record.trial_ends_at = datetime.now(timezone.utc) + timedelta(
                days=subscription["trialDays"]
            )
        else:
            shop_record.trial_ends_at = None
    elif external_status == "PENDING":
        shop_record.subscription_status = "PENDING"
    else:
        shop_record.subscription_status = "INACTIVE"
        if not current_trial_active:
            shop_record.trial_ends_at = None

    db.commit()

    redirect_params = {
        "shop": shop_domain,
        "billing": "success" if external_status in {"ACTIVE", "PENDING"} else "declined",
    }
    if host:
        redirect_params["host"] = host

    return RedirectResponse(f"{FRONTEND_APP_URL}/dashboard?{urlencode(redirect_params)}")


@router.get("/status")
def billing_status(shop: Shop = Depends(get_installed_shop)):
    return _billing_status_payload(shop)
