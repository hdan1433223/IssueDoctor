import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "token", "cookie", "password"}
BEARER_PATTERN = re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]+")
QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token)=)[^&\s]+"
)


def redact_secret(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if str(key).lower() in SENSITIVE_KEYS else redact_secret(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secret(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secret(item) for item in value)
    if isinstance(value, str):
        text = BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
        return QUERY_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    return value

