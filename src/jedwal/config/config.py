"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Jedwal API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str

    # API
    allowed_origins: list[str] = ["*"]

    # AWS Configuration
    aws_region: str = "us-east-1"
    dynamodb_endpoint_url: str | None = None  # Only for local development

    # DynamoDB Tables
    sheets_api_table: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    oauth_secret_token: str

    # Sentry
    sentry_dsn: str

    # Stripe
    stripe_webhook_secret: str
    stripe_subscription_price_id: str
    stripe_usage_based_price_id: str
    stripe_secret_key: str

    # URLs
    api_base_url: str
    client_base_url: str
    client_app_base_url: str

    # Cookies
    cookie_allowed_domain: str

    # CloudFront
    cloudfront_distribution_id: str

    # Encryption
    encryption_key_id: str

    # Email
    emails_enabled: bool = True

    # Free tier limits
    free_tier_request_limit: int = 5_000

    # Testing
    test_data_refresh_info: str = ""

    # Webhooks & Queues
    webhook_queue_url: str

    # Image Storage
    image_storage_bucket: str
    image_storage_bucket_url: str


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
