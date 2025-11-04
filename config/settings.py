import os
from typing import List, Optional
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação"""

    # App
    app_name: str = Field(default="Telegram Finance Bot")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Telegram
    telegram_bot_token: str = Field(..., description="Token do bot do Telegram")
    telegram_webhook_url: Optional[str] = Field(default=None, description="URL do webhook")

    # OpenAI
    openai_api_key: str = Field(..., description="Chave da API OpenAI")
    openai_model: str = Field(default="gpt-3.5-turbo")

    # Google Sheets
    google_sheets_spreadsheet_id: str = Field(..., description="ID da planilha Google")
    google_credentials_file: str = Field(default="credentials/google_service_account.json")

    # Database
    database_url: str = Field(default="sqlite:///./finance_bot.db")

    # Categories
    default_categories: List[str] = Field(
        default=["Alimentação", "Transporte", "Saúde", "Lazer", "Casa", "Outros"]
    )

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """Obter configurações (cached)"""
    return Settings()