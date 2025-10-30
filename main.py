"""Entry point for running the application."""

import uvicorn


def main():
    """Run the FastAPI application."""
    uvicorn.run(
        "jedwal.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
