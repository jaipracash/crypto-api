"""Pydantic response models and shared API types."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Currency = Literal["usd", "inr"]
CoinOrder = Literal[
    "market_cap_desc",
    "market_cap_asc",
    "volume_desc",
    "volume_asc",
    "price_desc",
    "price_asc",
    "change_desc",
    "change_asc",
]


class APIModel(BaseModel):
    """Base response model that ignores extra upstream values."""

    model_config = ConfigDict(extra="ignore")


class CoinItem(APIModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    rank: int | None = None
    price: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    change_24h_pct: float | None = None
    circulating_supply: float | None = None
    total_supply: float | None = None
    max_supply: float | None = None
    sparkline_7d: list[float] = Field(default_factory=list)
    is_watchlisted: bool = False


class CoinListResponse(APIModel):
    page: int
    per_page: int
    has_more: bool
    data_source: str
    items: list[CoinItem]


class CoinLinks(APIModel):
    website: str | None = None
    whitepaper: str | None = None


class CoinDetail(CoinItem):
    high_24h: float | None = None
    low_24h: float | None = None
    ath: float | None = None
    ath_change_pct: float | None = None
    ath_date: str | None = None
    atl: float | None = None
    atl_change_pct: float | None = None
    atl_date: str | None = None
    description: str = ""
    links: CoinLinks


class ChartResponse(APIModel):
    coin_id: str
    days: int
    currency: Currency
    prices: list[tuple[int, float]]
    min: float | None = None
    max: float | None = None
    change_pct: float | None = None


class SearchItem(APIModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    rank: int | None = None


class SearchResponse(APIModel):
    query: str
    items: list[SearchItem]


class GlobalMarket(APIModel):
    total_market_cap: float | None = None
    total_volume_24h: float | None = None
    market_cap_change_24h_pct: float | None = None
    btc_dominance: float | None = None
    eth_dominance: float | None = None
    others_dominance: float | None = None
    active_coins: int | None = None


class TrendingItem(APIModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    rank: int | None = None
    price_btc: float | None = None


class TrendingResponse(APIModel):
    items: list[TrendingItem]


class MoversResponse(APIModel):
    gainers: list[CoinItem]
    losers: list[CoinItem]


class WatchlistResponse(APIModel):
    count: int
    items: list[CoinItem]


class WatchlistMutation(APIModel):
    coin_id: str
    watchlisted: bool
