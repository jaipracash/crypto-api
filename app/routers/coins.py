"""Coin list, details, chart, and search endpoints."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Path, Query, Request, Response

from app import db
from app.config import settings
from app.schemas import (
    ChartResponse,
    CoinDetail,
    CoinListResponse,
    CoinOrder,
    Currency,
    SearchResponse,
)
from app.services.coingecko import CoinGeckoClient, UpstreamFailure
from app.services.data import (
    coin_detail,
    coin_item,
    integer,
    number,
    provide,
    read_mock,
    scale_mock_market,
)

router = APIRouter(tags=["coins"])
CHART_DAYS = {1, 7, 30, 90, 365}
logger = logging.getLogger(__name__)


def _client(request: Request) -> CoinGeckoClient:
    return request.app.state.coingecko


def _key(endpoint: str, **params: Any) -> str:
    """Build deterministic cache keys including all request parameters."""
    return f"{endpoint}:{json.dumps(params, sort_keys=True, separators=(',', ':'))}"


def _device(device_id: str | None) -> str | None:
    if device_id is not None and (not device_id.strip() or len(device_id) > 128):
        from app.services.coingecko import UpstreamFailure

        raise UpstreamFailure("INVALID_PARAMS", "X-Device-ID must be 1-128 characters.", 400)
    return device_id.strip() if device_id else None


@router.get("/coins", response_model=CoinListResponse)
async def list_coins(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=250),
    order: CoinOrder = Query("market_cap_desc"),
    currency: Currency = Query("usd"),
    category: str | None = Query(None, min_length=1, max_length=100),
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
) -> dict[str, Any]:
    """Return a paginated, sortable market list."""
    device_id = _device(x_device_id)
    key = _key(
        "coins",
        page=page,
        per_page=per_page,
        order=order,
        currency=currency,
        category=category,
    )
    upstream_per_page = min(per_page + 1, 250)
    result = await provide(
        cache_key=key,
        ttl=60,
        client=_client(request),
        fetch=lambda client: client.get(
            "/coins/markets",
            {
                "vs_currency": currency,
                "order": order,
                "per_page": upstream_per_page,
                "page": page,
                "sparkline": "true",
                "price_change_percentage": "1h,24h,7d,30d",
                **({"category": category} if category is not None else {}),
            },
        ),
        mock=lambda: read_mock("coins.json"),
    )
    rows = result.value
    if currency == "inr" and result.source == "mock":
        rows = [scale_mock_market(row) for row in rows]
    if result.source == "mock":
        rows = _sort_mock_rows(rows, order)
        data = rows[(page - 1) * per_page : page * per_page + 1]
    else:
        data = rows
    has_more = len(data) > per_page
    data = data[:per_page]
    watched = set(db.list_watchlist(settings.database_path, device_id)) if device_id else set()
    items = [coin_item(row, str(row.get("id")) in watched) for row in data]
    response.headers["X-Data-Source"] = result.source
    return {
        "page": page,
        "per_page": per_page,
        "has_more": has_more,
        "data_source": result.source,
        "items": items,
    }


def _sort_mock_rows(rows: list[dict[str, Any]], order: CoinOrder) -> list[dict[str, Any]]:
    """Apply supported market ordering to the checked-in mock coin list."""
    sort_fields: dict[str, tuple[str, bool]] = {
        "market_cap_desc": ("market_cap", True),
        "market_cap_asc": ("market_cap", False),
        "volume_desc": ("total_volume", True),
        "volume_asc": ("total_volume", False),
        "price_desc": ("current_price", True),
        "price_asc": ("current_price", False),
        "change_desc": ("price_change_percentage_24h", True),
        "change_asc": ("price_change_percentage_24h", False),
    }
    field, reverse = sort_fields[order]
    return sorted(rows, key=lambda row: number(row.get(field)) or 0, reverse=reverse)


@router.get("/coins/{coin_id}", response_model=CoinDetail)
async def get_coin(
    request: Request,
    response: Response,
    coin_id: str = Path(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$"),
    currency: Currency = Query("usd"),
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
) -> dict[str, Any]:
    """Return market metrics and descriptive data for one coin."""
    device_id = _device(x_device_id)
    key = _key("coin_detail", coin_id=coin_id, currency=currency)
    result = await provide(
        cache_key=key,
        ttl=60,
        client=_client(request),
        fetch=lambda client: client.get(
            f"/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "true",
            },
        ),
        mock=lambda: _mock_detail(coin_id),
    )
    watched = bool(device_id and coin_id in db.list_watchlist(settings.database_path, device_id))
    detail = _normalize_detail(result.value, result.source, currency, watched)
    response.headers["X-Data-Source"] = result.source
    return detail


def _mock_detail(coin_id: str) -> dict[str, Any]:
    rows = read_mock("coins.json")
    row = next((coin for coin in rows if coin["id"] == coin_id), None)
    if row is None:
        from app.services.coingecko import UpstreamFailure

        raise UpstreamFailure("COIN_NOT_FOUND", "The requested coin was not found.", 404)
    detail = read_mock("coin_details.json").get(coin_id, {})
    return {"market_row": row, "detail": detail}


def _normalize_detail(
    raw: dict[str, Any], source: str, currency: Currency, watched: bool
) -> dict[str, Any]:
    if source == "mock":
        row = raw["market_row"]
        details = raw["detail"]
        rate = 83.0 if currency == "inr" else 1.0
        market_row = scale_mock_market(row, rate)
        item = coin_item(market_row, watched)
        detail_market = {
            key: value * rate if isinstance(value, (int, float)) else value
            for key, value in details.items()
            if key not in {"description", "website", "whitepaper"}
        }
        return {
            **item,
            "high_24h": detail_market.get("high_24h"),
            "low_24h": detail_market.get("low_24h"),
            "ath": detail_market.get("ath"),
            "ath_change_pct": details.get("ath_change_pct"),
            "ath_date": details.get("ath_date"),
            "atl": detail_market.get("atl"),
            "atl_change_pct": details.get("atl_change_pct"),
            "atl_date": details.get("atl_date"),
            "description": details.get("description", ""),
            "links": {
                "website": details.get("website"),
                "whitepaper": details.get("whitepaper"),
            },
        }
    return coin_detail(raw, watched, currency)


@router.get("/coins/{coin_id}/chart", response_model=ChartResponse)
async def get_coin_chart(
    request: Request,
    response: Response,
    coin_id: str = Path(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$"),
    days: int = Query(7),
    currency: Currency = Query("usd"),
) -> dict[str, Any]:
    """Return historical prices and summary statistics."""
    if days not in CHART_DAYS:
        from app.services.coingecko import UpstreamFailure

        raise UpstreamFailure("INVALID_PARAMS", "days must be one of 1, 7, 30, 90, or 365.", 400)
    key = _key(
        "chart",
        coin_id=coin_id,
        days=days,
        currency=currency,
        native_ohlc=True,
    )
    async def fetch_chart(client: CoinGeckoClient) -> dict[str, Any]:
        chart = await client.get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": currency, "days": days},
        )
        try:
            chart["ohlc"] = await client.get(
                f"/coins/{coin_id}/ohlc",
                {"vs_currency": currency, "days": days},
            )
        except UpstreamFailure as error:
            logger.warning(
                "Native OHLC unavailable for %s (%s days): %s",
                coin_id,
                days,
                error.code,
            )
            chart["ohlc"] = []
        return chart

    result = await provide(
        cache_key=key,
        ttl=300,
        client=_client(request),
        fetch=fetch_chart,
    )
    points = result.value.get("prices", [])
    prices: list[tuple[int, float]] = []
    for point in points:
        if isinstance(point, list) and len(point) >= 2:
            timestamp, price = integer(point[0]), number(point[1])
            if timestamp is not None and price is not None:
                prices.append((timestamp, price))
    raw_market_caps = result.value.get("market_caps", [])
    market_caps: list[tuple[int, float]] = []
    for point in raw_market_caps:
        if isinstance(point, list) and len(point) >= 2:
            timestamp, market_cap = integer(point[0]), number(point[1])
            if timestamp is not None and market_cap is not None:
                market_caps.append(
                    (
                        timestamp,
                        market_cap,
                    )
                )
    ohlc: list[tuple[int, float, float, float, float]] = []
    for point in result.value.get("ohlc", []):
        if isinstance(point, list) and len(point) >= 5:
            timestamp = integer(point[0])
            open_price, high, low, close = [number(point[index]) for index in range(1, 5)]
            if (
                timestamp is not None
                and open_price is not None
                and high is not None
                and low is not None
                and close is not None
            ):
                ohlc.append(
                    (
                        timestamp,
                        open_price,
                        high,
                        low,
                        close,
                    )
                )
    values = [price for _, price in prices]
    change_pct = ((values[-1] - values[0]) / values[0] * 100) if len(values) > 1 and values[0] else None
    response.headers["X-Data-Source"] = result.source
    return {
        "coin_id": coin_id,
        "days": days,
        "currency": currency,
        "prices": prices,
        "market_caps": market_caps,
        "ohlc": ohlc,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "change_pct": change_pct,
    }


@router.get("/search", response_model=SearchResponse)
async def search_coins(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=2, max_length=100),
) -> dict[str, Any]:
    """Search coins by name or ticker."""
    query = q.strip()
    if len(query) < 2:
        from app.services.coingecko import UpstreamFailure

        raise UpstreamFailure("INVALID_PARAMS", "Search query must contain at least 2 characters.", 400)
    result = await provide(
        cache_key=_key("search", q=query.lower()),
        ttl=60,
        client=_client(request),
        fetch=lambda client: client.get("/search", {"query": query}),
        mock=lambda: {
            "coins": [
                row
                for row in read_mock("coins.json")
                if query.lower() in row["name"].lower()
                or query.lower() in row["symbol"].lower()
            ]
        },
    )
    entries = result.value.get("coins", [])
    items = [
        {
            "id": str(item.get("id", "")),
            "symbol": str(item.get("symbol", "")).lower(),
            "name": str(item.get("name", "")),
            "image": item.get("large") or item.get("thumb") or item.get("image"),
            "rank": integer(item.get("market_cap_rank", item.get("rank"))),
        }
        for item in entries
    ]
    response.headers["X-Data-Source"] = result.source
    return {"query": query, "items": items}
