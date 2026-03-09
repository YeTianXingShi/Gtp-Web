from __future__ import annotations

import re
from typing import Any


def safe_filename(raw: str) -> str:
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("_")
    return cleaned[:80] or "conversation"


def safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None
