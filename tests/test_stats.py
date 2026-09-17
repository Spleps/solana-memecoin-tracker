import asyncio

from bot import db


def test_bot_stats_include_user_and_global_counts(tmp_path) -> None:
    db_path = tmp_path / "tracker.db"

    async def run() -> None:
        await db.init_db(db_path)
        await db.add_watch(db_path, 1, "11111111111111111111111111111111", "first", 1.0)
        await db.add_watch(db_path, 1, "22222222222222222222222222222222", "second", 2.0)
        await db.set_feed_enabled(db_path, 1, True)
        await db.add_tracked_wallet(db_path, 1, "33333333333333333333333333333333", "alice")
        await db.add_tracked_wallet(db_path, 2, "44444444444444444444444444444444", "bob")

        stats = await db.get_bot_stats(db_path, 1)
        assert stats["user_watched_tokens"] == 2
        assert stats["user_tracked_wallets"] == 1
        assert stats["feed_enabled"] is True
        assert stats["watched_tokens"] == 2
        assert stats["unique_tokens"] == 2
        assert stats["tracked_wallets"] == 2
        assert stats["feed_subscribers"] == 1

    asyncio.run(run())
