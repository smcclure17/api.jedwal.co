"""Main FastAPI application architecture."""

from contextlib import asynccontextmanager

import mangum
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from starlette.middleware.sessions import SessionMiddleware

from jedwal.api import api_router
from jedwal.common import sentry
from jedwal.config import settings

sentry.init()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")

    yield

    print(f"Shutting down {settings.app_name}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    # This produces faster JSON serialization and keeps UTF-8 by default.
    # For example, code snippets like <Image.../> are kept intact.
    default_response_class=ORJSONResponse
)


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.oauth_secret_token,
    same_site="none",
    https_only=True,
    domain="jedwal.co",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.client_base_url,
        settings.client_app_base_url,
        settings.api_base_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.debug else None,
        },
    )


app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


mangumHandler = mangum.Mangum(app, lifespan="off")


# See: https://github.com/Kludex/mangum/issues/307
# By default, Mangum redirects go to the underlying lambda/gateway
# URL, not the cloudfront/canonical domain. They use the "Host"
# header value, so we override that here with the correct domain.
def handler(event, context):
    event["multiValueHeaders"]["Host"] = ["api.jedwal.co"]
    return mangumHandler(event, context)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "jedwal.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
