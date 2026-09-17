from dataclasses import dataclass

from .dexscreener import PairData
from .rugcheck import RiskInfo


@dataclass(frozen=True)
class TokenScore:
    value: float
    reasons: tuple[str, ...]


def calculate_score(pair: PairData, risk: RiskInfo | None) -> TokenScore:
    score = 50.0
    reasons: list[str] = []
    if pair.liquidity_usd >= 100_000:
        score += 20
        reasons.append("strong liquidity")
    elif pair.liquidity_usd >= 10_000:
        score += 10
        reasons.append("acceptable liquidity")
    else:
        score -= 15
        reasons.append("thin liquidity")
    if pair.volume_h24 >= pair.liquidity_usd * 2 > 0:
        score += 10
        reasons.append("strong volume")
    if risk:
        score -= min(30, risk.score_normalised * 0.3)
        if risk.freeze_authority:
            score -= 15
            reasons.append("freeze authority enabled")
        if risk.mint_authority:
            score -= 15
            reasons.append("mint authority enabled")
        if risk.rugged:
            score = 0
            reasons.append("marked as rugged")
    return TokenScore(max(0, min(100, score)), tuple(reasons))
