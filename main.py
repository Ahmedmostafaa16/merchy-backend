from time import perf_counter

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.config import FRONTEND_APP_URL
from core.auth import normalize_shop, router as auth_router
from core.session_token import verify_shopify_session_token
from core.webhooks import router as webhooks_router
from routers.requests import report_router, router as requests_router
from routers.dashboard import router as dashboard_router
from routers.api import router as api_router
from routers.notifications import router as notifications_router
from routers.po import router as po_router
from routers.legal import router as legal_router
from routers import jobs
from routers.billing import router as billing_router
from routers.location import router as location_router
app = FastAPI()




# ----------------------------
# CORS (required for Shopify iframe + frontend)
# ----------------------------

ALLOWED_ORIGINS = [
    "https://admin.shopify.com",
    FRONTEND_APP_URL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in ALLOWED_ORIGINS if origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if exc.status_code == 401:
        return JSONResponse(status_code=401, content={"error": "invalid session token"})
    if exc.status_code == 500:
        return JSONResponse(status_code=500, content={"error": "server error"})

    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, __: Exception):
    return JSONResponse(status_code=500, content={"error": "server error"})


# ----------------------------
# Shopify iframe embedding headers
# ----------------------------

@app.middleware("http")
async def add_shopify_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["Content-Security-Policy"] = (
        "frame-ancestors https://*.myshopify.com https://admin.shopify.com;"
    )

    return response


def _request_shop_label(request: Request) -> str:
    webhook_shop = request.headers.get("X-Shopify-Shop-Domain")
    if webhook_shop:
        return normalize_shop(webhook_shop)

    authorization = request.headers.get("Authorization")
    if authorization:
        try:
            return verify_shopify_session_token(authorization)
        except HTTPException:
            return "unknown"

    return "unknown"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = perf_counter()
    shop = _request_shop_label(request)
    try:
        response = await call_next(request)
    finally:
        elapsed_ms = (perf_counter() - started) * 1000
        print(f"[SHOP: {shop}] {request.method} {request.url.path} {elapsed_ms:.2f}ms")

    return response


# ----------------------------
# Routers
# ----------------------------

app.include_router(auth_router)
app.include_router(webhooks_router)
app.include_router(requests_router)
app.include_router(report_router)
app.include_router(dashboard_router)
app.include_router(api_router)
app.include_router(notifications_router)
app.include_router(jobs.router)
app.include_router(po_router)
app.include_router(legal_router)
app.include_router(billing_router)
app.include_router(location_router)
@app.get("/")
async def root():
    return {"status": "ok"}
