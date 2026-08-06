import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import scripts, parsing

app = FastAPI(title="Narrator API", version="1.0.0")

# CORS_ALLOWED_ORIGINS: comma-separated list, set in Railway env vars once
# the Lovable app's real domain is known. Defaults cover local dev.
_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default port, used by the Lovable app
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scripts.router)
app.include_router(parsing.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
