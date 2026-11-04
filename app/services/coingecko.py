"""Async CoinGecko client and shared upstream error types."""

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class UpstreamFailure(Exception):
    """Represent a failed CoinGecko request in a transport-independent way."""

    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CoinGeckoClient:
    """CoinGecko HTTP client with timeouts and one network-error retry."""

    def __init__(self) -> None:
        headers = {"accept": "application/json"}
        if settings.coingecko_api_key:
            headers["x-cg-demo-api-key"] = settings.coingecko_api_key
        self._client = httpx.AsyncClient(
            base_url=settings.coingecko_base_url,
            headers=headers,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch decoded JSON, retrying one time after a network failure."""
        for attempt in range(2):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code == 429:
                    raise UpstreamFailure(
                        "UPSTREAM_RATE_LIMITED",
                        "CoinGecko rate limit reached.",
                        429,
                    )
                if response.status_code == 404:
                    raise UpstreamFailure(
                        "COIN_NOT_FOUND", "The requested coin was not found.", 404
                    )
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise UpstreamFailure(
                        "UPSTREAM_ERROR", "CoinGecko returned invalid JSON."
                    ) from exc
            except UpstreamFailure:
                raise
            except httpx.RequestError as exc:
                logger.warning("CoinGecko network request failed (attempt %s): %s", attempt + 1, exc)
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                raise UpstreamFailure(
                    "UPSTREAM_ERROR", "CoinGecko could not be reached."
                ) from exc
            except httpx.HTTPStatusError as exc:
                logger.warning("CoinGecko returned HTTP %s", exc.response.status_code)
                raise UpstreamFailure(
                    "UPSTREAM_ERROR", "CoinGecko returned an unsuccessful response."
                ) from exc
        raise UpstreamFailure("UPSTREAM_ERROR", "CoinGecko could not be reached.")
