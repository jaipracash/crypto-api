"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db
from app.config import settings
from app.routers import coins, market, prices, watchlist
from app.services.coingecko import CoinGeckoClient, UpstreamFailure

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize persistent storage and manage the upstream HTTP client."""
    db.initialize_database(settings.database_path)
    application.state.coingecko = CoinGeckoClient()
    try:
        yield
    finally:
        await application.state.coingecko.close()


app = FastAPI(
    title="Crypto Research API",
    description="CoinGecko-backed market research API with per-device watchlists.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Source"],
)
app.include_router(coins.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")


@app.exception_handler(UpstreamFailure)
async def upstream_failure_handler(
    request: Request, exc: UpstreamFailure
) -> JSONResponse:
    """Render upstream and domain errors in one stable response format."""
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI validation failures to the documented 400 format."""
    del request
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "INVALID_PARAMS",
                "message": details or "Invalid request parameters.",
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Keep framework-generated HTTP errors in the same JSON envelope."""
    del request
    code = "COIN_NOT_FOUND" if exc.status_code == 404 else "INVALID_PARAMS"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return a non-sensitive unified error."""
    logger.error(
        "Unhandled API error for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "UPSTREAM_ERROR", "message": "The request could not be completed."}},
    )


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Report that the API process is responsive."""
    return {"status": "ok"}
