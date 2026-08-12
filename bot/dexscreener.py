from dataclasses import dataclass

import httpx

BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"
CHUNK_SIZE = 30
CHAIN_ID = "solana"


@dataclass
class PairData:
    token_address: str
    symbol: str
    name: str
    price_usd: float
    liquidity_usd: float
    volume_h24: float
    url: str


async def get_pairs(token_addresses: list[str]) -> dict[str, PairData]:
    """Best (highest-liquidity) Solana pair per token address, keyed by the address as given."""
    if not token_addresses:
        return {}

    results: dict[str, PairData] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for i in range(0, len(token_addresses), CHUNK_SIZE):
            chunk = token_addresses[i : i + CHUNK_SIZE]
            resp = await client.get(f"{BASE_URL}/{','.join(chunk)}")
            resp.raise_for_status()
            pairs = resp.json().get("pairs") or []

            best_pair_by_addr: dict[str, dict] = {}
            for pair in pairs:
                if pair.get("chainId") != CHAIN_ID:
                    continue
                base = pair.get("baseToken") or {}
                addr = base.get("address")
                if not addr or addr not in chunk:
                    continue
                liq = (pair.get("liquidity") or {}).get("usd") or 0
                current_best = best_pair_by_addr.get(addr)
                current_liq = (current_best.get("liquidity") or {}).get("usd") or 0 if current_best else -1
                if liq > current_liq:
                    best_pair_by_addr[addr] = pair

            for addr, pair in best_pair_by_addr.items():
                base = pair.get("baseToken") or {}
                try:
                    price = float(pair.get("priceUsd") or 0)
                except (TypeError, ValueError):
                    price = 0.0
                results[addr] = PairData(
                    token_address=addr,
                    symbol=base.get("symbol", "?"),
                    name=base.get("name", "?"),
                    price_usd=price,
                    liquidity_usd=float((pair.get("liquidity") or {}).get("usd") or 0.0),
                    volume_h24=float((pair.get("volume") or {}).get("h24") or 0.0),
                    url=pair.get("url", f"https://dexscreener.com/solana/{addr}"),
                )
    return results
