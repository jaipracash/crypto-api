"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the API and CoinGecko client."""

    coingecko_base_url: str = os.getenv(
        "COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3"
    ).rstrip("/")
    coingecko_api_key: str | None = os.getenv("COINGECKO_API_KEY") or None
    coingecko_api_plan: str = os.getenv("COINGECKO_API_PLAN", "demo").strip().lower()
    database_path: Path = Path(
        os.getenv("DATABASE_PATH", str(Path(__file__).parent / "crypto_research.db"))
    )
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "*").split(",")
        if origin.strip()
    )


settings = Settings()
