"""Simulated WebSocket price feed for interview/demo use."""

import asyncio
import random
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.data import number, read_mock, scale_mock_market

router = APIRouter(tags=["simulated prices"])
PRICE_UPDATE_SECONDS = 2.0
MAX_STEP_PERCENT = 0.25
COIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]{1,128}$")


def _mock_starting_price(coin_id: str, currency: str) -> float | None:
    """Get the demo stream's starting quote from checked-in mock market data."""
    rows: list[dict[str, Any]] = read_mock("coins.json")
    row = next((item for item in rows if item.get("id") == coin_id), None)
    if row is None:
        return None
    if currency == "inr":
        row = scale_mock_market(row)
    return number(row.get("current_price"))


@router.websocket("/ws/prices/{coin_id}")
async def simulated_price_stream(websocket: WebSocket, coin_id: str) -> None:
    """Stream clearly marked simulated price updates for a known mock coin.

    The initial quote comes from the checked-in fixture; subsequent quotes are
    bounded random-walk updates. This endpoint does not represent live prices.
    """
    currency = websocket.query_params.get("currency", "usd").lower()
    if not COIN_ID_PATTERN.fullmatch(coin_id) or currency not in {"usd", "inr"}:
        await websocket.close(code=1008, reason="Invalid coin id or currency")
        return

    try:
        price = _mock_starting_price(coin_id, currency)
    except (OSError, ValueError, TypeError):
        price = None
    if price is None or price <= 0:
        await websocket.close(code=1008, reason="Coin is not available in mock data")
        return

    await websocket.accept()
    rng = random.Random()
    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "coin_id": coin_id,
                "currency": currency,
                "price": price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "mock",
            }
        )
        while True:
            await asyncio.sleep(PRICE_UPDATE_SECONDS)
            # Small bounded percentage moves keep the mock line continuous.
            change_pct = rng.uniform(-MAX_STEP_PERCENT, MAX_STEP_PERCENT)
            price *= 1 + change_pct / 100
            await websocket.send_json(
                {
                    "type": "price_update",
                    "coin_id": coin_id,
                    "currency": currency,
                    "price": round(price, 10),
                    "change_pct": round(change_pct, 6),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "mock",
                }
            )
    except WebSocketDisconnect:
        return
