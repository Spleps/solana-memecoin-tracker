import asyncio
import logging

from aiogram import Bot, Dispatcher

from . import db, feed, handlers, poller, walletpoller
from .config import load_config


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    await db.init_db(cfg.db_path)

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()
    dp.include_router(handlers.setup(cfg))

    poll_task = asyncio.create_task(poller.poll_loop(bot, cfg))
    feed_task = asyncio.create_task(feed.run(bot, cfg))
    wallet_task = asyncio.create_task(walletpoller.poll_loop(bot, cfg))
    try:
        await dp.start_polling(bot)
    finally:
        poll_task.cancel()
        feed_task.cancel()
        wallet_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
