"""
运行时状态管理模块

负责管理应用的运行时状态和热更新配置，包括：
- 运行时设置管理
- AI 客户端初始化
- 环境变量热更新
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable

from dotenv import dotenv_values
from flask import Flask, current_app
from openai import OpenAI

from gtpweb.ai_providers import ModelOption, build_model_options
from gtpweb.attachments import parse_allowed_attachment_exts
from gtpweb.config import AppConfig, load_model_catalog, parse_bool, parse_image_tool_provider
from gtpweb.utils import safe_int

# 可热更新的环境变量键
HOT_RELOADABLE_ENV_KEYS = {
    "IMAGE_TOOL_PROVIDER",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "GOOGLE_BASE_URL",
    "GOOGLE_API_KEY",
    "MAX_UPLOAD_MB",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_TEXT_FILE_CHARS",
    "ALLOWED_ATTACHMENT_EXTS",
}


@dataclass
class RuntimeSettings:
    image_tool_provider: str
    openai_base_url: str
    openai_api_key: str
    openai_models: list[str]
    openai_image_model: str
    google_base_url: str
    google_api_key: str
    google_models: list[str]
    google_image_model: str
    models: list[str]
    model_options: tuple[ModelOption, ...]
    max_upload_mb: int
    max_upload_bytes: int
    max_pdf_upload_mb: int
    max_pdf_upload_bytes: int
    max_attachments_per_message: int
    max_text_file_chars: int
    allowed_attachment_exts: set[str]


@dataclass
class RuntimeState:
    settings: RuntimeSettings
    env_values: dict[str, str]
    openai_client: OpenAI | None
    google_client: Any | None



def _normalize_env_values(raw_values: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw_values.items():
        if not key or value is None:
            continue
        normalized[str(key)] = str(value)
    return normalized



def read_env_file_values(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    return _normalize_env_values(dotenv_values(env_file))



def read_env_files_values(env_files: tuple[Path, ...]) -> dict[str, str]:
    merged_values: dict[str, str] = {}
    for env_file in env_files:
        merged_values.update(read_env_file_values(env_file))
    return merged_values



def parse_env_text(raw_text: str) -> dict[str, str]:
    return _normalize_env_values(dotenv_values(stream=StringIO(raw_text)))



def build_runtime_settings(
    base_config: AppConfig,
    *,
    env_values: dict[str, str],
) -> RuntimeSettings:
    def choose_text(key: str, fallback: str, *, allow_empty: bool = False) -> str:
        if key not in env_values:
            return fallback
        value = str(env_values[key]).strip()
        if allow_empty:
            return value
        return value or fallback

    def choose_int(key: str, fallback: int) -> int:
        if key not in env_values:
            return fallback
        parsed = safe_int(str(env_values[key]))
        return parsed or fallback

    def choose_allowed_exts(fallback: set[str]) -> set[str]:
        if "ALLOWED_ATTACHMENT_EXTS" not in env_values:
            return set(fallback)
        raw_exts = str(env_values["ALLOWED_ATTACHMENT_EXTS"]).strip()
        return parse_allowed_attachment_exts(raw_exts) if raw_exts else set(fallback)

    model_catalog = load_model_catalog(base_config.model_config_file)

    image_tool_provider = parse_image_tool_provider(
        choose_text("IMAGE_TOOL_PROVIDER", base_config.image_tool_provider)
    )
    openai_base_url = choose_text("OPENAI_BASE_URL", base_config.openai_base_url, allow_empty=True)
    openai_api_key = choose_text("OPENAI_API_KEY", base_config.openai_api_key, allow_empty=True)
    openai_models = [item.name for item in model_catalog.openai.models]
    openai_image_model = model_catalog.openai.image_model
    google_base_url = choose_text("GOOGLE_BASE_URL", base_config.google_base_url, allow_empty=True)
    google_api_key = choose_text("GOOGLE_API_KEY", base_config.google_api_key, allow_empty=True)
    google_models = [item.name for item in model_catalog.google.models]
    google_image_model = model_catalog.google.image_model

    use_openai = bool(openai_models or openai_image_model)
    use_google = bool(google_models or google_image_model)

    if use_openai and not openai_base_url:
        raise ValueError("OPENAI_BASE_URL is required when OpenAI is configured.")
    if use_openai and not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when OpenAI is configured.")
    if use_google and not google_api_key:
        raise ValueError("GOOGLE_API_KEY is required when Google is configured.")

    model_options = build_model_options(model_catalog.openai.models, model_catalog.google.models)
    models = [item.id for item in model_options]
    max_upload_mb = choose_int("MAX_UPLOAD_MB", base_config.max_upload_mb)
    max_pdf_upload_mb = choose_int("MAX_PDF_UPLOAD_MB", base_config.max_pdf_upload_mb)
    max_attachments_per_message = choose_int(
        "MAX_ATTACHMENTS_PER_MESSAGE",
        base_config.max_attachments_per_message,
    )
    max_text_file_chars = choose_int("MAX_TEXT_FILE_CHARS", base_config.max_text_file_chars)
    allowed_attachment_exts = choose_allowed_exts(base_config.allowed_attachment_exts)

    return RuntimeSettings(
        image_tool_provider=image_tool_provider,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        openai_models=openai_models,
        openai_image_model=openai_image_model,
        google_base_url=google_base_url,
        google_api_key=google_api_key,
        google_models=google_models,
        google_image_model=google_image_model,
        models=models,
        model_options=model_options,
        max_upload_mb=max_upload_mb,
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_pdf_upload_mb=max_pdf_upload_mb,
        max_pdf_upload_bytes=max_pdf_upload_mb * 1024 * 1024,
        max_attachments_per_message=max_attachments_per_message,
        max_text_file_chars=max_text_file_chars,
        allowed_attachment_exts=allowed_attachment_exts,
    )



def _build_openai_client(
    settings: RuntimeSettings,
    openai_client_factory: Callable[..., OpenAI],
) -> OpenAI | None:
    if not (settings.openai_models or settings.openai_image_model):
        return None
    return openai_client_factory(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )



def _build_google_client(
    settings: RuntimeSettings,
    google_client_factory: Callable[..., Any],
) -> Any | None:
    if not (settings.google_models or settings.google_image_model):
        return None
    return google_client_factory(
        api_key=settings.google_api_key,
        base_url=settings.google_base_url,
    )



def create_runtime_state(
    base_config: AppConfig,
    openai_client_factory: Callable[..., OpenAI],
    google_client_factory: Callable[..., Any],
) -> RuntimeState:
    env_values = read_env_files_values(base_config.env_files)
    settings = build_runtime_settings(base_config, env_values=env_values)
    return RuntimeState(
        settings=settings,
        env_values=env_values,
        openai_client=_build_openai_client(settings, openai_client_factory),
        google_client=_build_google_client(settings, google_client_factory),
    )



def get_runtime_state() -> RuntimeState:
    return current_app.extensions["runtime_state"]



def _snapshot_model_config_keys(model_options: Iterable[ModelOption], provider: str) -> tuple[dict[str, Any], ...]:
    snapshots: list[dict[str, Any]] = []
    for option in model_options:
        if option.provider != provider:
            continue
        item: dict[str, Any] = {
            "name": option.model_name,
            "label": option.label,
        }
        if provider == "openai":
            item["reasoning"] = (
                None
                if option.openai_reasoning is None
                else {
                    "enabled": option.openai_reasoning.enabled,
                    "effort": option.openai_reasoning.effort,
                    "summary": option.openai_reasoning.summary,
                    "effort_options": option.openai_reasoning.effort_options,
                }
            )
        elif provider == "google":
            item["thinking"] = (
                None
                if option.google_thinking is None
                else {
                    "enabled": option.google_thinking.enabled,
                    "include_thoughts": option.google_thinking.include_thoughts,
                    "level": option.google_thinking.level,
                    "level_options": option.google_thinking.level_options,
                }
            )
        snapshots.append(item)
    return tuple(snapshots)



def _collect_runtime_setting_changes(
    old_settings: RuntimeSettings,
    new_settings: RuntimeSettings,
) -> list[str]:
    changed_keys: list[str] = []
    if old_settings.image_tool_provider != new_settings.image_tool_provider:
        changed_keys.append("IMAGE_TOOL_PROVIDER")
    if old_settings.openai_base_url != new_settings.openai_base_url:
        changed_keys.append("OPENAI_BASE_URL")
    if old_settings.openai_api_key != new_settings.openai_api_key:
        changed_keys.append("OPENAI_API_KEY")
    if old_settings.openai_models != new_settings.openai_models:
        changed_keys.append("OPENAI_MODELS")
    if old_settings.openai_image_model != new_settings.openai_image_model:
        changed_keys.append("OPENAI_IMAGE_MODEL")
    if _snapshot_model_config_keys(old_settings.model_options, "openai") != _snapshot_model_config_keys(
        new_settings.model_options,
        "openai",
    ):
        changed_keys.append("OPENAI_MODEL_CONFIG")
    if old_settings.google_base_url != new_settings.google_base_url:
        changed_keys.append("GOOGLE_BASE_URL")
    if old_settings.google_api_key != new_settings.google_api_key:
        changed_keys.append("GOOGLE_API_KEY")
    if old_settings.google_models != new_settings.google_models:
        changed_keys.append("GOOGLE_MODELS")
    if old_settings.google_image_model != new_settings.google_image_model:
        changed_keys.append("GOOGLE_IMAGE_MODEL")
    if _snapshot_model_config_keys(old_settings.model_options, "google") != _snapshot_model_config_keys(
        new_settings.model_options,
        "google",
    ):
        changed_keys.append("GOOGLE_MODEL_CONFIG")
    if old_settings.max_upload_mb != new_settings.max_upload_mb:
        changed_keys.append("MAX_UPLOAD_MB")
    if old_settings.max_attachments_per_message != new_settings.max_attachments_per_message:
        changed_keys.append("MAX_ATTACHMENTS_PER_MESSAGE")
    if old_settings.max_text_file_chars != new_settings.max_text_file_chars:
        changed_keys.append("MAX_TEXT_FILE_CHARS")
    if old_settings.allowed_attachment_exts != new_settings.allowed_attachment_exts:
        changed_keys.append("ALLOWED_ATTACHMENT_EXTS")
    return changed_keys



def apply_runtime_config_values(
    app: Flask,
    base_config: AppConfig,
    new_env_values: dict[str, str],
) -> dict[str, list[str]]:
    runtime_state: RuntimeState = app.extensions["runtime_state"]
    old_env_values = dict(runtime_state.env_values)
    old_settings = runtime_state.settings
    new_settings = build_runtime_settings(base_config, env_values=new_env_values)

    changed_env_keys = sorted(
        key
        for key in (set(old_env_values) | set(new_env_values))
        if old_env_values.get(key, "") != new_env_values.get(key, "")
    )
    changed_setting_keys = _collect_runtime_setting_changes(old_settings, new_settings)

    applied_keys = sorted(set(key for key in changed_env_keys if key in HOT_RELOADABLE_ENV_KEYS) | set(changed_setting_keys))
    restart_required_keys = [key for key in changed_env_keys if key not in HOT_RELOADABLE_ENV_KEYS]

    runtime_state.settings = new_settings
    runtime_state.env_values = dict(new_env_values)

    if (
        old_settings.openai_base_url != new_settings.openai_base_url
        or old_settings.openai_api_key != new_settings.openai_api_key
        or old_settings.openai_models != new_settings.openai_models
        or old_settings.openai_image_model != new_settings.openai_image_model
    ):
        openai_client_factory = app.extensions["openai_client_factory"]
        runtime_state.openai_client = _build_openai_client(new_settings, openai_client_factory)

    if (
        old_settings.google_base_url != new_settings.google_base_url
        or old_settings.google_api_key != new_settings.google_api_key
        or old_settings.google_models != new_settings.google_models
        or old_settings.google_image_model != new_settings.google_image_model
    ):
        google_client_factory = app.extensions["google_client_factory"]
        runtime_state.google_client = _build_google_client(new_settings, google_client_factory)

    return {
        "applied_keys": applied_keys,
        "restart_required_keys": restart_required_keys,
    }



def apply_runtime_env_values(
    app: Flask,
    base_config: AppConfig,
    new_env_values: dict[str, str],
) -> dict[str, list[str]]:
    return apply_runtime_config_values(app, base_config, new_env_values)
