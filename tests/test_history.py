import asyncio

from bot import db


def test_token_history_is_recorded(tmp_path) -> None:
    db_path = tmp_path / "tracker.db"

    async def run() -> None:
        await db.init_db(db_path)
        await db.upsert_snapshot(db_path, "11111111111111111111111111111111", 1.0, 50_000.0, 100_000.0)
        await db.upsert_snapshot(db_path, "11111111111111111111111111111111", 1.5, 75_000.0, 200_000.0)

        history = await db.get_token_history(db_path, "11111111111111111111111111111111", 5)
        assert len(history) == 2
        assert history[0]["price_usd"] == 1.5
        assert history[1]["price_usd"] == 1.0

    asyncio.run(run())
