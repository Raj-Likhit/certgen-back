import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .api.endpoints import router
from .core import config

from .core.logging_config import logger

app = FastAPI(title="Cert-Gen-V2 API", version="2.0.0")

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self' *; connect-src 'self' *; script-src 'self' 'unsafe-inline' 'unsafe-eval' *; style-src 'self' 'unsafe-inline' *; font-src 'self' data: *; img-src 'self' data: *;"
    return response

from .core.limiter import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration - Split deployment setup
allowed_origins = [
    "http://localhost:5173",  # Local development
    "https://certgen-front.vercel.app",  # Production frontend (old)
    "https://sih2026-mecs-cert.vercel.app",  # Production frontend (new)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://(certgen-front|sih2026-mecs-cert).*\.vercel\.app$",  # All frontend preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assets
os.makedirs("assets", exist_ok=True)
# Mount with a wrapper to ensure CORS headers for local font loading
@app.middleware("http")
async def static_cors_middleware(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response

app.mount("/assets", StaticFiles(directory=config.ASSETS_DIR), name="assets")

@app.on_event("startup")
async def startup_event():
    try:
        # Industrial Optimization: Pre-load templates and fonts into RAM
        from .services.asset_manager import initialize_assets
        initialize_assets()
        logger.info("Successfully initialized production assets")
    except Exception as e:
        logger.error(f"FATAL: Asset initialization failed: {str(e)}")
        # We don't raise here so the app can start and we can use the debug endpoint

# Routes - For Vercel serverless deployment, mount at root
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
