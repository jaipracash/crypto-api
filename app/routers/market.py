"""Global market, trending, and price movers endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from app.schemas import Currency, GlobalMarket, MoversResponse, TrendingResponse
from app.services.coingecko import CoinGeckoClient
from app.services.data import coin_item, number, provide, read_mock, scale_mock_market

router = APIRouter(prefix="/market", tags=["market"])


def _client(request: Request) -> CoinGeckoClient:
    return request.app.state.coingecko


def _key(endpoint: str, **params: Any) -> str:
    return f"{endpoint}:{json.dumps(params, sort_keys=True, separators=(',', ':'))}"


@router.get("/global", response_model=GlobalMarket)
async def global_market(
    request: Request,
    response: Response,
    currency: Currency = Query("usd"),
) -> dict[str, Any]:
    """Return aggregate market statistics."""
    result = await provide(
        cache_key=_key("global", currency=currency),
        ttl=120,
        client=_client(request),
        fetch=lambda client: client.get("/global"),
        mock=lambda: read_mock("global.json"),
    )
    raw = result.value.get("data", result.value)
    market_cap = raw.get("total_market_cap") or {}
    volume = raw.get("total_volume") or {}
    dominance = raw.get("market_cap_percentage") or {}
    total_cap = number(market_cap.get(currency))
    btc = number(dominance.get("btc"))
    eth = number(dominance.get("eth"))
    response.headers["X-Data-Source"] = result.source
    return {
        "total_market_cap": total_cap,
        "total_volume_24h": number(volume.get(currency)),
        "market_cap_change_24h_pct": number(raw.get("market_cap_change_percentage_24h_usd")),
        "btc_dominance": btc,
        "eth_dominance": eth,
        "others_dominance": max(0.0, 100.0 - btc - eth) if btc is not None and eth is not None else None,
        "active_coins": raw.get("active_cryptocurrencies"),
    }


@router.get("/trending", response_model=TrendingResponse)
async def trending(
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Return CoinGecko's current trending coins."""
    result = await provide(
        cache_key=_key("trending"),
        ttl=300,
        client=_client(request),
        fetch=lambda client: client.get("/search/trending"),
        mock=lambda: read_mock("trending.json"),
    )
    rows = result.value.get("coins", [])
    items = []
    for entry in rows:
        item = entry.get("item", entry)
        items.append(
            {
                "id": str(item.get("id", "")),
                "symbol": str(item.get("symbol", "")).lower(),
                "name": str(item.get("name", "")),
                "image": item.get("large") or item.get("thumb") or item.get("image"),
                "rank": item.get("market_cap_rank", item.get("rank")),
                "price_btc": number(item.get("price_btc")),
            }
        )
    response.headers["X-Data-Source"] = result.source
    return {"items": items}


@router.get("/movers", response_model=MoversResponse)
async def movers(
    request: Request,
    response: Response,
    limit: int = Query(5, ge=1, le=50),
    currency: Currency = Query("usd"),
) -> dict[str, Any]:
    """Compute top gainers and losers from the top 250 by market cap."""
    result = await provide(
        cache_key=_key("movers", limit=limit, currency=currency),
        ttl=60,
        client=_client(request),
        fetch=lambda client: client.get(
            "/coins/markets",
            {
                "vs_currency": currency,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
        ),
        mock=lambda: read_mock("coins.json"),
    )
    rows = result.value
    if currency == "inr" and result.source == "mock":
        rows = [scale_mock_market(row) for row in rows]
    valid = [row for row in rows if row.get("price_change_percentage_24h") is not None]
    gainers = sorted(valid, key=lambda row: float(row["price_change_percentage_24h"]), reverse=True)[:limit]
    losers = sorted(valid, key=lambda row: float(row["price_change_percentage_24h"]))[:limit]
    response.headers["X-Data-Source"] = result.source
    return {
        "gainers": [coin_item(row) for row in gainers],
        "losers": [coin_item(row) for row in losers],
    }
