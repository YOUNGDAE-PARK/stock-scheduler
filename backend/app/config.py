from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)

    database_url: str = Field(default="sqlite:///./stock_scheduler.db", alias="DATABASE_URL")
    codex_bin: str = Field(default="/usr/bin/codex", alias="CODEX_BIN")
    cors_allow_origins: str = Field(default="", alias="CORS_ALLOW_ORIGINS")
    notification_mode: str = Field(default="dry-run", alias="NOTIFICATION_MODE")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    kis_env: str = Field(default="virtual", alias="KIS_ENV")
    kis_grant_type: str = Field(default="client_credentials", alias="KIS_GRANT_TYPE")
    kis_real_app_key: str = Field(default="", alias="KIS_REAL_APP_KEY")
    kis_real_app_secret: str = Field(default="", alias="KIS_REAL_APP_SECRET")
    kis_virtual_app_key: str = Field(default="", alias="KIS_VIRTUAL_APP_KEY")
    kis_virtual_app_secret: str = Field(default="", alias="KIS_VIRTUAL_APP_SECRET")
    kis_real_base_url: str = Field(
        default="https://openapi.koreainvestment.com:9443",
        alias="KIS_REAL_BASE_URL",
    )
    kis_virtual_base_url: str = Field(
        default="https://openapivts.koreainvestment.com:29443",
        alias="KIS_VIRTUAL_BASE_URL",
    )

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL is implemented in the local v1 scaffold")
        return Path(self.database_url.replace("sqlite:///", "", 1))

    @property
    def kis_mode(self) -> str:
        value = self.kis_env.strip().lower()
        if value in {"real", "prod", "production", "live"}:
            return "real"
        if value in {"virtual", "mock", "paper", "simulation", "vts"}:
            return "virtual"
        raise ValueError("KIS_ENV must be one of: real, prod, production, live, virtual, mock, paper, simulation, vts")

    @property
    def kis_base_url(self) -> str:
        if self.kis_mode == "real":
            return self.kis_real_base_url.rstrip("/")
        return self.kis_virtual_base_url.rstrip("/")

    @property
    def kis_app_key(self) -> str:
        if self.kis_mode == "real":
            return self.kis_real_app_key
        return self.kis_virtual_app_key

    @property
    def kis_app_secret(self) -> str:
        if self.kis_mode == "real":
            return self.kis_real_app_secret
        return self.kis_virtual_app_secret

    @property
    def kis_token_url(self) -> str:
        return f"{self.kis_base_url}/oauth2/tokenP"


@lru_cache
def get_settings() -> Settings:
    return Settings()
