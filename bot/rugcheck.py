import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

FULL_URL_TEMPLATE = "https://api.rugcheck.xyz/v1/tokens/{address}/report"
SUMMARY_URL_TEMPLATE = "https://api.rugcheck.xyz/v1/tokens/{address}/report/summary"


@dataclass
class RiskInfo:
    score_normalised: float
    lp_locked_pct: float
    risk_names: list[str]
    freeze_authority: str | None
    rugged: bool
    market_type: str | None


async def _get_json(client: httpx.AsyncClient, url: str) -> dict | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def get_risk(token_address: str) -> RiskInfo | None:
    async with httpx.AsyncClient(timeout=10) as client:
        full, summary = await asyncio.gather(
            _get_json(client, FULL_URL_TEMPLATE.format(address=token_address)),
            _get_json(client, SUMMARY_URL_TEMPLATE.format(address=token_address)),
        )

    if full is None and summary is None:
        logger.warning("rugcheck lookup failed for %s", token_address)
        return None
    full = full or {}
    summary = summary or {}

    risks = full.get("risks") or summary.get("risks") or []
    markets = full.get("markets") or []
    score = full.get("score_normalised", summary.get("score_normalised"))
    return RiskInfo(
        score_normalised=float(score or 0),
        lp_locked_pct=float(summary.get("lpLockedPct") or 0),
        risk_names=[r["name"] for r in risks if r.get("name")],
        freeze_authority=full.get("freezeAuthority"),
        rugged=bool(full.get("rugged")),
        market_type=markets[0].get("marketType") if markets else None,
    )


def format_warning(risk: RiskInfo) -> str:
    lines = []
    if risk.rugged:
        lines.append("⛔ RugCheck: уже помечен как раг")
    if risk.freeze_authority:
        lines.append("🚫 Freeze authority включён — возможно НЕЛЬЗЯ продать")

    if risk.score_normalised >= 60:
        level = "🔴 высокий риск рага"
    elif risk.score_normalised >= 30:
        level = "🟡 средний риск"
    else:
        level = "🟢 низкий риск"
    lines.append(f"Риск: {level} (score {risk.score_normalised:.0f}/100, LP locked {risk.lp_locked_pct:.0f}%)")

    if risk.risk_names:
        lines.append(", ".join(risk.risk_names[:3]))
    return "\n".join(lines)
