from __future__ import annotations

import re
from fnmatch import fnmatchcase
from typing import Any, Iterable


def safe_filename(raw: str) -> str:
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("_")
    return cleaned[:80] or "conversation"


def safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_model_match_patterns(
    raw_value: str,
    *,
    default: Iterable[str] = (),
) -> list[str]:
    patterns = [item.strip().lower() for item in str(raw_value or "").split(",") if item.strip()]
    return patterns or [item.strip().lower() for item in default if str(item).strip()]


def model_name_matches_patterns(model_name: str, patterns: Iterable[str]) -> bool:
    normalized_name = str(model_name or "").strip().lower()
    if not normalized_name:
        return False

    for pattern in patterns:
        normalized_pattern = str(pattern or "").strip().lower()
        if not normalized_pattern:
            continue
        if fnmatchcase(normalized_name, normalized_pattern):
            return True
    return False
