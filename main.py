from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from core.auth  import router as auth_router
from routers.requests import router as requests_router
from routers.dashboard import router as dashboard_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(requests_router)
app.include_router(dashboard_router)
