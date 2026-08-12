import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    token_address TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(chat_id, token_address)
);

CREATE TABLE IF NOT EXISTS snapshots (
    token_address TEXT PRIMARY KEY,
    price_usd REAL,
    liquidity_usd REAL,
    volume_h24 REAL,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER PRIMARY KEY,
    feed_enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS candidates (
    token_address TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    creator TEXT
);

CREATE TABLE IF NOT EXISTS creators (
    wallet_address TEXT PRIMARY KEY,
    success_count INTEGER NOT NULL DEFAULT 0,
    last_launch TEXT
);

CREATE TABLE IF NOT EXISTS tracked_wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    wallet_address TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(chat_id, wallet_address)
);

CREATE TABLE IF NOT EXISTS wallet_cursor (
    wallet_address TEXT PRIMARY KEY,
    last_signature TEXT
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE candidates ADD COLUMN creator TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists (pre-existing db from before this migration)
        try:
            conn.execute("ALTER TABLE snapshots ADD COLUMN market_type TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE watchlist ADD COLUMN entry_price REAL")
        except sqlite3.OperationalError:
            pass


async def init_db(db_path: Path) -> None:
    await asyncio.to_thread(_init_db_sync, db_path)


def _add_watch_sync(
    db_path: Path, chat_id: int, token_address: str, label: str | None, entry_price: float | None
) -> bool:
    with _connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO watchlist (chat_id, token_address, label, created_at, entry_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, token_address, label, datetime.now(UTC).isoformat(), entry_price),
            )
            return True
        except sqlite3.IntegrityError:
            return False


async def add_watch(
    db_path: Path, chat_id: int, token_address: str, label: str | None = None, entry_price: float | None = None
) -> bool:
    return await asyncio.to_thread(_add_watch_sync, db_path, chat_id, token_address, label, entry_price)


def _set_entry_price_sync(db_path: Path, chat_id: int, token_address: str, entry_price: float) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE watchlist SET entry_price = ? WHERE chat_id = ? AND token_address = ?",
            (entry_price, chat_id, token_address),
        )
        return cur.rowcount > 0


async def set_entry_price(db_path: Path, chat_id: int, token_address: str, entry_price: float) -> bool:
    return await asyncio.to_thread(_set_entry_price_sync, db_path, chat_id, token_address, entry_price)


def _remove_watch_sync(db_path: Path, chat_id: int, token_address: str) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE chat_id = ? AND token_address = ?",
            (chat_id, token_address),
        )
        return cur.rowcount > 0


async def remove_watch(db_path: Path, chat_id: int, token_address: str) -> bool:
    return await asyncio.to_thread(_remove_watch_sync, db_path, chat_id, token_address)


def _list_watch_sync(db_path: Path, chat_id: int) -> list[sqlite3.Row]:
    with _connect(db_path) as conn:
        return conn.execute(
            """
            SELECT w.token_address, w.label, w.entry_price,
                   s.price_usd, s.liquidity_usd, s.volume_h24, s.last_checked
            FROM watchlist w
            LEFT JOIN snapshots s ON s.token_address = w.token_address
            WHERE w.chat_id = ?
            ORDER BY w.created_at
            """,
            (chat_id,),
        ).fetchall()


async def list_watch(db_path: Path, chat_id: int) -> list[sqlite3.Row]:
    return await asyncio.to_thread(_list_watch_sync, db_path, chat_id)


def _all_watched_tokens_sync(db_path: Path) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT token_address FROM watchlist").fetchall()
        return [r["token_address"] for r in rows]


async def all_watched_tokens(db_path: Path) -> list[str]:
    return await asyncio.to_thread(_all_watched_tokens_sync, db_path)


def _get_watchers_sync(db_path: Path, token_address: str) -> list[int]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chat_id FROM watchlist WHERE token_address = ?", (token_address,)
        ).fetchall()
        return [r["chat_id"] for r in rows]


