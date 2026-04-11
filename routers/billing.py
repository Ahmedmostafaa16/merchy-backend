# routers/billing.py

from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.auth import get_valid_shopify_access_token
from core.config import SHOPIFY_API_VERSION
from core.deps import get_db, get_installed_shop
from models import Shop

GET_SUBSCRIPTION_QUERY = """
query {
  appInstallation {
    activeSubscriptions {
      id
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

    request_id = res.headers.get("x-request-id")
    print("[BILLING] SHOPIFY REQUEST ID:", request_id)

    try:
        payload = res.json()
    except ValueError:
        payload = {"raw_text": res.text}

    print("[BILLING] SHOPIFY HTTP STATUS:", res.status_code)
    print("[BILLING] SHOPIFY RESPONSE:", payload)

    if res.is_error:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Shopify GraphQL request failed",
                "request_id": request_id,
                "shopify_status": res.status_code,
                "shopify_response": payload,
            },
        )

    return payload


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

    trial_ends_at = None
    if store.trial_ends_at is not None:
        trial_ends_at = store.trial_ends_at.replace(tzinfo=timezone.utc).isoformat()

    return {
        "status": effective_status,
        "trial_ends_at": trial_ends_at,
        "plan": "basic",
        "has_access": is_active or in_trial,
    }


@router.get("/sync")
async def sync_billing_status(
    shop: Shop = Depends(get_installed_shop),
    db: Session = Depends(get_db),
):
    access_token = get_valid_shopify_access_token(db, shop.shop_domain)

    result = await run_graphql(
        shop.shop_domain,
        access_token,
        GET_SUBSCRIPTION_QUERY,
        {},
    )

    subscriptions = result["data"]["appInstallation"]["activeSubscriptions"]

    if subscriptions:
        subscription = subscriptions[0]

        shop.subscription_id = subscription["id"]
        shop.subscription_status = subscription["status"]

        if subscription.get("trialDays"):
            shop.trial_ends_at = datetime.now(timezone.utc) + timedelta(
                days=subscription["trialDays"]
            )
        else:
            shop.trial_ends_at = None
    else:
        shop.subscription_id = None
        shop.subscription_status = "INACTIVE"
        shop.trial_ends_at = None

    db.commit()

    return {"subscription_status": shop.subscription_status}


@router.get("/status")
def billing_status(shop: Shop = Depends(get_installed_shop)):
    return _billing_status_payload(shop)
