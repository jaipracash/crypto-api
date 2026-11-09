# Crypto Research API

FastAPI backend for a crypto research mobile app. It uses CoinGecko when available,
then falls back to in-memory cached data and checked-in mock JSON. Device watchlists
are persisted in SQLite.

## Technology and design

- **Python** with **FastAPI** and **Uvicorn** for asynchronous REST and WebSocket
  endpoints.
- **Pydantic 2** for request validation and typed API response models.
- **HTTPX** for asynchronous CoinGecko requests, with connection/read timeouts
  and a retry for network errors.
- **cachetools** for an in-memory TTL cache with stale-value retention.
- **SQLite** through Python's built-in `sqlite3` module for per-device
  watchlists.
- **python-dotenv** and environment variables for runtime configuration.

Routers in `app/routers/` handle HTTP and WebSocket endpoints. Shared Pydantic
models are in `app/schemas.py`; `app/services/coingecko.py` owns upstream
requests; `app/services/data.py` normalizes provider data and applies the cache,
stale-data, and mock fallback policy. `app/db.py` handles watchlist persistence.
The application lifespan initializes SQLite and manages the shared CoinGecko
HTTP client.

## Run locally

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For the Demo API, set `COINGECKO_API_PLAN=demo` and `COINGECKO_API_KEY`. For a
paid CoinGecko plan, set `COINGECKO_API_PLAN=pro`, provide your Pro key in
`COINGECKO_API_KEY`, and set `COINGECKO_BASE_URL=https://pro-api.coingecko.com/api/v3`.
The backend selects the matching API key header. `CORS_ORIGINS` and
`DATABASE_PATH` can also be configured. Keep API keys in the local `.env` file
and out of source control; `.env.example` lists supported variables.
The API documentation is available at `http://localhost:8000/docs`.

For Flutter, use `http://10.0.2.2:8000` from the Android emulator. A real device
should use the development computer's LAN IP (for example,
`http://192.168.1.25:8000`) and both devices must be on the same network.

## Endpoints

All market and watchlist endpoints are under `/api`. Market endpoints return the
`X-Data-Source` response header (`live`, `cache`, or `mock`). Watchlist endpoints
require an `X-Device-ID` header; this is a per-install/device identifier, not a
secret. Supported currencies are `usd` and `inr`.

### Health

```bash
curl http://localhost:8000/health
```

### Coin list

Supports page, per-page (maximum 250), order, currency and optional CoinGecko
category parameters. Items include 1h, 24h, 7d and 30d percentage changes.

```bash
curl 'http://localhost:8000/api/coins?page=1&per_page=100&order=market_cap_desc&currency=usd&category=layer-1'
```

### Coin details

```bash
curl 'http://localhost:8000/api/coins/bitcoin?currency=usd'
```

### Price chart

`days` must be one of `1`, `7`, `30`, `90`, or `365`.
If CoinGecko has no chart data available (or the upstream request is
unavailable/rate-limited), this endpoint returns an empty chart with HTTP 200
and `X-Data-Source: no-data`. The app can render its chart empty state instead
of showing fixture points or treating a missing history as a server error.

```bash
curl 'http://localhost:8000/api/coins/bitcoin/chart?days=7&currency=usd'
```

### Search

The search query must contain at least two characters.

```bash
curl 'http://localhost:8000/api/search?q=bit'
```

### Global market

```bash
curl 'http://localhost:8000/api/market/global?currency=usd'
```

### Trending coins

Returns full coin-item market data for trending assets.

```bash
curl http://localhost:8000/api/market/trending
```

### Market movers

Deprecated; use `/api/coins` and filter/sort client-side. `limit` must be between
1 and 50.

```bash
curl 'http://localhost:8000/api/market/movers?limit=5&currency=usd'
```

### Simulated WebSocket price stream

For the interview demo, the backend exposes mock-only WebSockets for coins in
the checked-in market fixture. The all-coins endpoint sends one `snapshot` with
all fixture coins first, then a small, bounded random update for each coin every
two seconds. Every message has `source: "mock"`; these updates are simulated and
are not CoinGecko live prices. The normal REST coin details and chart endpoints
remain the source of market snapshots/history.

```text
ws://localhost:8000/api/ws/prices?currency=usd
ws://localhost:8000/api/ws/prices/bitcoin?currency=usd
```

Use `wss://` when the API is deployed behind HTTPS. Supported currencies are
`usd` and `inr`. Unknown coins and invalid parameters are rejected with WebSocket
close code `1008`.

### Get a device watchlist

```bash
curl 'http://localhost:8000/api/watchlist?currency=usd' \
  -H 'X-Device-ID: my-phone'
```

### Add a coin to the watchlist

```bash
curl -X POST http://localhost:8000/api/watchlist/bitcoin \
  -H 'X-Device-ID: my-phone'
```

### Remove a coin from the watchlist

```bash
curl -X DELETE http://localhost:8000/api/watchlist/bitcoin \
  -H 'X-Device-ID: my-phone'
```

## Errors and fallback behavior

Errors use `{"error":{"code":"...","message":"..."}}`. Validation errors are
`INVALID_PARAMS` (400), unknown coins are `COIN_NOT_FOUND` (404), exhausted
CoinGecko quota is `UPSTREAM_RATE_LIMITED` (429), and other unavailable upstream
requests are `UPSTREAM_ERROR` (502). Fresh cache is preferred, followed by live
CoinGecko data, stale cache, and mock JSON. Mock fixtures cover the top 20 coins,
global market, trending list, and sample charts.

## Testing

No automated backend test suite is currently included in this repository.
FastAPI's interactive endpoint documentation is available at `/docs` while the
service is running; `/health` provides a simple process health check.