async def get_watchers(db_path: Path, token_address: str) -> list[int]:
    return await asyncio.to_thread(_get_watchers_sync, db_path, token_address)


def _get_snapshot_sync(db_path: Path, token_address: str) -> sqlite3.Row | None:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM snapshots WHERE token_address = ?", (token_address,)
        ).fetchone()


async def get_snapshot(db_path: Path, token_address: str) -> sqlite3.Row | None:
    return await asyncio.to_thread(_get_snapshot_sync, db_path, token_address)


def _upsert_snapshot_sync(
    db_path: Path,
    token_address: str,
    price_usd: float,
    liquidity_usd: float,
    volume_h24: float,
    market_type: str | None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO snapshots (token_address, price_usd, liquidity_usd, volume_h24, last_checked, market_type)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_address) DO UPDATE SET
                price_usd = excluded.price_usd,
                liquidity_usd = excluded.liquidity_usd,
                volume_h24 = excluded.volume_h24,
                last_checked = excluded.last_checked,
                market_type = excluded.market_type
            """,
            (token_address, price_usd, liquidity_usd, volume_h24, datetime.now(UTC).isoformat(), market_type),
        )


async def upsert_snapshot(
    db_path: Path,
    token_address: str,
    price_usd: float,
    liquidity_usd: float,
    volume_h24: float,
    market_type: str | None = None,
) -> None:
    await asyncio.to_thread(
        _upsert_snapshot_sync, db_path, token_address, price_usd, liquidity_usd, volume_h24, market_type
    )


def _set_feed_enabled_sync(db_path: Path, chat_id: int, enabled: bool) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers (chat_id, feed_enabled) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET feed_enabled = excluded.feed_enabled
            """,
            (chat_id, int(enabled)),
        )


async def set_feed_enabled(db_path: Path, chat_id: int, enabled: bool) -> None:
    await asyncio.to_thread(_set_feed_enabled_sync, db_path, chat_id, enabled)


def _get_feed_subscribers_sync(db_path: Path) -> list[int]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers WHERE feed_enabled = 1").fetchall()
        return [r["chat_id"] for r in rows]


async def get_feed_subscribers(db_path: Path) -> list[int]:
    return await asyncio.to_thread(_get_feed_subscribers_sync, db_path)


def _add_candidate_sync(db_path: Path, token_address: str, source: str, creator: str | None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO candidates (token_address, source, first_seen, status, creator)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (token_address, source, datetime.now(UTC).isoformat(), creator),
        )


async def add_candidate(db_path: Path, token_address: str, source: str, creator: str | None = None) -> None:
    await asyncio.to_thread(_add_candidate_sync, db_path, token_address, source, creator)


def _get_pending_candidates_sync(db_path: Path) -> list[sqlite3.Row]:
    with _connect(db_path) as conn:
        return conn.execute("SELECT * FROM candidates WHERE status = 'pending'").fetchall()


async def get_pending_candidates(db_path: Path) -> list[sqlite3.Row]:
    return await asyncio.to_thread(_get_pending_candidates_sync, db_path)


def _mark_candidate_status_sync(db_path: Path, token_address: str, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE candidates SET status = ? WHERE token_address = ?", (status, token_address)
        )


async def mark_candidate_status(db_path: Path, token_address: str, status: str) -> None:
    await asyncio.to_thread(_mark_candidate_status_sync, db_path, token_address, status)


