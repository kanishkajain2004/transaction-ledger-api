from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ledger:ledger@localhost:5433/ledger"
    test_database_url: str = "postgresql+psycopg://ledger:ledger@localhost:5433/ledger_test"


settings = Settings()
