"""Per-device watchlist endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Header, Path, Query, Request, Response

from app import db
from app.config import settings
from app.schemas import Currency, WatchlistMutation, WatchlistResponse
from app.services.coingecko import CoinGeckoClient, UpstreamFailure
from app.services.data import coin_item, provide, read_mock, scale_mock_market

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _device_id(device_id: str) -> str:
    value = device_id.strip()
    if not value or len(value) > 128:
        raise UpstreamFailure("INVALID_PARAMS", "X-Device-ID must be 1-128 characters.", 400)
    return value


def _key(ids: list[str], currency: Currency) -> str:
    return "watchlist:" + json.dumps(
        {"ids": ids, "currency": currency}, sort_keys=True, separators=(",", ":")
    )


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    request: Request,
    response: Response,
    currency: Currency = Query("usd"),
    x_device_id: str = Header(..., alias="X-Device-ID", min_length=1, max_length=128),
) -> dict[str, Any]:
    """Return the device's watchlisted coins with live market data."""
    device_id = _device_id(x_device_id)
    ids = db.list_watchlist(settings.database_path, device_id)
    if not ids:
        response.headers["X-Data-Source"] = "live"
        return {"count": 0, "items": []}
    client: CoinGeckoClient = request.app.state.coingecko
    result = await provide(
        cache_key=_key(ids, currency),
        ttl=60,
        client=client,
        fetch=lambda upstream: upstream.get(
            "/coins/markets",
            {
                "vs_currency": currency,
                "ids": ",".join(ids),
                "order": "market_cap_desc",
                "per_page": min(len(ids), 250),
                "page": 1,
                "sparkline": "true",
                "price_change_percentage": "24h",
            },
        ),
        mock=lambda: [
            row for row in read_mock("coins.json") if row.get("id") in set(ids)
        ],
    )
    rows = result.value
    if not isinstance(rows, list):
        rows = []
    if currency == "inr" and result.source == "mock":
        rows = [scale_mock_market(row) for row in rows]
    indexed = {str(row.get("id")): row for row in rows}
    items = [coin_item(indexed[coin_id], True) for coin_id in ids if coin_id in indexed]
    response.headers["X-Data-Source"] = result.source
    return {"count": len(items), "items": items}


@router.post("/{coin_id}", response_model=WatchlistMutation)
async def add_watchlist(
    response: Response,
    coin_id: str = Path(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$"),
    x_device_id: str = Header(..., alias="X-Device-ID", min_length=1, max_length=128),
) -> dict[str, Any]:
    """Add a coin to the watchlist; repeated additions are harmless."""
    db.add_to_watchlist(settings.database_path, _device_id(x_device_id), coin_id)
    response.headers["X-Data-Source"] = "live"
    return {"coin_id": coin_id, "watchlisted": True}


@router.delete("/{coin_id}", response_model=WatchlistMutation)
async def delete_watchlist(
    response: Response,
    coin_id: str = Path(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$"),
    x_device_id: str = Header(..., alias="X-Device-ID", min_length=1, max_length=128),
) -> dict[str, Any]:
    """Remove a coin from the watchlist; repeated deletions are harmless."""
    db.remove_from_watchlist(settings.database_path, _device_id(x_device_id), coin_id)
    response.headers["X-Data-Source"] = "live"
    return {"coin_id": coin_id, "watchlisted": False}
