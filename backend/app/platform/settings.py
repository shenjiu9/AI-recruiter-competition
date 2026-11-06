from datetime import date

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+psycopg://recruiter:recruiter@localhost:5432/recruiter"
    signing_key: str
    encryption_key: str
    dev_auth_enabled: bool = False
    dev_login_password: str = ""
    position_worker_enabled: bool = True
    conversation_worker_enabled: bool = True
    ai_worker_enabled: bool = False
    dify_base_url: str = ""
    dify_api_keys: dict[str, SecretStr] = {}
    ai_timeout_seconds: int = Field(default=45, ge=1, le=120)
    candidate_portal_url: str = "http://localhost:5175"
    position_holidays: list[date] = []
    position_workdays: list[date] = []
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ]

    @model_validator(mode="after")
    def secure_configuration(self):
        if self.dify_base_url:
            from urllib.parse import urlparse

            url = urlparse(self.dify_base_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("DIFY_BASE_URL must be an HTTP(S) service URL without credentials")
            if self.environment != "development" and url.scheme != "https":
                raise ValueError("Production Dify requires HTTPS")
        if len(self.signing_key) < 32:
            raise ValueError("SIGNING_KEY must contain at least 32 characters")
        if self.dev_auth_enabled and (
            self.environment != "development" or not self.dev_login_password
        ):
            raise ValueError("Development authentication requires development mode and a password")
        return self
