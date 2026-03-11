from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from gtpweb.openai_stream import get_obj_value, to_dict
from gtpweb.utils import model_name_matches_patterns

PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"

PROVIDER_LABELS = {
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_GOOGLE: "Google Gemini",
}


@dataclass(frozen=True)
class OpenAIReasoningSettings:
    enabled: bool = True
    effort: str = ""
    summary: str = ""


@dataclass(frozen=True)
class GoogleThinkingSettings:
    enabled: bool = True
    include_thoughts: bool = True
    level: str = ""
    budget: int | None = None


@dataclass(frozen=True)
class ProviderModelConfig:
    name: str
    label: str
    openai_reasoning: OpenAIReasoningSettings | None = None
    google_thinking: GoogleThinkingSettings | None = None


@dataclass(frozen=True)
class ModelOption:
    id: str
    provider: str
    model_name: str
    label: str
    group_label: str
    openai_reasoning: OpenAIReasoningSettings | None = None
    google_thinking: GoogleThinkingSettings | None = None


@dataclass(frozen=True)
class ModelGroup:
    key: str
    label: str
    options: tuple[ModelOption, ...]


_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def supports_google_thinking(model_name: str, model_patterns: Iterable[str]) -> bool:
    return model_name_matches_patterns(model_name, model_patterns)


def _coerce_provider_model_config(model_config: ProviderModelConfig | str) -> ProviderModelConfig:
    if isinstance(model_config, ProviderModelConfig):
        return model_config
    model_name = str(model_config or "").strip()
    return ProviderModelConfig(name=model_name, label=model_name)


def build_model_option(provider: str, model_config: ProviderModelConfig) -> ModelOption:
    model_config = _coerce_provider_model_config(model_config)
    group_label = PROVIDER_LABELS.get(provider, provider)
    return ModelOption(
        id=f"{provider}:{model_config.name}",
        provider=provider,
        model_name=model_config.name,
        label=model_config.label,
        group_label=group_label,
        openai_reasoning=model_config.openai_reasoning,
        google_thinking=model_config.google_thinking,
    )


def build_model_options(
    openai_models: Iterable[ProviderModelConfig | str],
    google_models: Iterable[ProviderModelConfig | str],
) -> tuple[ModelOption, ...]:
    options: list[ModelOption] = []
    for provider, model_configs in (
        (PROVIDER_OPENAI, openai_models),
        (PROVIDER_GOOGLE, google_models),
    ):
        for model_config in model_configs:
            options.append(build_model_option(provider, model_config))
    if not options:
        raise ValueError("至少需要配置一个可用的 AI 模型。")
    return tuple(options)


def build_model_groups(model_options: Iterable[ModelOption]) -> tuple[ModelGroup, ...]:
    grouped: list[ModelGroup] = []
    options_tuple = tuple(model_options)
    for provider in (PROVIDER_OPENAI, PROVIDER_GOOGLE):
        provider_options = tuple(option for option in options_tuple if option.provider == provider)
        if not provider_options:
            continue
        grouped.append(
            ModelGroup(
                key=provider,
                label=PROVIDER_LABELS.get(provider, provider),
                options=provider_options,
            )
        )
    return tuple(grouped)


def resolve_model_option(model_value: str, model_options: Iterable[ModelOption]) -> ModelOption | None:
    normalized = str(model_value or "").strip()
    options_tuple = tuple(model_options)
    if not options_tuple:
        return None
    if not normalized:
        return options_tuple[0]

    for option in options_tuple:
        if option.id == normalized:
            return option

    matched_by_name = [option for option in options_tuple if option.model_name == normalized]
    if len(matched_by_name) == 1:
        return matched_by_name[0]
    return None


def normalize_model_selection(
    model_value: str,
    model_options: Iterable[ModelOption],
    *,
    fallback_to_first: bool = False,
) -> str:
    resolved = resolve_model_option(model_value, model_options)
    if resolved is not None:
        return resolved.id

    options_tuple = tuple(model_options)
    if fallback_to_first and options_tuple:
        return options_tuple[0].id
    return str(model_value or "").strip()


def _build_google_part_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    part_type = str(item.get("type", "")).strip().lower()
    if part_type == "text":
        text = str(item.get("text", ""))
        return {"text": text} if text else None
    if part_type != "image_url":
        return None

    image_url = item.get("image_url")
    if not isinstance(image_url, dict):
        return None
    url = str(image_url.get("url", "")).strip()
    match = _DATA_URL_RE.match(url)
    if match is None:
        return {"text": f"[暂不支持的图片地址: {url}]"} if url else None
    return {
        "inline_data": {
            "mime_type": match.group("mime").strip(),
            "data": match.group("data").strip(),
        }
    }


def _build_google_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        text = content.strip()
        return [{"text": text}] if text else []
    if not isinstance(content, list):
        return []

    parts: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        part = _build_google_part_from_item(item)
        if part is not None:
            parts.append(part)
    return parts


def build_google_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip().lower() or "user"
        parts = _build_google_parts(message.get("content"))
        if not parts:
            continue

        if role == "assistant":
            contents.append({"role": "model", "parts": parts})
            continue
        if role == "system":
            combined_text = "\n".join(
                part["text"] for part in parts if isinstance(part.get("text"), str) and part["text"]
            ).strip()
            if combined_text:
                contents.append({"role": "user", "parts": [{"text": f"[系统提示]\n{combined_text}"}]})
            continue

        contents.append({"role": "user", "parts": parts})
    return contents


def build_google_generate_content_config(
    *,
    thinking_settings: GoogleThinkingSettings | None,
) -> Any | None:
    if thinking_settings is None or not thinking_settings.enabled:
        return None

    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "当前环境缺少 `google-genai` 依赖，请先执行 `pip install -r requirements.txt`。"
        ) from exc

    thinking_kwargs: dict[str, Any] = {"include_thoughts": thinking_settings.include_thoughts}
    if thinking_settings.budget is not None:
        thinking_kwargs["thinking_budget"] = thinking_settings.budget
    elif thinking_settings.level:
        thinking_kwargs["thinking_level"] = thinking_settings.level

    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(**thinking_kwargs)
    )


def _extract_google_parts(event_obj: Any) -> list[dict[str, Any]]:
    event_dict = to_dict(event_obj)
    candidates = event_dict.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return []

    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return []
    content = first_candidate.get("content")
    if not isinstance(content, dict):
        return []
    parts = content.get("parts")
    return parts if isinstance(parts, list) else []


def extract_google_text_delta(event_obj: Any) -> str:
    text = get_obj_value(event_obj, "text")
    if isinstance(text, str):
        return text

    fragments: list[str] = []
    for part in _extract_google_parts(event_obj):
        if not isinstance(part, dict):
            continue
        if part.get("thought") is True:
            continue
        fragment = part.get("text")
        if isinstance(fragment, str) and fragment:
            fragments.append(fragment)
    return "".join(fragments)


def extract_google_reasoning_delta(event_obj: Any) -> str:
    fragments: list[str] = []
    for part in _extract_google_parts(event_obj):
        if not isinstance(part, dict):
            continue
        if part.get("thought") is not True:
            continue
        fragment = part.get("text")
        if isinstance(fragment, str) and fragment:
            fragments.append(fragment)
    return "".join(fragments)
