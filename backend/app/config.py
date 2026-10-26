"""Settings loaded from environment variables (or a .env file in backend/)."""
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv is optional
    pass


@dataclass(frozen=True)
class Settings:
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "")
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    paypal_base_url: str = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    paypal_webhook_id: str = os.getenv("PAYPAL_WEBHOOK_ID", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./hawker.db")
    seller_token: str = os.getenv("SELLER_TOKEN", "change-me")
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")


settings = Settings()
