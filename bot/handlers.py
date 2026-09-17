from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import Message

from . import db, dexscreener, llmverdict, rugcheck, scoring
from .config import Config
from .validation import is_solana_address

HELP_TEXT = (
    "Solana Memecoin Tracker\n\n"
    "/watch <token_address> [entry_price] [label] — watch a token\n"
    "/entryprice <token_address> <price> — set or update entry price\n"
    "/unwatch <token_address> — remove a token\n"
    "/list — list watched tokens\n"
    "/history <token_address> [limit] — show recent price and liquidity history\n"
    "/stats — show current bot status and usage\n"
    "/feed on|off — enable or disable the new-pair feed\n"
    "/topcreators — creators with successful launches\n"
    "/trackwallet <wallet_address> [label] — track wallet swaps\n"
    "/untrackwallet <wallet_address> — remove a wallet\n"
    "/wallets — list tracked wallets\n"
    "/help — show this help\n\n"
    "Alerts are sent when configured price, liquidity, or volume thresholds are crossed."
)


def format_price(price: float) -> str:
    if price == 0:
        return "0"
    if price < 0.01:
        return f"{price:.8f}".rstrip("0").rstrip(".")
    return f"{price:.4f}"


def format_usd(value: float) -> str:
    return f"${value:,.0f}"


