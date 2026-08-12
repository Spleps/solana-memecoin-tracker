from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from . import db, dexscreener, llmverdict, rugcheck
from .config import Config

HELP_TEXT = (
    "Solana Memecoin Tracker\n\n"
    "/watch <адрес_токена> [цена_входа] [метка] — добавить токен в отслеживание, можно с ценой входа для P&L\n"
    "/entryprice <адрес_токена> <цена> — задать/обновить цену входа\n"
    "/unwatch <адрес_токена> — убрать из отслеживания\n"
    "/list — список отслеживаемых токенов\n"
    "/feed on|off — фид новых Solana-пар (pump.fun + DexScreener), которые набрали реальную ликвидность\n"
    "/topcreators — кошельки-создатели pump.fun токенов с историей успешных запусков\n"
    "/trackwallet <адрес> [метка] — отслеживать сделки конкретного кошелька\n"
    "/untrackwallet <адрес> — убрать кошелёк из отслеживания\n"
    "/wallets — список отслеживаемых кошельков\n"
    "/help — эта справка\n\n"
    "Алерты приходят при изменении цены/ликвидности/объёма сверх порогов."
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

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            HELP_TEXT + f"\n\nТекущие пороги: цена ±{cfg.price_alert_pct}%, "
            f"ликвидность -{cfg.liquidity_drop_pct}%, объём +{cfg.volume_spike_pct}%"
        )

    @router.message(Command("watch"))
    async def cmd_watch(message: Message, command: CommandObject) -> None:
        parts = (command.args or "").split()
        if not parts:
            await message.answer("Использование: /watch <адрес_токена> [цена_входа] [метка]")
            return
        token_address, rest = parts[0], parts[1:]

        entry_price: float | None = None
        if rest and (parsed := _try_float(rest[0])) is not None:
            entry_price = parsed
            rest = rest[1:]
        label = " ".join(rest) if rest else None

        pairs = await dexscreener.get_pairs([token_address])
        pair = pairs.get(token_address)
        if pair is None:
            await message.answer("Не нашёл такой токен на DexScreener (Solana). Проверь адрес.")
            return

        added = await db.add_watch(cfg.db_path, message.chat.id, token_address, label, entry_price)
        await db.upsert_snapshot(cfg.db_path, token_address, pair.price_usd, pair.liquidity_usd, pair.volume_h24)

        if not added:
            await message.answer(f"{pair.symbol} уже в списке отслеживания.")
            return

        risk = await rugcheck.get_risk(token_address)
        lines = [
            f"Добавлено: {pair.name} ({pair.symbol})",
            f"Цена: ${format_price(pair.price_usd)}",
            f"Ликвидность: {format_usd(pair.liquidity_usd)}",
            f"Объём 24ч: {format_usd(pair.volume_h24)}",
        ]
        if entry_price is not None:
            lines.append(f"Цена входа: ${format_price(entry_price)}")
        if risk is not None:
            lines.append(rugcheck.format_warning(risk))

        prompt = llmverdict.build_prompt(pair.name, pair.symbol, pair.price_usd, pair.liquidity_usd, pair.volume_h24, risk)
        verdict = await llmverdict.get_verdict(prompt, cfg)
        if verdict:
            lines.append(verdict)

        lines.append(pair.url)
        await message.answer("\n".join(lines))

    @router.message(Command("entryprice"))
    async def cmd_entryprice(message: Message, command: CommandObject) -> None:
        parts = (command.args or "").split()
        price = _try_float(parts[-1]) if parts else None
        if len(parts) != 2 or price is None:
            await message.answer("Использование: /entryprice <адрес_токена> <цена>")
            return
        token_address = parts[0]
        ok = await db.set_entry_price(cfg.db_path, message.chat.id, token_address, price)
        if ok:
            await message.answer(f"Цена входа для {token_address} обновлена: ${format_price(price)}")
        else:
            await message.answer("Этот токен не в списке отслеживания. Сначала /watch.")

    @router.message(Command("unwatch"))
    async def cmd_unwatch(message: Message, command: CommandObject) -> None:
        token_address = (command.args or "").strip()
        if not token_address:
            await message.answer("Использование: /unwatch <адрес_токена>")
            return
        removed = await db.remove_watch(cfg.db_path, message.chat.id, token_address)
        await message.answer("Убрано из отслеживания." if removed else "Такого токена нет в списке.")

    @router.message(Command("feed"))
    async def cmd_feed(message: Message, command: CommandObject) -> None:
        arg = (command.args or "").strip().lower()
        if arg not in ("on", "off"):
            await message.answer("Использование: /feed on  или  /feed off")
            return
        await db.set_feed_enabled(cfg.db_path, message.chat.id, arg == "on")
        if arg == "on":
            await message.answer(
                "Фид новых пар включён. Буду присылать токены, набравшие ликвидность "
                f"от ${cfg.discovery_min_liquidity_usd:,.0f}."
            )
        else:
            await message.answer("Фид новых пар выключен.")

    @router.message(Command("topcreators"))
    async def cmd_topcreators(message: Message) -> None:
        rows = await db.get_top_creators(cfg.db_path)
        if not rows:
            await message.answer(
                "Пока нет создателей с успешными запусками. "
                f"Считается запуск, чей токен набрал ликвидность от ${cfg.discovery_min_liquidity_usd:,.0f}."
            )
            return
        lines = ["Создатели с историей успешных запусков:"]
        for row in rows:
            lines.append(f"• {row['wallet_address']} — {row['success_count']} запусков")
        await message.answer("\n".join(lines))

    @router.message(Command("trackwallet"))
    async def cmd_trackwallet(message: Message, command: CommandObject) -> None:
        if not cfg.helius_api_key:
            await message.answer("Трекинг кошельков не настроен (нет HELIUS_API_KEY на сервере).")
            return
        args = (command.args or "").split(maxsplit=1)
        if not args:
            await message.answer("Использование: /trackwallet <адрес_кошелька> [метка]")
            return
        wallet_address, label = args[0], (args[1] if len(args) > 1 else None)
        added = await db.add_tracked_wallet(cfg.db_path, message.chat.id, wallet_address, label)
        if not added:
            await message.answer("Этот кошелёк уже отслеживается.")
            return
        await message.answer(f"Отслеживаю кошелёк {wallet_address}. Пришлю сообщение при новой сделке.")

    @router.message(Command("untrackwallet"))
    async def cmd_untrackwallet(message: Message, command: CommandObject) -> None:
        wallet_address = (command.args or "").strip()
        if not wallet_address:
            await message.answer("Использование: /untrackwallet <адрес_кошелька>")
            return
        removed = await db.remove_tracked_wallet(cfg.db_path, message.chat.id, wallet_address)
        await message.answer("Убрано из отслеживания." if removed else "Такого кошелька нет в списке.")

    @router.message(Command("wallets"))
    async def cmd_wallets(message: Message) -> None:
        rows = await db.list_tracked_wallets(cfg.db_path, message.chat.id)
        if not rows:
            await message.answer("Список пуст. Добавь кошелёк: /trackwallet <адрес>")
            return
        lines = ["Отслеживаемые кошельки:"]
        for row in rows:
            label = f" ({row['label']})" if row["label"] else ""
            lines.append(f"• {row['wallet_address']}{label}")
        await message.answer("\n".join(lines))

    @router.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        rows = await db.list_watch(cfg.db_path, message.chat.id)
        if not rows:
            await message.answer("Список пуст. Добавь токен: /watch <адрес_токена>")
            return
        lines = ["Отслеживаемые токены:"]
        for row in rows:
            label = f" ({row['label']})" if row["label"] else ""
            price = format_price(row["price_usd"]) if row["price_usd"] is not None else "?"
            liq = format_usd(row["liquidity_usd"]) if row["liquidity_usd"] is not None else "?"
            line = f"• {row['token_address']}{label}\n  цена ${price}, ликв. {liq}"
            if row["entry_price"] and row["price_usd"] is not None:
                pnl = (row["price_usd"] - row["entry_price"]) / row["entry_price"] * 100
                line += f"\n  P&L от входа (${format_price(row['entry_price'])}): {pnl:+.1f}%"
            lines.append(line)
        await message.answer("\n".join(lines))

    return router
