import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.helius.xyz/v0/addresses/{address}/transactions"


@dataclass
class SwapEvent:
    signature: str
    timestamp: int
    direction: str  # "buy" | "sell"
    mint: str
    amount: float
    source: str


async def get_recent_swaps(api_key: str, wallet_address: str, since_signature: str | None) -> list[SwapEvent]:
    """New swaps for a wallet, oldest first, newer than since_signature (None = only the latest batch)."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                BASE_URL.format(address=wallet_address),
                params={"api-key": api_key, "limit": 20},
            )
            resp.raise_for_status()
            txs = resp.json()
    except Exception:
        logger.warning("helius lookup failed for %s", wallet_address)
        return []

    events: list[SwapEvent] = []
    for tx in txs:  # newest first
        if tx.get("signature") == since_signature:
            break
        if tx.get("type") != "SWAP":
            continue
        for transfer in tx.get("tokenTransfers", []):
            if transfer.get("fromUserAccount") == wallet_address:
                direction = "sell"
            elif transfer.get("toUserAccount") == wallet_address:
                direction = "buy"
            else:
                continue
            events.append(
                SwapEvent(
                    signature=tx["signature"],
                    timestamp=tx.get("timestamp", 0),
                    direction=direction,
                    mint=transfer.get("mint", "?"),
                    amount=float(transfer.get("tokenAmount", 0)),
                    source=tx.get("source", "?"),
                )
            )

    events.reverse()  # oldest first, so alerts arrive in chronological order
    return events
