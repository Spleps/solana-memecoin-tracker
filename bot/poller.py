import asyncio
import logging
import sqlite3

from aiogram import Bot

from . import db, dexscreener, rugcheck
from .config import Config
from .handlers import format_price, format_usd

logger = logging.getLogger(__name__)


async def poll_loop(bot: Bot, cfg: Config) -> None:
    while True:
        try:
            await _poll_once(bot, cfg)
        except Exception:
            logger.exception("poll cycle failed")
        await asyncio.sleep(cfg.poll_interval_s)


async def _poll_once(bot: Bot, cfg: Config) -> None:
    tokens = await db.all_watched_tokens(cfg.db_path)
    if not tokens:
        return

    pairs = await dexscreener.get_pairs(tokens)

    for token_address in tokens:
        pair = pairs.get(token_address)
        if pair is None:
            continue

        old = await db.get_snapshot(cfg.db_path, token_address)
        risk = await rugcheck.get_risk(token_address)
        new_market_type = risk.market_type if risk else None
        await db.upsert_snapshot(
            cfg.db_path, token_address, pair.price_usd, pair.liquidity_usd, pair.volume_h24, new_market_type
        )

        if old is None or old["price_usd"] is None:
            continue  # first observation for this token, nothing to compare yet

        watchers = None

        old_market_type = old["market_type"] if "market_type" in old.keys() else None
        if old_market_type and new_market_type and old_market_type != new_market_type:
            watchers = await db.get_watchers(cfg.db_path, token_address)
            migration_text = (
                f"🔀 {pair.name} ({pair.symbol}) мигрировал: {old_market_type} → {new_market_type}\n{pair.url}"
            )
            for chat_id in watchers:
                try:
                    await bot.send_message(chat_id, migration_text)
                except Exception:
                    logger.exception("failed to send migration alert to %s", chat_id)

        alerts = _check_alerts(cfg, old, pair)
        if not alerts:
            continue

        if watchers is None:
            watchers = await db.get_watchers(cfg.db_path, token_address)
        text = _format_alert(pair, alerts)
        for chat_id in watchers:
            try:
                await bot.send_message(chat_id, text)
            except Exception:
                logger.exception("failed to send alert to %s", chat_id)


def _pct_change(old: float, new: float) -> float:
    if not old:
        return 0.0
    return (new - old) / old * 100


def _check_alerts(cfg: Config, old: sqlite3.Row, pair: dexscreener.PairData) -> list[str]:
    alerts = []

    price_change = _pct_change(old["price_usd"], pair.price_usd)
    if abs(price_change) >= cfg.price_alert_pct:
        direction = "выросла" if price_change > 0 else "упала"
        alerts.append(f"Цена {direction} на {price_change:+.1f}%")

    liq_change = _pct_change(old["liquidity_usd"], pair.liquidity_usd)
    if liq_change <= -cfg.liquidity_drop_pct:
        alerts.append(f"⚠️ Ликвидность упала на {liq_change:.1f}% — возможен rug pull")

    vol_change = _pct_change(old["volume_h24"], pair.volume_h24)
    if vol_change >= cfg.volume_spike_pct:
        alerts.append(f"Объём вырос на {vol_change:+.1f}%")

    return alerts


def _format_alert(pair: dexscreener.PairData, alerts: list[str]) -> str:
    lines = [f"{pair.name} ({pair.symbol})", *alerts, ""]
    lines.append(f"Цена: ${format_price(pair.price_usd)}")
    lines.append(f"Ликвидность: {format_usd(pair.liquidity_usd)}")
    lines.append(f"Объём 24ч: {format_usd(pair.volume_h24)}")
    lines.append(pair.url)
    return "\n".join(lines)
