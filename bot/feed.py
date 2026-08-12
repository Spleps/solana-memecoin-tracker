import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot

from . import db, dexscreener, discovery, llmverdict, pumpportal, rugcheck
from .config import Config
from .handlers import format_price, format_usd

logger = logging.getLogger(__name__)


async def run(bot: Bot, cfg: Config) -> None:
    await asyncio.gather(
        _ingest_pumpportal(bot, cfg),
        _sweep_loop(bot, cfg),
    )


async def _ingest_pumpportal(bot: Bot, cfg: Config) -> None:
    async for event in pumpportal.stream_new_tokens():
        mint = event.get("mint")
        if not mint:
            continue
        creator = event.get("traderPublicKey")
        await db.add_candidate(cfg.db_path, mint, "pumpfun", creator)

        if creator:
            success_count = await db.get_creator_success_count(cfg.db_path, creator)
            if success_count >= cfg.creator_success_threshold:
                await _notify_known_creator(bot, cfg, event, creator, success_count)


async def _notify_known_creator(bot: Bot, cfg: Config, event: dict, creator: str, success_count: int) -> None:
    subscribers = await db.get_feed_subscribers(cfg.db_path)
    if not subscribers:
        return
    name = event.get("name", "?")
    symbol = event.get("symbol", "?")
    mint = event.get("mint")
    text = (
        f"👤 Известный создатель ({success_count} успешных запусков) только что выпустил новый токен\n"
        f"{name} ({symbol})\n"
        f"https://pump.fun/coin/{mint}"
    )
    for chat_id in subscribers:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            logger.exception("failed to send known-creator alert to %s", chat_id)


async def _sweep_loop(bot: Bot, cfg: Config) -> None:
    while True:
        try:
            await _sweep_once(bot, cfg)
        except Exception:
            logger.exception("discovery sweep failed")
        await asyncio.sleep(cfg.discovery_poll_interval_s)


async def _sweep_once(bot: Bot, cfg: Config) -> None:
    try:
        for addr in await discovery.poll_discovery():
            await db.add_candidate(cfg.db_path, addr, "dexscreener")
    except Exception:
        logger.exception("discovery poll failed")

    pending = await db.get_pending_candidates(cfg.db_path)
    if not pending:
        return

    pairs = await dexscreener.get_pairs([row["token_address"] for row in pending])
    now = datetime.now(UTC)
    subscribers: list[int] | None = None

    for row in pending:
        addr = row["token_address"]
        pair = pairs.get(addr)

        if pair and pair.liquidity_usd >= cfg.discovery_min_liquidity_usd:
            if subscribers is None:
                subscribers = await db.get_feed_subscribers(cfg.db_path)
            await db.mark_candidate_status(cfg.db_path, addr, "alerted")
            if row["creator"]:
                await db.record_creator_success(cfg.db_path, row["creator"])
            risk = await rugcheck.get_risk(addr)
            prompt = llmverdict.build_prompt(pair.name, pair.symbol, pair.price_usd, pair.liquidity_usd, pair.volume_h24, risk)
            verdict = await llmverdict.get_verdict(prompt, cfg)
            text = _format_new_pair(pair, row["source"], risk, verdict)
            for chat_id in subscribers:
                try:
                    await bot.send_message(chat_id, text)
                except Exception:
                    logger.exception("failed to send feed alert to %s", chat_id)
            continue

        first_seen = datetime.fromisoformat(row["first_seen"])
        age_min = (now - first_seen).total_seconds() / 60
        if age_min >= cfg.candidate_max_age_min:
            await db.mark_candidate_status(cfg.db_path, addr, "dropped")


def _format_new_pair(
    pair: dexscreener.PairData, source: str, risk: rugcheck.RiskInfo | None, verdict: str | None
) -> str:
    lines = [
        f"🆕 {pair.name} ({pair.symbol}) [{source}]",
        f"Цена: ${format_price(pair.price_usd)}",
        f"Ликвидность: {format_usd(pair.liquidity_usd)}",
        f"Объём 24ч: {format_usd(pair.volume_h24)}",
    ]
    if risk is not None:
        lines.append(rugcheck.format_warning(risk))
    if verdict:
        lines.append(verdict)
    lines.append(pair.url)
    return "\n".join(lines)
