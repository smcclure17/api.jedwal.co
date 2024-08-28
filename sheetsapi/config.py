from typing import List
import pydantic_settings
import starlette
import starlette.config


class EnvConstants(pydantic_settings.BaseSettings):
    """Environment constants.

    Constants should be set in .env file with keys matching variable names
    at root of project (or set as environment variables, e.g., via CloudFormation).
    """

    SHEETS_API_TABLE: str

    ANALYTICS_TABLE: str

    AWS_REGION: str = "us-east-1"

    GOOGLE_CLIENT_ID: str

    GOOGLE_CLIENT_SECRET: str

    OAUTH_SECRET_TOKEN: str

    SENTRY_DSN: str

    ENVIRONMENT: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class Config:
    Constants: EnvConstants = None

    @staticmethod
    def init():
        Config.Constants = EnvConstants()

    @staticmethod
    def to_starlette_config() -> starlette.config.Config:
        """Converts the configuration to a Starlette configuration object.

        Used because starlette middleware requires a Starlette config object.

        Returns:
            Starlette config object with environment constants from the app config.
        """
        return starlette.config.Config(environ=Config.Constants.model_dump())
