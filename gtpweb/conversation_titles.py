from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAIError

from gtpweb.ai_providers import PROVIDER_GOOGLE, PROVIDER_OPENAI

logger = logging.getLogger(__name__)

_DEFAULT_PREFIX = "新对话 "
_TITLE_PATTERN = re.compile(r"^新对话\s*(\d+)$")


def allocate_default_conversation_title(existing_titles: list[str]) -> str:
    used_numbers: set[int] = set()
    for raw_title in existing_titles:
        title = str(raw_title or "").strip()
        match = _TITLE_PATTERN.match(title)
        if not match:
            continue
        try:
            used_numbers.add(int(match.group(1)))
        except ValueError:
            continue

    next_number = 1
    while next_number in used_numbers:
        next_number += 1
    return f"{_DEFAULT_PREFIX}{next_number}"


def is_default_conversation_title(title: str) -> bool:
    return bool(_TITLE_PATTERN.match(str(title or "").strip()))


def _normalize_title(raw_title: str, fallback: str) -> str:
    text = str(raw_title or "").strip()
    if not text:
        return fallback
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r'^["“”\'\'`\-:：#\s]+', "", text)
    text = re.sub(r'["“”\'\'`\s]+$', "", text)
    text = text[:60].strip()
    return text or fallback


def _extract_title_from_text(raw_text: str, fallback: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return fallback
    first_line = text.splitlines()[0].strip()
    if first_line.lower().startswith("title:"):
        first_line = first_line.split(":", 1)[1].strip()
    if first_line.lower().startswith("标题："):
        first_line = first_line.split("：", 1)[1].strip()
    return _normalize_title(first_line, fallback)


def _build_title_source_messages(completion_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    source_messages: list[dict[str, str]] = []
    for item in completion_messages[:4]:
        role = str(item.get("role", "")).strip() or "user"
        content = item.get("content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if str(part.get("type", "")) == "text":
                    text_parts.append(str(part.get("text", "")))
            normalized = "\n".join(part for part in text_parts if part).strip()
        else:
            normalized = str(content or "").strip()
        if not normalized:
            continue
        source_messages.append({"role": role, "content": normalized[:400]})
    return source_messages


def _heuristic_title_from_messages(completion_messages: list[dict[str, Any]], fallback: str) -> str:
    for item in completion_messages:
        if str(item.get("role", "")).strip() != "user":
            continue
        content = item.get("content", "")
        if isinstance(content, list):
            parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
            text = " ".join(part for part in parts if part).strip()
        else:
            text = str(content or "").strip()
        if not text:
            continue
        text = re.sub(r"\[附件\].*", "", text)
        text = re.sub(r"^(帮我|请帮我|麻烦你|请问|我想|我要|我需要)", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        text = text[:16].strip(" ，。！？；：,.!?:;")
        return _normalize_title(text, fallback)
    return fallback


def generate_conversation_title(
    *,
    selected_provider: str,
    upstream_model: str,
    completion_messages: list[dict[str, Any]],
    openai_client: Any,
    google_client: Any,
    fallback_title: str,
) -> str:
    prompt = (
        "你是聊天标题生成器。请根据对话生成一个中文短标题。"
        "硬性要求：1) 4到12个字；2) 只输出标题本身；3) 不要句子、不要解释、不要标点结尾；"
        "4) 不要出现‘帮我’‘请问’‘下面是’‘一份可直接用的’这类废话。"
        "好标题示例：Python图片批改名、成都旅行计划、Nginx反代排错。"
    )
    title_source = _build_title_source_messages(completion_messages)
    heuristic_fallback = _heuristic_title_from_messages(completion_messages, fallback_title)

    try:
        if selected_provider == PROVIDER_OPENAI:
            if openai_client is None:
                return heuristic_fallback
            response = openai_client.chat.completions.create(
                model=upstream_model,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(title_source, ensure_ascii=False),
                    },
                ],
            )
            choice = response.choices[0] if getattr(response, "choices", None) else None
            content = getattr(getattr(choice, "message", None), "content", "") if choice else ""
            candidate = _extract_title_from_text(str(content or ""), heuristic_fallback)
            if len(candidate) > 16 or any(token in candidate for token in ("下面", "可以", "支持", "脚本", "说明")):
                return heuristic_fallback
            return candidate

        if selected_provider == PROVIDER_GOOGLE:
            if google_client is None:
                return heuristic_fallback
            response = google_client.models.generate_content(
                model=upstream_model,
                contents=[
                    {"role": "user", "parts": [{"text": prompt}]},
                    {
                        "role": "user",
                        "parts": [{"text": json.dumps(title_source, ensure_ascii=False)}],
                    },
                ],
            )
            text = getattr(response, "text", "")
            candidate = _extract_title_from_text(str(text or ""), heuristic_fallback)
            if len(candidate) > 16 or any(token in candidate for token in ("下面", "可以", "支持", "脚本", "说明")):
                return heuristic_fallback
            return candidate
    except OpenAIError:
        logger.exception("生成会话标题失败(OpenAI): 模型=%s", upstream_model)
        return fallback_title
    except Exception:
        logger.exception("生成会话标题失败: 来源=%s 模型=%s", selected_provider, upstream_model)
        return fallback_title

    return fallback_title
