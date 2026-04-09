from urllib.parse import urlparse

import jwt
from fastapi import Depends, Header, HTTPException, status

from core.config import SHOPIFY_API_KEY, SHOPIFY_API_SECRET


def _normalize_shop_domain(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        return parsed.netloc.lower()
    return raw.lower().strip("/")


def _normalize_issuer_host(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    return parsed.netloc.lower() if parsed.netloc else ""


def _error(status_code: int, message: str):
    raise HTTPException(status_code=status_code, detail={"error": message})


def verify_shopify_session_token(
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization:
        _error(status.HTTP_401_UNAUTHORIZED, "missing session token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        _error(status.HTTP_401_UNAUTHORIZED, "invalid session token")

    token = token.strip()

    try:
        payload = jwt.decode(
            token,
            SHOPIFY_API_SECRET,
            algorithms=["HS256"],
            audience=SHOPIFY_API_KEY,
            options={"require": ["exp", "nbf", "aud", "iss", "dest"]},
        )
    except jwt.ExpiredSignatureError:
        _error(status.HTTP_401_UNAUTHORIZED, "invalid session token")
    except jwt.ImmatureSignatureError:
        _error(status.HTTP_401_UNAUTHORIZED, "invalid session token")
    except HTTPException:
        raise
    except Exception:
        _error(status.HTTP_401_UNAUTHORIZED, "invalid session token")

    shop_domain = _normalize_shop_domain(payload.get("dest", ""))
    issuer_host = _normalize_issuer_host(payload.get("iss", ""))
    if not shop_domain or not issuer_host or issuer_host != shop_domain:
        _error(status.HTTP_401_UNAUTHORIZED, "invalid session token")

    return shop_domain


def get_session_shop_domain(shop_domain: str = Depends(verify_shopify_session_token)) -> str:
    return _normalize_shop_domain(shop_domain)


def get_current_shop(shop_domain: str = Depends(get_session_shop_domain)) -> str:
    return shop_domain


def ensure_shop_matches_token(shop_domain: str, token_shop_domain: str) -> None:
    if _normalize_shop_domain(shop_domain) != _normalize_shop_domain(token_shop_domain):
        _error(status.HTTP_403_FORBIDDEN, "shop mismatch")
