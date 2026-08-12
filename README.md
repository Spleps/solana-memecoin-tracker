# Solana Memecoin Tracker

Telegram-бот для отслеживания мемкоинов на Solana: личный вотчлист адресов токенов, алерты по цене/ликвидности/объёму. Данные — DexScreener public API (без ключа).

## Запуск

```bash
cp .env.example .env   # вписать BOT_TOKEN от @BotFather
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m bot.main
```

## Команды

- `/watch <адрес_токена> [цена_входа] [метка]` — добавить токен в отслеживание, опционально с ценой входа для P&L
- `/entryprice <адрес_токена> <цена>` — задать/обновить цену входа задним числом
- `/unwatch <адрес_токена>` — убрать
- `/list` — список отслеживаемых токенов с последними метриками
- `/feed on|off` — фид новых Solana-пар (pump.fun через PumpPortal + DexScreener profiles/boosts), которые набрали реальную ликвидность
- `/topcreators` — кошельки-создатели с историей успешных запусков (см. ниже)
- `/trackwallet <адрес> [метка]` — отслеживать сделки конкретного кошелька (нужен `HELIUS_API_KEY`)
- `/untrackwallet <адрес>` — убрать кошелёк из отслеживания
- `/wallets` — список отслеживаемых кошельков
- `/help` — справка и текущие пороги алертов

## Пороги алертов (`.env`)

- `PRICE_ALERT_PCT` — изменение цены за один цикл опроса (по умолчанию 15%)
- `LIQUIDITY_DROP_PCT` — падение ликвидности, возможный rug pull (по умолчанию 30%)
- `VOLUME_SPIKE_PCT` — рост объёма за 24ч (по умолчанию 100%)
- `POLL_INTERVAL_S` — интервал опроса DexScreener (по умолчанию 60 сек)

## Фид новых пар (`.env`)

Новые токены на pump.fun стартуют с почти одинаковой стартовой капитализацией бондинг-кривой (~28-30 SOL) — это не сигнал качества. Поэтому фид не алертит по факту создания токена, а ждёт, пока он наберёт реальную ликвидность на DEX:

- `DISCOVERY_MIN_LIQUIDITY_USD` — порог ликвидности для алерта (по умолчанию $2000)
- `DISCOVERY_POLL_INTERVAL_S` — как часто проверять кандидатов и опрашивать DexScreener profiles/boosts (по умолчанию 90 сек)
- `CANDIDATE_MAX_AGE_MIN` — сколько минут ждать, прежде чем списать кандидата, который так и не набрал ликвидность (по умолчанию 60)

## Создатели с историей (`.env`)

PumpPortal-события создания токена включают кошелёк создателя. Когда его токен графуирует (набирает ликвидность), кошелёк получает +1 к счётчику успешных запусков (`/topcreators`). Как только счётчик достигает `CREATOR_SUCCESS_THRESHOLD` (по умолчанию 2), новый запуск этого кошелька сразу шлётся подписчикам `/feed` как ранний сигнал — ещё до того, как токен наберёт ликвидность.

Это не PnL-трекинг трейдеров (для него нет бесплатного источника данных на Solana), а трек-рекорд создателей на основе уже собираемых бесплатных данных.

## Трекинг сделок кошелька (`.env`)

`/trackwallet` показывает реальные покупки/продажи отслеживаемого кошелька через Helius Enhanced Transactions API (бесплатный тариф, нужна регистрация на helius.dev за ключом — без пополнения SOL, в отличие от PumpPortal-сделок).

- `HELIUS_API_KEY` — ключ с helius.dev; без него `/trackwallet` отвечает, что функция не настроена
- `WALLET_POLL_INTERVAL_S` — как часто проверять новые сделки по каждому отслеживаемому кошельку (по умолчанию 45 сек)

## Sell-checker и миграции площадок

Каждый вызов RugCheck (в `/watch` и `/feed`) теперь также проверяет `freezeAuthority` (владелец может заморозить твой кошелёк — не продашь) и флаг `rugged` (уже помечен как раг) — эти строки идут первыми в предупреждении, перед обычной оценкой риска.

Для токенов из личного вотчлиста (`/watch`) бот дополнительно следит за тем, на какой площадке торгуется токен (`markets[0].marketType` из RugCheck — `pump_fun_amm`, `raydium`, `orca` и т.д.) и шлёт отдельный алерт при смене площадки (например, миграция с внутреннего AMM пампа на Raydium).

## AI-вердикт (`.env`)

В `/watch` и `/feed` добавляется короткий вердикт от Claude на основе уже собранных данных (цена, ликвидность, RugCheck-риски) — не новая информация, а синтез существующих сигналов в одну фразу.

- `LLM_BACKEND` — `cli` (по умолчанию) или `api`
  - `cli` — дёргает локальный `claude` CLI (`claude -p "..."`) по существующей подписке Claude Code, бесплатно. Требует, чтобы `claude` был установлен и авторизован на машине, где крутится бот.
  - `api` — использует Anthropic API напрямую через `ANTHROPIC_API_KEY`
- `ANTHROPIC_API_KEY` — нужен только при `LLM_BACKEND=api`
- `LLM_API_MODEL` — модель для API-режима (по умолчанию `claude-opus-5`; можно указать более дешёвую, например `claude-haiku-4-5`, если вердикт будет генерироваться часто — это может быть заметно по цене на объёме)

Если вызов LLM не удался (CLI недоступен, нет ключа, таймаут) — строка с вердиктом просто не добавляется, остальной алерт уходит как обычно.

## systemd (автозапуск)

```ini
# ~/.config/systemd/user/solana-tracker.service
[Unit]
Description=Solana Memecoin Tracker Bot
After=network-online.target

[Service]
WorkingDirectory=/home/rytm/Projects/solana-memecoin-tracker
ExecStart=/home/rytm/Projects/solana-memecoin-tracker/.venv/bin/python -m bot.main
EnvironmentFile=/home/rytm/Projects/solana-memecoin-tracker/.env
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now solana-tracker
journalctl --user -u solana-tracker -f
```
