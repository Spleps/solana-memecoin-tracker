import string

BASE58_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
BASE58_ALPHABET = BASE58_ALPHABET.replace("0", "").replace("I", "").replace("O", "").replace("l", "")


def is_solana_address(value: str) -> bool:
    if not 32 <= len(value) <= 44:
        return False
    return all(char in BASE58_ALPHABET for char in value)


def parse_allowed_chat_ids(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()
    ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError as exc:
            raise ValueError(f"Invalid Telegram chat ID in ALLOWED_TELEGRAM_IDS: {item}") from exc
    return frozenset(ids)
