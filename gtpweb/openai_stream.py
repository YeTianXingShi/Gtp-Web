from __future__ import annotations

import json
import re
from typing import Any

from openai import APIStatusError


def sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def get_obj_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        try:
            data = model_dump()
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def extract_text_delta(event_obj: Any) -> str:
    event_type = get_obj_value(event_obj, "type")
    if event_type == "response.output_text.delta":
        delta = get_obj_value(event_obj, "delta")
        return delta if isinstance(delta, str) else ""

    # Fallback for OpenAI-compatible providers returning ChatCompletions style stream chunks.
    event_dict = to_dict(event_obj)
    if not event_dict:
        return ""

    choices = event_dict.get("choices")
    if isinstance(choices, list) and choices:
        delta_obj = choices[0].get("delta", {})
        if isinstance(delta_obj, dict):
            content = delta_obj.get("content")
            if isinstance(content, str):
                return content
    return ""


def extract_error_message(data: dict[str, Any], fallback: str = "AI 服务返回错误") -> str:
    error_obj = data.get("error")
    if isinstance(error_obj, dict):
        message = error_obj.get("message")
        if isinstance(message, str) and message:
            return message
    return fallback


def summarize_non_json_error(body_text: str) -> str:
    raw = body_text.strip()
    if not raw:
        return "上游返回空响应"

    lowered = raw.lower()
    if "<html" in lowered:
        match = re.search(r"<title>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = " ".join(match.group(1).split())[:120]
            return f"上游返回 HTML 页面: {title}"
        return "上游返回 HTML 页面，通常是 OPENAI_BASE_URL 配置错误或被网关拦截。"

    return raw[:300]


def extract_status_error_message(exc: APIStatusError, fallback: str = "AI 服务返回错误") -> tuple[int | None, str]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if response is None:
        return status_code, str(exc) or fallback

    try:
        data = response.json()
        if isinstance(data, dict):
            return response.status_code, extract_error_message(data, fallback=fallback)
    except Exception:
        pass

    body_text = ""
    try:
        body_text = response.text
    except Exception:
        body_text = ""

    if body_text:
        return response.status_code, summarize_non_json_error(body_text)
    return response.status_code, str(exc) or fallback
