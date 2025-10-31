"""Main FastAPI application following Netflix Dispatch architecture."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from jedwal.api import api_router
from jedwal.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")

    yield

    # Shutdown logic
    print(f"Shutting down {settings.app_name}")


# Create the main FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)


# Session middleware for authentication (must be before CORS)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.oauth_secret_token,
    same_site="none",
    https_only=True,
    # domain="jedwal.co",
)

# CORS middleware for cross-origin requests
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


# Include the API router
app.include_router(api_router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": f"/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "jedwal.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
