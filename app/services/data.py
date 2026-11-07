"""Shared data normalization, fallback, and mock-data helpers."""

import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.services.cache import response_cache
from app.services.coingecko import CoinGeckoClient, UpstreamFailure

logger = logging.getLogger(__name__)
MOCK_DIRECTORY = Path(__file__).parent.parent / "mock_data"


@dataclass(frozen=True)
class DataResult:
    """Data returned by a provider and the source used to obtain it."""

    value: Any
    source: str


class _TextExtractor(HTMLParser):
    """Extract readable text from upstream HTML descriptions."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(value: str | None) -> str:
    """Remove HTML markup and normalize whitespace."""
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def number(value: Any) -> float | None:
    """Convert optional upstream numeric values without failing on nulls."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def integer(value: Any) -> int | None:
    """Convert an optional upstream value to an integer."""
    numeric = number(value)
    return int(numeric) if numeric is not None else None


def scale_mock_market(row: dict[str, Any], rate: float = 83.0) -> dict[str, Any]:
    """Convert USD-denominated fixture values for another fiat currency."""
    converted = dict(row)
    for field in ("current_price", "market_cap", "total_volume"):
        if converted.get(field) is not None:
            converted[field] = float(converted[field]) * rate
    sparkline = converted.get("sparkline_in_7d")
    if isinstance(sparkline, dict):
        converted["sparkline_in_7d"] = {
            "price": [float(value) * rate for value in sparkline.get("price", [])]
        }
    return converted


def coin_item(raw: dict[str, Any], is_watchlisted: bool = False) -> dict[str, Any]:
    """Normalize a CoinGecko market/search row to the public coin item."""
    sparkline = raw.get("sparkline_in_7d") or {}
    values = sparkline.get("price") or []
    return {
        "id": str(raw.get("id", "")),
        "symbol": str(raw.get("symbol", "")).lower(),
        "name": str(raw.get("name", "")),
        "image": raw.get("image"),
        "rank": integer(raw.get("market_cap_rank", raw.get("rank"))),
        "price": number(raw.get("current_price", raw.get("price"))),
        "market_cap": number(raw.get("market_cap")),
        "volume_24h": number(raw.get("total_volume", raw.get("volume_24h"))),
        "change_1h_pct": number(
            raw.get("price_change_percentage_1h_in_currency", raw.get("change_1h_pct"))
        ),
        "change_24h_pct": number(
            raw.get("price_change_percentage_24h", raw.get("change_24h_pct"))
        ),
        "change_7d_pct": number(
            raw.get("price_change_percentage_7d_in_currency", raw.get("change_7d_pct"))
        ),
        "change_30d_pct": number(
            raw.get("price_change_percentage_30d_in_currency", raw.get("change_30d_pct"))
        ),
        "circulating_supply": number(raw.get("circulating_supply")),
        "total_supply": number(raw.get("total_supply")),
        "max_supply": number(raw.get("max_supply")),
        "sparkline_7d": [value for item in values if (value := number(item)) is not None],
        "is_watchlisted": is_watchlisted,
    }


def coin_detail(
    raw: dict[str, Any], is_watchlisted: bool = False, currency: str = "usd"
) -> dict[str, Any]:
    """Normalize a CoinGecko coin details response."""
    market = raw.get("market_data") or {}
    links = raw.get("links") or {}
    homepage = next((url for url in links.get("homepage", []) if url), None)
    return {
        **coin_item(
            {
                "id": raw.get("id"),
                "symbol": raw.get("symbol"),
                "name": raw.get("name"),
                "image": (raw.get("image") or {}).get("large")
                if isinstance(raw.get("image"), dict)
                else raw.get("image"),
                "market_cap_rank": raw.get("market_cap_rank"),
                "current_price": (market.get("current_price") or {}).get(currency),
                "market_cap": (market.get("market_cap") or {}).get(currency),
                "total_volume": (market.get("total_volume") or {}).get(currency),
                "price_change_percentage_24h": market.get(
                    "price_change_percentage_24h"
                ),
                "circulating_supply": market.get("circulating_supply"),
                "total_supply": market.get("total_supply"),
                "max_supply": market.get("max_supply"),
                "sparkline_in_7d": raw.get("sparkline_in_7d"),
            },
            is_watchlisted,
        ),
        "high_24h": number((market.get("high_24h") or {}).get(currency)),
        "low_24h": number((market.get("low_24h") or {}).get(currency)),
        "ath": number((market.get("ath") or {}).get(currency)),
        "ath_change_pct": number((market.get("ath_change_percentage") or {}).get(currency)),
        "ath_date": (market.get("ath_date") or {}).get(currency),
        "atl": number((market.get("atl") or {}).get(currency)),
        "atl_change_pct": number((market.get("atl_change_percentage") or {}).get(currency)),
        "atl_date": (market.get("atl_date") or {}).get(currency),
        "description": strip_html((raw.get("description") or {}).get("en")),
        "links": {"website": homepage, "whitepaper": links.get("whitepaper") or None},
    }


def read_mock(name: str) -> Any:
    """Load a checked-in JSON fallback file."""
    with (MOCK_DIRECTORY / name).open(encoding="utf-8") as mock_file:
        return json.load(mock_file)


async def provide(
    *,
    cache_key: str,
    ttl: int,
    client: CoinGeckoClient,
    fetch: Callable[[CoinGeckoClient], Awaitable[Any]],
    mock: Callable[[], Any] | None = None,
) -> DataResult:
    """Apply fresh-cache, live, stale-cache, then optional mock fallback ordering."""
    cached = response_cache.get_fresh(cache_key)
    if cached is not None:
        return DataResult(cached, "cache")
    upstream_error: UpstreamFailure | None = None
    try:
        value = await fetch(client)
        response_cache.set(cache_key, value, ttl)
        return DataResult(value, "live")
    except UpstreamFailure as exc:
        upstream_error = exc
        logger.warning("Upstream request failed %s: %s", exc.code, exc.message)
    except (TypeError, ValueError, KeyError) as exc:
        logger.exception("Could not normalize upstream response")
        upstream_error = UpstreamFailure("UPSTREAM_ERROR", "CoinGecko returned invalid data.")

    stale = response_cache.get_stale(cache_key)
    if stale is not None:
        return DataResult(stale, "cache")
    if mock is not None:
        try:
            return DataResult(mock(), "mock")
        except (OSError, ValueError, KeyError, TypeError):
            logger.exception("Mock fallback data could not be loaded")
    if upstream_error:
        raise upstream_error
    raise UpstreamFailure("UPSTREAM_ERROR", "No market data source is available.")
