from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import FRONTEND_APP_URL
from core.auth import router as auth_router
from core.webhooks import router as webhooks_router
from routers.requests import router as requests_router
from routers.dashboard import router as dashboard_router
from routers.api import router as api_router
from routers.notifications import router as notifications_router
from routers.po import router as po_router
from routers.legal import router as legal_router
from routers import jobs

app = FastAPI()

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


def _resolve_frontend_build_dir() -> Path | None:
    candidates = [
        PROJECT_ROOT / "Frontend" / "merchy" / "build",
        APP_DIR / "Frontend" / "merchy" / "build",
        PROJECT_ROOT / "build",
        APP_DIR / "build",
        Path.cwd() / "Frontend" / "merchy" / "build",
        Path.cwd() / "build",
    ]

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate

    return None


FRONTEND_BUILD_DIR = _resolve_frontend_build_dir()
FRONTEND_INDEX_FILE = FRONTEND_BUILD_DIR / "index.html" if FRONTEND_BUILD_DIR else None




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
    allow_origin_regex=r"^https:\/\/[a-zA-Z0-9-]+\.myshopify\.com$",
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
app.include_router(notifications_router)
app.include_router(jobs.router)
app.include_router(po_router)
app.include_router(legal_router)

if FRONTEND_BUILD_DIR and (FRONTEND_BUILD_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_BUILD_DIR / "static"), name="frontend-static")

@app.get("/")
async def root():
    if not FRONTEND_INDEX_FILE or not FRONTEND_INDEX_FILE.exists():
        return JSONResponse(
            status_code=503,
            content={"error": "frontend build not found"},
        )
    return FileResponse(FRONTEND_INDEX_FILE)


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if not FRONTEND_BUILD_DIR or not FRONTEND_INDEX_FILE or not FRONTEND_INDEX_FILE.exists():
        return JSONResponse(
            status_code=503,
            content={"error": "frontend build not found"},
        )

    candidate = FRONTEND_BUILD_DIR / full_path

    if full_path and candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    return FileResponse(FRONTEND_INDEX_FILE)
