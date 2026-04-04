from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core.config import APP_URL, SUPPORT_EMAIL

router = APIRouter(tags=["legal"])


def _base_url() -> str:
    return APP_URL.rstrip("/") if APP_URL else "https://example.com"


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy_policy() -> str:
    base_url = _base_url()
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Merchy Privacy Policy</title>
    <style>
      body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 16px; line-height: 1.6; color: #111827; }}
      h1, h2 {{ color: #0f172a; }}
      code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>Privacy Policy</h1>
    <p>Effective date: April 4, 2026</p>
    <p>Merchy is a Shopify embedded app that helps merchants review inventory, sales, replenishment suggestions, purchase orders, and stock alert settings.</p>

    <h2>What data we collect</h2>
    <p>Based on the current app scopes and code, the app may collect product data, inventory quantities, order-derived sales data, shop domain, installation status, purchase order records created in-app, and notification email settings.</p>

    <h2>Why we collect it</h2>
    <p>We use this data to calculate forecasting metrics, generate replenishment recommendations, save purchase orders, support notification workflows, and operate the app inside Shopify Admin.</p>

    <h2>How data is stored</h2>
    <p>The application stores operational app data in its database and may cache limited UI data in the merchant browser local storage. Sensitive credentials must be provided through environment variables, not hardcoded source files.</p>

    <h2>Sharing and selling</h2>
    <p>The app does not sell merchant data. Third-party delivery providers may process limited data only when needed to operate the service, such as email delivery for stock alerts.</p>

    <h2>Retention and deletion</h2>
    <p>The repository includes webhook handlers for <code>customers/data_request</code>, <code>customers/redact</code>, and <code>shop/redact</code>. Merchants should define and publish their final retention schedule before App Store submission. Current implementation notes are documented in <code>docs/data_retention_and_deletion.md</code>.</p>

    <h2>Contact</h2>
    <p>For privacy requests or support, contact <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.</p>

    <h2>Related links</h2>
    <p><a href="{base_url}/legal/terms">Terms of Service</a></p>
  </body>
</html>"""


@router.get("/legal/terms", response_class=HTMLResponse)
def terms_of_service() -> str:
    base_url = _base_url()
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Merchy Terms of Service</title>
    <style>
      body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 16px; line-height: 1.6; color: #111827; }}
      h1, h2 {{ color: #0f172a; }}
    </style>
  </head>
  <body>
    <h1>Terms of Service</h1>
    <p>Effective date: April 4, 2026</p>
    <p>These terms govern access to the Merchy Shopify app.</p>

    <h2>Use of the service</h2>
    <p>The app is intended for Shopify merchants to review inventory and sales data, generate replenishment suggestions, and manage purchase-order workflows.</p>

    <h2>Merchant responsibilities</h2>
    <p>Merchants are responsible for the accuracy of the data in their Shopify store and for reviewing any forecast or purchasing decision before acting on it.</p>

    <h2>Availability</h2>
    <p>The service may change as the app moves from custom-app assumptions toward public-app readiness. Review and support instructions are documented in the repository for submission preparation.</p>

    <h2>Support</h2>
    <p>Questions can be sent to <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.</p>

    <h2>Related links</h2>
    <p><a href="{base_url}/legal/privacy">Privacy Policy</a></p>
  </body>
</html>"""
