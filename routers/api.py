from fastapi import APIRouter, Depends
from core.session_tokens import verify_shopify_session_token

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/me")
def me(payload = Depends(verify_shopify_session_token)):
    return {"ok": True, "shop": payload.get("dest")}