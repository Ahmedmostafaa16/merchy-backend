import os
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SCOPES = "read_products,read_orders"
REDIRECT_URI = os.getenv("REDIRECT_URI")
SHOPIFY_API_KEY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01")
