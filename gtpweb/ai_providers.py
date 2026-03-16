"""
AI 提供商配置和处理模块

本模块负责管理 OpenAI 和 Google AI 提供商的模型配置，
包括模型选项解析、对话设置构建、以及 API 调用格式的转换。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

from gtpweb.openai_stream import get_obj_value, to_dict
from gtpweb.utils import model_name_matches_patterns

# 提供商常量
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"

# 提供商显示名称
PROVIDER_LABELS = {
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_GOOGLE: "Google Gemini",
}


@dataclass(frozen=True)
class OpenAIReasoningSettings:
    """
    OpenAI 推理设置

    Attributes:
        enabled: 是否启用推理
        effort: 推理强度（如 "low", "medium", "high"）
        summary: 推理摘要
        effort_options: 可用的推理强度选项列表
    """
    enabled: bool = True
    effort: str = ""
    summary: str = ""
    effort_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoogleThinkingSettings:
    """
    Google Gemini Thinking 设置

    Attributes:
        enabled: 是否启用 Thinking
        include_thoughts: 是否包含思考过程
        level: Thinking 级别
        level_options: 可用的级别选项列表
    """
    enabled: bool = True
    include_thoughts: bool = True
    level: str = ""
    level_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationModelSettings:
    """
    对话级别的模型设置

    这些设置可以覆盖模型的默认设置。

    Attributes:
        reasoning_effort: OpenAI 推理强度（覆盖默认值）
        thinking_level: Google Thinking 级别（覆盖默认值）
    """
    reasoning_effort: str = ""
    thinking_level: str = ""


@dataclass(frozen=True)
class ProviderModelConfig:
    """
    单个提供商的模型配置

    Attributes:
        name: 模型名称（API 使用的名称）
        label: 模型显示标签
        openai_reasoning: OpenAI 特定的推理设置
        google_thinking: Google 特定的 Thinking 设置
    """
    name: str
    label: str
    openai_reasoning: OpenAIReasoningSettings | None = None
    google_thinking: GoogleThinkingSettings | None = None


@dataclass(frozen=True)
class ModelOption:
    """
    模型选项（前端可用的模型）

    Attributes:
        id: 模型唯一标识符（格式：provider:model_name）
        provider: 提供商名称
        model_name: 模型名称
        label: 模型显示标签
        group_label: 分组标签（提供商名称）
        openai_reasoning: OpenAI 推理设置
        google_thinking: Google Thinking 设置
    """
    id: str
    provider: str
    model_name: str
    label: str
    group_label: str
    openai_reasoning: OpenAIReasoningSettings | None = None
    google_thinking: GoogleThinkingSettings | None = None


@dataclass(frozen=True)
class ModelGroup:
    """
    模型分组（按提供商分组）

    Attributes:
        key: 分组键（提供商名称）
        label: 分组标签
        options: 该组下的模型选项列表
    """
    key: str
    label: str
    options: tuple[ModelOption, ...]


# Data URL 正则表达式
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def supports_google_thinking(model_name: str, model_patterns: Iterable[str]) -> bool:
    """
    判断模型是否支持 Google Thinking

    Args:
        model_name: 模型名称
        model_patterns: 模型名称匹配模式列表

    Returns:
        是否支持 Thinking 功能
    """
    return model_name_matches_patterns(model_name, model_patterns)


def _coerce_provider_model_config(model_config: ProviderModelConfig | str) -> ProviderModelConfig:
    """
    将模型配置转换为统一的 ProviderModelConfig 对象

    Args:
        model_config: 模型配置（可以是字符串或 ProviderModelConfig）

    Returns:
        标准化的 ProviderModelConfig 对象
    """
    if isinstance(model_config, ProviderModelConfig):
        return model_config
    model_name = str(model_config or "").strip()
    return ProviderModelConfig(name=model_name, label=model_name)


def build_model_option(provider: str, model_config: ProviderModelConfig) -> ModelOption:
    """
    构建模型选项

    Args:
        provider: 提供商名称
        model_config: 模型配置

    Returns:
        模型选项对象
    """
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
    """
    构建所有可用模型选项

    Args:
        openai_models: OpenAI 模型列表
        google_models: Google 模型列表

    Returns:
        所有模型选项的元组

    Raises:
        ValueError: 当没有配置任何模型时
    """
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
    """
    按提供商构建模型分组

    Args:
        model_options: 模型选项列表

    Returns:
        模型分组元组（按提供商分组）
    """
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
    """
    根据模型值解析模型选项

    支持通过 ID（如 "openai:gpt-4"）或模型名称（如 "gpt-4"）查找。

    Args:
        model_value: 模型值
        model_options: 可用模型选项列表

    Returns:
        匹配的模型选项，未找到则返回 None
    """
    normalized = str(model_value or "").strip()
    options_tuple = tuple(model_options)

    if not options_tuple:
        return None
    if not normalized:
        return options_tuple[0]

    # 优先匹配 ID
    for option in options_tuple:
        if option.id == normalized:
            return option

    # 其次匹配模型名称
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
    """
    标准化模型选择

    尝试解析模型值，返回有效的模型 ID。
    如果找不到匹配的模型，可选择回退到第一个模型或返回原值。

    Args:
        model_value: 模型值
        model_options: 可用模型选项列表
        fallback_to_first: 是否回退到第一个模型

    Returns:
        标准化的模型 ID
    """
    resolved = resolve_model_option(model_value, model_options)
    if resolved is not None:
        return resolved.id

    options_tuple = tuple(model_options)
    if fallback_to_first and options_tuple:
        return options_tuple[0].id

    return str(model_value or "").strip()


def _normalize_choice_value(raw_value: Any) -> str:
    """
    标准化选项值

    Args:
        raw_value: 原始值

    Returns:
        转小写后的字符串
    """
    return str(raw_value or "").strip().lower()


def _resolve_selectable_value(
    *,
    requested_value: Any,
    default_value: str,
    selectable_values: tuple[str, ...],
    unsupported_message: str,
    invalid_message: str,
    strict: bool,
) -> str:
    """
    解析可选择的值

    Args:
        requested_value: 请求的值
        default_value: 默认值
        selectable_values: 可选值列表
        unsupported_message: 不支持时的错误消息
        invalid_message: 无效时的错误消息
        strict: 是否严格模式（严格模式下抛出异常）

    Returns:
        解析后的值

    Raises:
        ValueError: 当 strict=True 且值无效时
    """
    normalized_default = _normalize_choice_value(default_value)
    if not normalized_default and selectable_values:
        normalized_default = selectable_values[0]

    normalized_requested = _normalize_choice_value(requested_value)
    if not normalized_requested:
        return normalized_default

    if selectable_values:
        if normalized_requested in selectable_values:
            return normalized_requested
        if strict:
            raise ValueError(invalid_message)
        return normalized_default

    if not normalized_default:
        if strict:
            raise ValueError(unsupported_message)
        return ""

    if normalized_requested == normalized_default:
        return normalized_requested
    if strict:
        raise ValueError(invalid_message)
    return normalized_default


def resolve_conversation_model_settings(
    model_option: ModelOption | None,
    *,
    reasoning_effort: Any = "",
    thinking_level: Any = "",
    strict: bool = False,
) -> ConversationModelSettings:
    """
    解析对话模型设置

    根据模型选项和请求的设置，构建对话级别的模型配置。

    Args:
        model_option: 模型选项
        reasoning_effort: OpenAI 推理强度
        thinking_level: Google Thinking 级别
        strict: 是否严格模式

    Returns:
        对话模型设置

    Raises:
        ValueError: 当 strict=True 且设置不支持时
    """
    if model_option is None:
        return ConversationModelSettings()

    # 处理 OpenAI 推理设置
    if model_option.provider == PROVIDER_OPENAI:
        reasoning_settings = model_option.openai_reasoning
        if reasoning_settings is None or not reasoning_settings.enabled:
            if _normalize_choice_value(reasoning_effort) and strict:
                raise ValueError("当前模型不支持切换 effort")
            return ConversationModelSettings()
        return ConversationModelSettings(
            reasoning_effort=_resolve_selectable_value(
                requested_value=reasoning_effort,
                default_value=reasoning_settings.effort,
                selectable_values=reasoning_settings.effort_options,
                unsupported_message="当前模型不支持切换 effort",
                invalid_message="无效的 effort",
                strict=strict,
            ),
        )

    # 处理 Google Thinking 设置
    if model_option.provider == PROVIDER_GOOGLE:
        thinking_settings = model_option.google_thinking
        if thinking_settings is None or not thinking_settings.enabled:
            if _normalize_choice_value(thinking_level) and strict:
                raise ValueError("当前模型不支持切换 level")
            return ConversationModelSettings()
        return ConversationModelSettings(
            thinking_level=_resolve_selectable_value(
                requested_value=thinking_level,
                default_value=thinking_settings.level,
                selectable_values=thinking_settings.level_options,
                unsupported_message="当前模型不支持切换 level",
                invalid_message="无效的 level",
                strict=strict,
            ),
        )

    return ConversationModelSettings()


def build_effective_openai_reasoning_settings(
    model_option: ModelOption,
    conversation_settings: ConversationModelSettings,
) -> OpenAIReasoningSettings | None:
    """
    构建有效的 OpenAI 推理设置

    将对话设置与模型默认设置合并。

    Args:
        model_option: 模型选项
        conversation_settings: 对话设置

    Returns:
        合并后的推理设置
    """
    reasoning_settings = model_option.openai_reasoning
    if reasoning_settings is None:
        return None
    if conversation_settings.reasoning_effort:
        return replace(reasoning_settings, effort=conversation_settings.reasoning_effort)
    return reasoning_settings


def build_effective_google_thinking_settings(
    model_option: ModelOption,
    conversation_settings: ConversationModelSettings,
) -> GoogleThinkingSettings | None:
    """
    构建有效的 Google Thinking 设置

    将对话设置与模型默认设置合并。

    Args:
        model_option: 模型选项
        conversation_settings: 对话设置

    Returns:
        合并后的 Thinking 设置
    """
    thinking_settings = model_option.google_thinking
    if thinking_settings is None:
        return None
    if conversation_settings.thinking_level:
        return replace(
            thinking_settings,
            level=conversation_settings.thinking_level,
        )
    return thinking_settings


def serialize_model_option(model_option: ModelOption) -> dict[str, Any]:
    """
    序列化模型选项为字典

    Args:
        model_option: 模型选项

    Returns:
        序列化后的字典
    """
    item: dict[str, Any] = {
        "id": model_option.id,
        "provider": model_option.provider,
        "model_name": model_option.model_name,
        "label": model_option.label,
        "group_label": model_option.group_label,
    }

    # 序列化 OpenAI 推理设置
    if model_option.openai_reasoning is not None:
        item["reasoning"] = {
            "enabled": model_option.openai_reasoning.enabled,
            "effort": model_option.openai_reasoning.effort,
            "summary": model_option.openai_reasoning.summary,
            "effort_options": list(model_option.openai_reasoning.effort_options),
        }

    # 序列化 Google Thinking 设置
    if model_option.google_thinking is not None:
        item["thinking"] = {
            "enabled": model_option.google_thinking.enabled,
            "include_thoughts": model_option.google_thinking.include_thoughts,
            "level": model_option.google_thinking.level,
            "level_options": list(model_option.google_thinking.level_options),
        }

    return item


def serialize_model_options(model_options: Iterable[ModelOption]) -> list[dict[str, Any]]:
    """
    序列化模型选项列表

    Args:
        model_options: 模型选项列表

    Returns:
        序列化后的字典列表
    """
    return [serialize_model_option(option) for option in model_options]


def _build_google_part_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """
    从消息项构建 Google API 的 Part 对象

    Args:
        item: 消息项（包含 type 和内容）

    Returns:
        Google API Part 对象，不支持的类型返回 None
    """
    part_type = str(item.get("type", "")).strip().lower()

    # 处理文本类型
    if part_type == "text":
        text = str(item.get("text", ""))
        return {"text": text} if text else None

    # 只处理图片类型
    if part_type != "image_url":
        return None

    image_url = item.get("image_url")
    if not isinstance(image_url, dict):
        return None

    url = str(image_url.get("url", "")).strip()

    # 解析 Data URL
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
    """
    从消息内容构建 Google API 的 Parts 列表

    Args:
        content: 消息内容（字符串或列表）

    Returns:
        Google API Parts 列表
    """
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
    """
    构建 Google API 的消息格式

    将 OpenAI 格式的消息转换为 Google API 格式。

    Args:
        messages: OpenAI 格式的消息列表

    Returns:
        Google API 格式的消息列表
    """
    contents: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role", "user")).strip().lower() or "user"
        parts = _build_google_parts(message.get("content"))
        if not parts:
            continue

        # 将 assistant 角色转换为 model
        if role == "assistant":
            contents.append({"role": "model", "parts": parts})
            continue

        # 将 system 角色转换为特殊用户消息
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
    """
    构建 Google API 的生成配置

    Args:
        thinking_settings: Thinking 设置

    Returns:
        GenerateContentConfig 对象，如果未启用 Thinking 则返回 None

    Raises:
        RuntimeError: 当缺少 google-genai 依赖时
    """
    if thinking_settings is None or not thinking_settings.enabled:
        return None

    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "当前环境缺少 `google-genai` 依赖，请先执行 `pip install -r requirements.txt`。"
        ) from exc

    thinking_kwargs: dict[str, Any] = {"include_thoughts": thinking_settings.include_thoughts}

    if thinking_settings.level:
        thinking_kwargs["thinking_level"] = thinking_settings.level

    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(**thinking_kwargs)
    )


def _extract_google_parts(event_obj: Any) -> list[dict[str, Any]]:
    """
    从 Google 流式事件中提取 Parts

    Args:
        event_obj: 流式事件对象

    Returns:
        Parts 列表
    """
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
    """
    从 Google 流式事件中提取文本增量

    Args:
        event_obj: 流式事件对象

    Returns:
        提取的文本内容
    """
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
    """
    从 Google 流式事件中提取推理增量

    Args:
        event_obj: 流式事件对象

    Returns:
        提取的推理内容
    """
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
