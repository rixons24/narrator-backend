import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import scripts, parsing

app = FastAPI(title="Narrator API", version="1.0.0")

# CORS_ALLOWED_ORIGINS: comma-separated list of EXACT origins (still
# supported for anything outside *.lovable.app, e.g. a future custom domain).
_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default port, used by the Lovable app locally
]

# CORS_ORIGIN_REGEX: matches any origin, e.g. any *.lovable.app subdomain —
# covers both the published domain (narrative-forge-audio.lovable.app) and
# Lovable's preview domains (id-preview--<project-id>.lovable.app), which
# are DIFFERENT hosts and would otherwise need to be added individually
# every time. Overridable via env var; defaults to *.lovable.app.
origin_regex = os.environ.get("CORS_ORIGIN_REGEX", r"https://.*\.lovable\.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scripts.router)
app.include_router(parsing.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
