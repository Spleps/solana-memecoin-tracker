import asyncio
import logging

from aiogram import Bot

from . import db, helius
from .config import Config

logger = logging.getLogger(__name__)


async def poll_loop(bot: Bot, cfg: Config) -> None:
    while True:
        try:
            await _poll_once(bot, cfg)
        except Exception:
            logger.exception("wallet poll cycle failed")
        await asyncio.sleep(cfg.wallet_poll_interval_s)


async def _poll_once(bot: Bot, cfg: Config) -> None:
    if not cfg.helius_api_key:
        return

    wallets = await db.all_tracked_wallets(cfg.db_path)
    for wallet_address in wallets:
        cursor = await db.get_wallet_cursor(cfg.db_path, wallet_address)
        events = await helius.get_recent_swaps(cfg.helius_api_key, wallet_address, cursor)
        if not events:
            continue

        if cursor is None:
            # first time tracking this wallet: establish a baseline, don't replay history as alerts
            await db.set_wallet_cursor(cfg.db_path, wallet_address, events[-1].signature)
            continue

        watchers = await db.get_wallet_watchers(cfg.db_path, wallet_address)
        for event in events:
            text = _format_swap(wallet_address, event)
            for chat_id in watchers:
                try:
                    await bot.send_message(chat_id, text)
                except Exception:
                    logger.exception("failed to send wallet alert to %s", chat_id)

        await db.set_wallet_cursor(cfg.db_path, wallet_address, events[-1].signature)


def _format_swap(wallet_address: str, event: "helius.SwapEvent") -> str:
    action = "🟢 bought" if event.direction == "buy" else "🔴 sold"
    short_wallet = wallet_address[:4] + "…" + wallet_address[-4:]
    return (
        f"👛 {short_wallet} {action}\n"
        f"Token: {event.mint}\n"
        f"Amount: {event.amount:,.2f}\n"
        f"Source: {event.source}\n"
        f"https://dexscreener.com/solana/{event.mint}"
    )
