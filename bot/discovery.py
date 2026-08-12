import httpx

PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"
CHAIN_ID = "solana"


async def poll_discovery() -> list[str]:
    """Recently profiled/boosted Solana token addresses on DexScreener (secondary source)."""
    addresses: set[str] = set()
    async with httpx.AsyncClient(timeout=15) as client:
        for url in (PROFILES_URL, BOOSTS_URL):
            resp = await client.get(url)
            resp.raise_for_status()
            for item in resp.json():
                if item.get("chainId") == CHAIN_ID and item.get("tokenAddress"):
                    addresses.add(item["tokenAddress"])
    return list(addresses)
