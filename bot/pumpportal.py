import asyncio
import json
import logging
from collections.abc import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

WS_URL = "wss://pumpportal.fun/api/data"
RECONNECT_DELAY_S = 5


async def stream_new_tokens() -> AsyncIterator[dict]:
    """Yields raw pump.fun 'create' events forever, reconnecting on any disconnect."""
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                logger.info("connected to PumpPortal")
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if event.get("txType") == "create" and event.get("mint"):
                        yield event
        except Exception:
            logger.exception("PumpPortal connection error, reconnecting in %ss", RECONNECT_DELAY_S)
            await asyncio.sleep(RECONNECT_DELAY_S)
