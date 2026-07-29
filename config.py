import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # DSS env variable contains the database connection string or connection params
    dss: str = Field(default="", alias="DSS")
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    tz: str = Field(default="Europe/Berlin", alias="TZ")

    # Fallbacks from .env-dev
    postgres_password: str = Field(default="einkaufsliste-dev-pass", alias="POSTGRES_PASSWORD")
    postgres_user: str = Field(default="einkaufsliste-dev", alias="POSTGRES_USER")
    postgres_db: str = Field(default="einkfaufsliste-dev", alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=10000, alias="POSTGRES_PORT")

    model_config = SettingsConfigDict(
        env_file=".env-dev",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True
    )

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def database_dsn(self) -> str:
        if self.dss:
            return self.dss
        return f"host={self.postgres_host} port={self.postgres_port} user={self.postgres_user} password={self.postgres_password} dbname={self.postgres_db} sslmode=disable"

settings = Settings()

