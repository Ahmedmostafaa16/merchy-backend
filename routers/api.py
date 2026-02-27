from fastapi import APIRouter, Depends
from core.session_token import verify_shopify_session_token

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/me")
def me(shop_domain: str = Depends(verify_shopify_session_token)):
    return {"ok": True, "shop": shop_domain}
