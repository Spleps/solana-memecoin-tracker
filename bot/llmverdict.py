import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)

_CLI_FALLBACK_PATH = os.path.expanduser("~/.local/bin/claude")
_CLI_TIMEOUT_S = 30


def _resolve_cli_path() -> str | None:
    # systemd services get a minimal PATH that doesn't include ~/.local/bin,
    # so `shutil.which` alone isn't reliable there — fall back to the known path.
    return shutil.which("claude") or (_CLI_FALLBACK_PATH if os.path.isfile(_CLI_FALLBACK_PATH) else None)


def build_prompt(
    name: str,
    symbol: str,
    price_usd: float,
    liquidity_usd: float,
    volume_h24: float,
    risk: "rugcheck.RiskInfo | None",  # noqa: F821
) -> str:
    lines = [
        "Ты аналитик мемкоинов на Solana. На основе ТОЛЬКО приведённых ниже данных дай короткий "
        "вердикт на русском (1-2 предложения, начни с эмодзи). Не придумывай факты сверх данных и не "
        "путай направление шкал (ниже указано явно, что означает каждое значение). "
        "RugCheck score — это уже итоговая композитная оценка риска от RugCheck, учитывающая контекст токена "
        "(включая то, что LP locked % малозначим для давно устоявшихся токенов с органической ликвидностью). "
        "Опирайся в первую очередь на score, а не пересчитывай риск заново по отдельным метрикам вроде LP locked. "
        "Если данных недостаточно для вывода — так и скажи.",
        "",
        f"Токен: {name} ({symbol})",
        f"Цена: ${price_usd}",
        f"Ликвидность: ${liquidity_usd:,.0f}",
        f"Объём 24ч: ${volume_h24:,.0f}",
    ]
    if risk is not None:
        lines.append(f"RugCheck score риска: {risk.score_normalised:.0f} из 100 (0 = безопасно, 100 = максимальный риск)")
        lines.append(f"LP locked: {risk.lp_locked_pct:.0f}% (выше = безопаснее, ликвидность заблокирована)")
        lines.append(f"Freeze authority: {'включён (плохо, могут заморозить твой кошелёк)' if risk.freeze_authority else 'нет (хорошо)'}")
        lines.append(f"Уже помечен как раг: {'да' if risk.rugged else 'нет'}")
        if risk.risk_names:
            lines.append(f"Флаги риска: {', '.join(risk.risk_names)}")
    return "\n".join(lines)


async def _get_verdict_cli(prompt: str) -> str | None:
    cli_path = _resolve_cli_path()
    if cli_path is None:
        logger.warning("claude CLI not found (checked PATH and %s)", _CLI_FALLBACK_PATH)
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path,
            "-p",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CLI_TIMEOUT_S)
        if proc.returncode != 0:
            logger.warning("claude CLI exited %s: %s", proc.returncode, stderr.decode(errors="replace")[:300])
            return None
        return stdout.decode(errors="replace").strip() or None
    except Exception:
        logger.exception("claude CLI verdict failed")
        return None


async def _get_verdict_api(prompt: str, api_key: str, model: str) -> str | None:
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return text.strip() or None
    except Exception:
        logger.exception("claude API verdict failed")
        return None


async def get_verdict(prompt: str, cfg) -> str | None:
    if cfg.llm_backend == "api":
        if not cfg.llm_api_key:
            logger.warning("LLM_BACKEND=api but ANTHROPIC_API_KEY is not set")
            return None
        return await _get_verdict_api(prompt, cfg.llm_api_key, cfg.llm_api_model)
    return await _get_verdict_cli(prompt)
