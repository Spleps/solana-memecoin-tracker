# Solana Memecoin Tracker

An English Telegram bot for monitoring Solana tokens, liquidity, volume, new pairs, creator history, and wallet swaps.

The bot uses public DexScreener data, RugCheck, PumpPortal, and optionally Helius and Claude. It is an alerting and research tool, not financial advice.

## What problem it solves

New Solana tokens produce information across several services. The bot brings those observations
into one Telegram workflow: a user can watch a token, receive changes in price or liquidity,
inspect recent history, and review basic authority and creator signals without manually checking
multiple dashboards.

It is designed for monitoring and research. It does not sign transactions, buy or sell tokens,
or hold private keys.

## Features

- Per-user token watchlists with entry prices and P&L percentage.
- Price, liquidity, volume, and DEX migration alerts.
- New-pair discovery from PumpPortal and DexScreener.
- RugCheck warnings for rug status, freeze authority, mint authority, and risk score.
- Configurable token quality score from 0 to 100 with reason-based scoring.
- Bot stats summary for watched tokens, tracked wallets, and feed status.
- Recent price/liquidity/history snapshots and `/history` command.
- Creator success history and known-creator alerts.
- Optional Helius wallet swap tracking.
- Alert cooldown and deduplication backed by SQLite.
- Telegram user allowlist for private deployments.
- Optional Claude CLI or Anthropic API verdicts.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env and set BOT_TOKEN
.venv/bin/python -m bot.main
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python -m bot.main
```

## Commands

| Command | Description |
|---|---|
| `/watch <token_address> [entry_price] [label]` | Add a Solana token |
| `/entryprice <token_address> <price>` | Set an entry price |
| `/unwatch <token_address>` | Remove a token |
| `/list` | Show watched tokens and P&L percentage |
| `/history <token_address> [limit]` | Show recent price, liquidity, and volume history |
| `/stats` | Show bot/user statistics and feed status |
| `/feed on\|off` | Enable or disable new-pair alerts |
| `/topcreators` | Show creators with successful launches |
| `/trackwallet <wallet_address> [label]` | Track wallet swaps |
| `/untrackwallet <wallet_address>` | Stop tracking a wallet |
| `/wallets` | Show tracked wallets |
| `/help` | Show help and thresholds |

## Example workflow

```text
/watch <token-address> 0.00042 frog
```

The bot stores the watch entry and can later report the current price, liquidity, volume and
percentage change from the saved entry price. If liquidity falls beyond the configured threshold,
the user receives a warning. A separate `/history <token-address> 10` request shows the latest
stored snapshots rather than only the current API response.

For discovery, enabling `/feed on` allows qualifying new pairs from the configured feed to be
checked against liquidity and token-quality thresholds. A token with enabled freeze authority or
an unfavourable RugCheck result is reported with those reasons instead of being silently treated
as safe.

## Configuration

Copy `.env.example` to `.env`. Important settings:

- `BOT_TOKEN`: Telegram bot token.
- `ALLOWED_TELEGRAM_IDS`: comma-separated Telegram IDs; leave empty only for a public bot.
- `POLL_INTERVAL_S`: watchlist polling interval.
- `PRICE_ALERT_PCT`, `LIQUIDITY_DROP_PCT`, `VOLUME_SPIKE_PCT`: alert thresholds.
- `ALERT_COOLDOWN_S`: suppresses identical alerts during the cooldown window.
- `MINIMUM_TOKEN_SCORE`: minimum score required for the new-pair feed.
- `DISCOVERY_MIN_LIQUIDITY_USD`: minimum liquidity for discovered pairs.
- `HELIUS_API_KEY`: enables wallet tracking.
- `LLM_BACKEND`: `cli`, `api`, or `off`.

All numeric settings are validated at startup. Existing SQLite databases are migrated in place; no tables are dropped.

## Data flow

1. A scheduled poller fetches public market and token metadata.
2. Normalized observations are stored in SQLite.
3. Rule-based checks compare the new observation with thresholds and previous snapshots.
4. Cooldowns and deduplication prevent repeated copies of the same alert.
5. Telegram commands expose watchlists, history, creator summaries and feed status.

Optional Helius wallet tracking and Claude-backed verdicts are disabled unless their configuration
is supplied. The core tracker remains usable with the public data providers alone.

## Data and limitations

The bot does not execute trades or custody funds. API data can be delayed, incomplete, rate-limited, or unavailable. A high token score is not a guarantee of safety or profitability. Always verify a token independently before trading.

## systemd

```ini
[Unit]
Description=Solana Memecoin Tracker
After=network-online.target

[Service]
WorkingDirectory=/home/user/solana-memecoin-tracker
ExecStart=/home/user/solana-memecoin-tracker/.venv/bin/python -m bot.main
EnvironmentFile=/home/user/solana-memecoin-tracker/.env
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now solana-tracker
journalctl --user -u solana-tracker -f
```
