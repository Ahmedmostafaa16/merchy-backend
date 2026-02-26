from typing import Optional, Dict, Any
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException

from core.config import SHOPIFY_API_KEY, SHOPIFY_API_SECRET


def _shop_from_dest(dest: str) -> str:
    # dest looks like: "https://mystore.myshopify.com"
    host = urlparse(dest).netloc
    return host


def verify_shopify_session_token(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Expect: Authorization: Bearer <session_token>
    Returns decoded payload if valid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer session token")

    token = authorization.split(" ", 1)[1].strip()

    # Decode without verifying issuer first to derive shop for issuer check
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session token")

    dest = unverified.get("dest")
    if not dest:
        raise HTTPException(status_code=401, detail="Session token missing dest")

    shop_domain = _shop_from_dest(dest)
    expected_issuer = f"https://{shop_domain}/admin"

    try:
        payload = jwt.decode(
            token,
            SHOPIFY_API_SECRET,
            algorithms=["HS256"],
            audience=SHOPIFY_API_KEY,
            issuer=expected_issuer,
            options={
                "require": ["exp", "nbf", "iss", "aud", "dest"],
            },
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Session token verification failed")