def _try_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def setup(cfg: Config) -> Router:
    router = Router()

    class AllowedUserFilter(BaseFilter):
        async def __call__(self, message: Message) -> bool:
            return not cfg.allowed_telegram_ids or (
                message.from_user is not None and message.from_user.id in cfg.allowed_telegram_ids
            )

    router.message.filter(AllowedUserFilter())

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            HELP_TEXT
            + f"\n\nThresholds: price ±{cfg.price_alert_pct}%, "
            f"liquidity -{cfg.liquidity_drop_pct}%, volume +{cfg.volume_spike_pct}%"
        )

    @router.message(Command("watch"))
    async def cmd_watch(message: Message, command: CommandObject) -> None:
        parts = (command.args or "").split()
        if not parts:
            await message.answer("Usage: /watch <token_address> [entry_price] [label]")
            return
        token_address, rest = parts[0], parts[1:]
        if not is_solana_address(token_address):
            await message.answer("Invalid Solana address.")
            return

        entry_price: float | None = None
        if rest and (parsed := _try_float(rest[0])) is not None:
            entry_price = parsed
            rest = rest[1:]
        if entry_price is not None and entry_price <= 0:
            await message.answer("Entry price must be greater than zero.")
            return
        label = " ".join(rest) if rest else None

        pairs = await dexscreener.get_pairs([token_address])
        pair = pairs.get(token_address)
        if pair is None:
            await message.answer("Token not found on DexScreener for Solana.")
            return
        added = await db.add_watch(cfg.db_path, message.chat.id, token_address, label, entry_price)
        await db.upsert_snapshot(cfg.db_path, token_address, pair.price_usd, pair.liquidity_usd, pair.volume_h24)
        if not added:
            await message.answer(f"{pair.symbol} is already being watched.")
            return

        risk = await rugcheck.get_risk(token_address)
        score = scoring.calculate_score(pair, risk)
        lines = [
            f"Added: {pair.name} ({pair.symbol})",
            f"Price: ${format_price(pair.price_usd)}",
            f"Liquidity: {format_usd(pair.liquidity_usd)}",
            f"24h volume: {format_usd(pair.volume_h24)}",
            f"Token score: {score.value:.0f}/100 ({'; '.join(score.reasons) if score.reasons else 'no issues'})",
        ]
        if entry_price is not None:
            lines.append(f"Entry price: ${format_price(entry_price)}")
        if risk is not None:
            lines.append(rugcheck.format_warning(risk))
        verdict = await llmverdict.get_verdict(
            llmverdict.build_prompt(pair.name, pair.symbol, pair.price_usd, pair.liquidity_usd, pair.volume_h24, risk),
            cfg,
        )
        if verdict:
            lines.append(verdict)
        lines.append(pair.url)
        await message.answer("\n".join(lines))

    @router.message(Command("entryprice"))
    async def cmd_entryprice(message: Message, command: CommandObject) -> None:
        parts = (command.args or "").split()
        price = _try_float(parts[-1]) if parts else None
        if len(parts) != 2 or price is None or price <= 0 or not is_solana_address(parts[0]):
            await message.answer("Usage: /entryprice <token_address> <positive_price>")
            return
        ok = await db.set_entry_price(cfg.db_path, message.chat.id, parts[0], price)
        await message.answer(
            f"Entry price updated: ${format_price(price)}"
            if ok
            else "This token is not being watched. Use /watch first."
        )

    @router.message(Command("unwatch"))
    async def cmd_unwatch(message: Message, command: CommandObject) -> None:
        token_address = (command.args or "").strip()
        if not is_solana_address(token_address):
            await message.answer("Usage: /unwatch <token_address>")
            return
        removed = await db.remove_watch(cfg.db_path, message.chat.id, token_address)
        await message.answer("Removed from watchlist." if removed else "Token is not in your watchlist.")

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        stats = await db.get_bot_stats(cfg.db_path, message.chat.id)
        lines = [
            "Bot status:",
            f"• Your watched tokens: {stats['user_watched_tokens']}",
            f"• Your tracked wallets: {stats['user_tracked_wallets']}",
            f"• Feed enabled for you: {'yes' if stats['feed_enabled'] else 'no'}",
            f"• Total watched tokens: {stats['watched_tokens']}",
            f"• Unique tokens in watchlist: {stats['unique_tokens']}",
            f"• Total tracked wallets: {stats['tracked_wallets']}",
            f"• Active feed subscribers: {stats['feed_subscribers']}",
        ]
        await message.answer("\n".join(lines))

    @router.message(Command("history"))
    async def cmd_history(message: Message, command: CommandObject) -> None:
        parts = (command.args or "").split()
        if len(parts) not in {1, 2} or not is_solana_address(parts[0]):
            await message.answer("Usage: /history <token_address> [limit]")
            return
        token_address = parts[0]
        try:
            limit = int(parts[1]) if len(parts) == 2 else 10
        except ValueError:
            await message.answer("History limit must be an integer.")
            return
        if limit <= 0:
            await message.answer("History limit must be greater than zero.")
            return
        rows = await db.get_token_history(cfg.db_path, token_address, limit)
        if not rows:
            await message.answer("No recent price history is available for this token yet.")
            return
        lines = [f"Recent history for {token_address}:"]
        for row in reversed(rows):
            date = row["recorded_at"][:19].replace("T", " ")
            price = format_price(row["price_usd"]) if row["price_usd"] is not None else "n/a"
            liq = format_usd(row["liquidity_usd"]) if row["liquidity_usd"] is not None else "n/a"
            vol = format_usd(row["volume_h24"]) if row["volume_h24"] is not None else "n/a"
            lines.append(f"• {date} | price ${price} | liq {liq} | vol {vol}")
        await message.answer("\n".join(lines))

    @router.message(Command("feed"))
    async def cmd_feed(message: Message, command: CommandObject) -> None:
        arg = (command.args or "").strip().lower()
        if arg not in ("on", "off"):
            await message.answer("Usage: /feed on or /feed off")
            return
        await db.set_feed_enabled(cfg.db_path, message.chat.id, arg == "on")
        await message.answer(
            "New-pair feed enabled. "
            f"Minimum liquidity: ${cfg.discovery_min_liquidity_usd:,.0f}."
            if arg == "on"
            else "New-pair feed disabled."
        )

    @router.message(Command("topcreators"))
    async def cmd_topcreators(message: Message) -> None:
        rows = await db.get_top_creators(cfg.db_path, cfg.creator_success_threshold)
        if not rows:
            await message.answer(
                "No creators have reached the history threshold yet. "
                f"Minimum: {cfg.creator_success_threshold} successful launches."
            )
            return
        lines = ["Creators with successful launches:"]
        lines.extend(f"• {row['wallet_address']} — {row['success_count']} launches" for row in rows)
        await message.answer("\n".join(lines))

    @router.message(Command("trackwallet"))
    async def cmd_trackwallet(message: Message, command: CommandObject) -> None:
        if not cfg.helius_api_key:
            await message.answer("Wallet tracking is not configured (HELIUS_API_KEY is missing).")
            return
        args = (command.args or "").split(maxsplit=1)
        if not args or not is_solana_address(args[0]):
            await message.answer("Usage: /trackwallet <wallet_address> [label]")
            return
        wallet_address, label = args[0], args[1] if len(args) > 1 else None
        added = await db.add_tracked_wallet(cfg.db_path, message.chat.id, wallet_address, label)
        await message.answer(
            f"Tracking wallet {wallet_address}. I will notify you about new swaps."
            if added
            else "This wallet is already being tracked."
        )

    @router.message(Command("untrackwallet"))
    async def cmd_untrackwallet(message: Message, command: CommandObject) -> None:
        wallet_address = (command.args or "").strip()
        if not is_solana_address(wallet_address):
            await message.answer("Usage: /untrackwallet <wallet_address>")
            return
        removed = await db.remove_tracked_wallet(cfg.db_path, message.chat.id, wallet_address)
        await message.answer("Removed from tracking." if removed else "Wallet is not being tracked.")

    @router.message(Command("wallets"))
    async def cmd_wallets(message: Message) -> None:
        rows = await db.list_tracked_wallets(cfg.db_path, message.chat.id)
        if not rows:
            await message.answer("Your wallet list is empty. Add one with /trackwallet <wallet_address>.")
            return
        lines = ["Tracked wallets:"]
        for row in rows:
            label = f" ({row['label']})" if row["label"] else ""
            lines.append(f"• {row['wallet_address']}{label}")
        await message.answer("\n".join(lines))

    @router.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        rows = await db.list_watch(cfg.db_path, message.chat.id)
        if not rows:
            await message.answer("Your watchlist is empty. Add one with /watch <token_address>.")
            return
        lines = ["Watched tokens:"]
        for row in rows:
            label = f" ({row['label']})" if row["label"] else ""
            price = format_price(row["price_usd"]) if row["price_usd"] is not None else "?"
            liq = format_usd(row["liquidity_usd"]) if row["liquidity_usd"] is not None else "?"
            line = f"• {row['token_address']}{label}\n  price ${price}, liquidity {liq}"
            if row["entry_price"] and row["price_usd"] is not None:
                pnl = (row["price_usd"] - row["entry_price"]) / row["entry_price"] * 100
                line += f"\n  P&L from entry (${format_price(row['entry_price'])}): {pnl:+.1f}%"
            lines.append(line)
        await message.answer("\n".join(lines))

    return router
