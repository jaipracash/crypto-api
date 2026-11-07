# Crypto Research API

FastAPI backend for a crypto research mobile app. It uses CoinGecko when available,
then falls back to in-memory cached data and checked-in mock JSON. Device watchlists
are persisted in SQLite.

## Run locally

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `COINGECKO_API_KEY` in `.env` to use an optional CoinGecko Demo API key.
`COINGECKO_BASE_URL`, `CORS_ORIGINS`, and `DATABASE_PATH` can also be configured.
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

For the interview demo, the backend exposes a mock-only WebSocket for the coins
in the checked-in market fixture. It sends a `snapshot` first, then a small,
bounded random price update every two seconds. Every message has `source: "mock"`;
these updates are simulated and are not CoinGecko live prices. The normal REST
coin details and chart endpoints remain the source of market snapshots/history.

```text
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
