from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.auth import router as auth_router
from core.webhooks import router as webhooks_router
from routers.requests import router as requests_router
from routers.dashboard import router as dashboard_router
from routers.api import router as api_router


app = FastAPI()


# ----------------------------
# CORS (required for Shopify iframe + frontend)
# ----------------------------

ALLOWED_ORIGINS = [
    "https://admin.shopify.com",
    "https://*.myshopify.com",
    "https://merchy-frontend-nwbb.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if exc.status_code == 401:
        return JSONResponse(status_code=401, content={"error": "invalid session token"})
    if exc.status_code == 403:
        return JSONResponse(status_code=403, content={"error": "shop mismatch"})
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


# ----------------------------
# Routers
# ----------------------------

app.include_router(auth_router)
app.include_router(webhooks_router)
app.include_router(requests_router)
app.include_router(dashboard_router)
app.include_router(api_router)


# ----------------------------
# Root health check
# ----------------------------

@app.get("/")
def health():
    return {"status": "Merchy backend running"}
