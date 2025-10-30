"""API router configuration following Netflix Dispatch pattern."""

from fastapi import APIRouter

# Main API router
api_router = APIRouter()

# Health check endpoint
@api_router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Include feature module routers
# Following Dispatch pattern: each module has its own router that gets included here
# api_router.include_router(
#     items_router,
#     prefix="/items",
#     tags=["items"],
# )
