import os
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SCOPES = "read_products"
REDIRECT_URI = os.getenv("REDIRECT_URI")
