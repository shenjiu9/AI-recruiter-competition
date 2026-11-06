from datetime import date

from pydantic import model_validator
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
        if len(self.signing_key) < 32:
            raise ValueError("SIGNING_KEY must contain at least 32 characters")
        if self.dev_auth_enabled and (
            self.environment != "development" or not self.dev_login_password
        ):
            raise ValueError("Development authentication requires development mode and a password")
        return self