def _record_creator_success_sync(db_path: Path, wallet_address: str) -> int:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO creators (wallet_address, success_count, last_launch) VALUES (?, 1, ?)
            ON CONFLICT(wallet_address) DO UPDATE SET
                success_count = success_count + 1,
                last_launch = excluded.last_launch
            """,
            (wallet_address, datetime.now(UTC).isoformat()),
        )
        row = conn.execute(
            "SELECT success_count FROM creators WHERE wallet_address = ?", (wallet_address,)
        ).fetchone()
        return row["success_count"]


async def record_creator_success(db_path: Path, wallet_address: str) -> int:
    return await asyncio.to_thread(_record_creator_success_sync, db_path, wallet_address)


def _get_creator_success_count_sync(db_path: Path, wallet_address: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT success_count FROM creators WHERE wallet_address = ?", (wallet_address,)
        ).fetchone()
        return row["success_count"] if row else 0


async def get_creator_success_count(db_path: Path, wallet_address: str) -> int:
    return await asyncio.to_thread(_get_creator_success_count_sync, db_path, wallet_address)


def _get_top_creators_sync(db_path: Path, min_count: int) -> list[sqlite3.Row]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM creators WHERE success_count >= ? ORDER BY success_count DESC LIMIT 20",
            (min_count,),
        ).fetchall()


async def get_top_creators(db_path: Path, min_count: int = 1) -> list[sqlite3.Row]:
    return await asyncio.to_thread(_get_top_creators_sync, db_path, min_count)


def _add_tracked_wallet_sync(db_path: Path, chat_id: int, wallet_address: str, label: str | None) -> bool:
    with _connect(db_path) as conn:
        try:
            conn.execute(
                "INSERT INTO tracked_wallets (chat_id, wallet_address, label, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, wallet_address, label, datetime.now(UTC).isoformat()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


async def add_tracked_wallet(db_path: Path, chat_id: int, wallet_address: str, label: str | None = None) -> bool:
    return await asyncio.to_thread(_add_tracked_wallet_sync, db_path, chat_id, wallet_address, label)


def _remove_tracked_wallet_sync(db_path: Path, chat_id: int, wallet_address: str) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM tracked_wallets WHERE chat_id = ? AND wallet_address = ?",
            (chat_id, wallet_address),
        )
        return cur.rowcount > 0


async def remove_tracked_wallet(db_path: Path, chat_id: int, wallet_address: str) -> bool:
    return await asyncio.to_thread(_remove_tracked_wallet_sync, db_path, chat_id, wallet_address)


def _list_tracked_wallets_sync(db_path: Path, chat_id: int) -> list[sqlite3.Row]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT wallet_address, label, created_at FROM tracked_wallets WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()


async def list_tracked_wallets(db_path: Path, chat_id: int) -> list[sqlite3.Row]:
    return await asyncio.to_thread(_list_tracked_wallets_sync, db_path, chat_id)


def _all_tracked_wallets_sync(db_path: Path) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT wallet_address FROM tracked_wallets").fetchall()
        return [r["wallet_address"] for r in rows]


async def all_tracked_wallets(db_path: Path) -> list[str]:
    return await asyncio.to_thread(_all_tracked_wallets_sync, db_path)


def _get_wallet_watchers_sync(db_path: Path, wallet_address: str) -> list[int]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chat_id FROM tracked_wallets WHERE wallet_address = ?", (wallet_address,)
        ).fetchall()
        return [r["chat_id"] for r in rows]


async def get_wallet_watchers(db_path: Path, wallet_address: str) -> list[int]:
    return await asyncio.to_thread(_get_wallet_watchers_sync, db_path, wallet_address)


def _get_wallet_cursor_sync(db_path: Path, wallet_address: str) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT last_signature FROM wallet_cursor WHERE wallet_address = ?", (wallet_address,)
        ).fetchone()
        return row["last_signature"] if row else None


async def get_wallet_cursor(db_path: Path, wallet_address: str) -> str | None:
    return await asyncio.to_thread(_get_wallet_cursor_sync, db_path, wallet_address)


def _set_wallet_cursor_sync(db_path: Path, wallet_address: str, last_signature: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO wallet_cursor (wallet_address, last_signature) VALUES (?, ?)
            ON CONFLICT(wallet_address) DO UPDATE SET last_signature = excluded.last_signature
            """,
            (wallet_address, last_signature),
        )


async def set_wallet_cursor(db_path: Path, wallet_address: str, last_signature: str) -> None:
    await asyncio.to_thread(_set_wallet_cursor_sync, db_path, wallet_address, last_signature)
