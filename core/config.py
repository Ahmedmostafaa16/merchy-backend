import os
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

load_dotenv()

def _strip_trailing_slash(value: str) -> str:
    return value.rstrip("/") if value else ""


def _base_url_from_redirect_uri(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SCOPES = os.getenv("SCOPES", "read_products,read_orders")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOPIFY_BILLING_TEST = os.getenv("SHOPIFY_BILLING_TEST", "false").strip().lower() == "true"
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL") or os.getenv("ZOHO_EMAIL") or "support@example.com"
APP_URL = _strip_trailing_slash(os.getenv("APP_URL", ""))
BACKEND_PUBLIC_URL = APP_URL or _base_url_from_redirect_uri(REDIRECT_URI or "")
FRONTEND_APP_URL = _strip_trailing_slash(os.getenv("FRONTEND_APP_URL", "http://localhost:3000"))
CRON_SECRET = os.getenv("CRON_SECRET", "")
