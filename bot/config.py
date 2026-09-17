import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .validation import parse_allowed_chat_ids

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: Path
    poll_interval_s: float
    price_alert_pct: float
    liquidity_drop_pct: float
    volume_spike_pct: float
    discovery_min_liquidity_usd: float
    discovery_poll_interval_s: float
    candidate_max_age_min: float
    creator_success_threshold: int
    helius_api_key: str | None
    wallet_poll_interval_s: float
    llm_backend: str
    llm_api_key: str | None
    llm_api_model: str
    allowed_telegram_ids: frozenset[int]
    alert_cooldown_s: float
    minimum_token_score: float


def load_config() -> Config:
    bot_token = os.environ["BOT_TOKEN"]
    db_path = BASE_DIR / os.environ.get("DB_PATH", "data/tracker.db")
    cfg = Config(
        bot_token=bot_token,
        db_path=db_path,
        poll_interval_s=float(os.environ.get("POLL_INTERVAL_S", "60")),
        price_alert_pct=float(os.environ.get("PRICE_ALERT_PCT", "15")),
        liquidity_drop_pct=float(os.environ.get("LIQUIDITY_DROP_PCT", "30")),
        volume_spike_pct=float(os.environ.get("VOLUME_SPIKE_PCT", "100")),
        discovery_min_liquidity_usd=float(os.environ.get("DISCOVERY_MIN_LIQUIDITY_USD", "2000")),
        discovery_poll_interval_s=float(os.environ.get("DISCOVERY_POLL_INTERVAL_S", "90")),
        candidate_max_age_min=float(os.environ.get("CANDIDATE_MAX_AGE_MIN", "60")),
        creator_success_threshold=int(os.environ.get("CREATOR_SUCCESS_THRESHOLD", "2")),
        helius_api_key=os.environ.get("HELIUS_API_KEY") or None,
        wallet_poll_interval_s=float(os.environ.get("WALLET_POLL_INTERVAL_S", "45")),
        llm_backend=os.environ.get("LLM_BACKEND", "cli"),
        llm_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        llm_api_model=os.environ.get("LLM_API_MODEL", "claude-opus-5"),
        allowed_telegram_ids=parse_allowed_chat_ids(os.environ.get("ALLOWED_TELEGRAM_IDS")),
        alert_cooldown_s=float(os.environ.get("ALERT_COOLDOWN_S", "1800")),
        minimum_token_score=float(os.environ.get("MINIMUM_TOKEN_SCORE", "0")),
    )
    if cfg.poll_interval_s <= 0 or cfg.discovery_poll_interval_s <= 0 or cfg.wallet_poll_interval_s <= 0:
        raise ValueError("Polling intervals must be greater than zero")
    if not 0 <= cfg.minimum_token_score <= 100:
        raise ValueError("MINIMUM_TOKEN_SCORE must be between 0 and 100")
    if cfg.alert_cooldown_s < 0:
        raise ValueError("ALERT_COOLDOWN_S cannot be negative")
    if cfg.llm_backend not in {"cli", "api", "off"}:
        raise ValueError("LLM_BACKEND must be cli, api, or off")
    return cfg
