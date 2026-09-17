from bot.dexscreener import PairData
from bot.rugcheck import RiskInfo
from bot.scoring import calculate_score


def pair(liquidity: float = 100_000, volume: float = 250_000) -> PairData:
    return PairData("A" * 32, "TEST", "Test", 1.0, liquidity, volume, "https://example.com")


def test_score_penalizes_dangerous_authorities() -> None:
    safe = calculate_score(pair(), None)
    risky = calculate_score(
        pair(),
        RiskInfo(80, 0, [], "freeze", "mint", False, None),
    )
    assert safe.value > risky.value
    assert "freeze authority enabled" in risky.reasons
    assert "mint authority enabled" in risky.reasons
