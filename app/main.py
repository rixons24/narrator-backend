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

# CORS_ORIGIN_REGEX: matches any *.lovable.app subdomain (covers both the
# published domain and Lovable's preview domains, which are different
# hosts) AND any http://localhost:<port>. The localhost part matters
# specifically because the local dev server's port isn't fixed — it was
# assumed to be Vite's default 5173 early on, then turned out to actually
# run on 8080 once someone actually started it. Matching any port here
# means a future port change can't silently break local testing again the
# same way. Overridable via env var if either assumption ever needs to
# change.
origin_regex = os.environ.get(
    "CORS_ORIGIN_REGEX", r"https://.*\.lovable\.app|http://localhost:\d+"
)

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
