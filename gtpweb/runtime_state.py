from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from dotenv import dotenv_values
from flask import Flask, current_app
from openai import OpenAI

from gtpweb.ai_providers import ModelOption, build_model_options
from gtpweb.attachments import parse_allowed_attachment_exts
from gtpweb.config import AppConfig, parse_models
from gtpweb.utils import safe_int

HOT_RELOADABLE_ENV_KEYS = {
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODELS",
    "GOOGLE_API_KEY",
    "GOOGLE_MODELS",
    "MAX_UPLOAD_MB",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_TEXT_FILE_CHARS",
    "ALLOWED_ATTACHMENT_EXTS",
}


@dataclass
class RuntimeSettings:
    openai_base_url: str
    openai_api_key: str
    openai_models: list[str]
    google_api_key: str
    google_models: list[str]
    models: list[str]
    model_options: tuple[ModelOption, ...]
    max_upload_mb: int
    max_upload_bytes: int
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

    def choose_models(key: str, fallback: list[str]) -> list[str]:
        if key not in env_values:
            return list(fallback)
        raw_models = str(env_values[key]).strip()
        return parse_models(raw_models, allow_empty=True)

    def choose_allowed_exts(fallback: set[str]) -> set[str]:
        if "ALLOWED_ATTACHMENT_EXTS" not in env_values:
            return set(fallback)
        raw_exts = str(env_values["ALLOWED_ATTACHMENT_EXTS"]).strip()
        return parse_allowed_attachment_exts(raw_exts) if raw_exts else set(fallback)

    openai_base_url = choose_text("OPENAI_BASE_URL", base_config.openai_base_url, allow_empty=True)
    openai_api_key = choose_text("OPENAI_API_KEY", base_config.openai_api_key, allow_empty=True)
    openai_models = choose_models("OPENAI_MODELS", base_config.openai_models)
    google_api_key = choose_text("GOOGLE_API_KEY", base_config.google_api_key, allow_empty=True)
    google_models = choose_models("GOOGLE_MODELS", base_config.google_models)

    if openai_models and not openai_base_url:
        raise ValueError("OPENAI_BASE_URL is required when OPENAI_MODELS is configured.")
    if openai_models and not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when OPENAI_MODELS is configured.")
    if google_models and not google_api_key:
        raise ValueError("GOOGLE_API_KEY is required when GOOGLE_MODELS is configured.")

    model_options = build_model_options(openai_models, google_models)
    models = [item.id for item in model_options]
    max_upload_mb = choose_int("MAX_UPLOAD_MB", base_config.max_upload_mb)
    max_attachments_per_message = choose_int(
        "MAX_ATTACHMENTS_PER_MESSAGE",
        base_config.max_attachments_per_message,
    )
    max_text_file_chars = choose_int("MAX_TEXT_FILE_CHARS", base_config.max_text_file_chars)
    allowed_attachment_exts = choose_allowed_exts(base_config.allowed_attachment_exts)

    return RuntimeSettings(
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        openai_models=openai_models,
        google_api_key=google_api_key,
        google_models=google_models,
        models=models,
        model_options=model_options,
        max_upload_mb=max_upload_mb,
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_attachments_per_message=max_attachments_per_message,
        max_text_file_chars=max_text_file_chars,
        allowed_attachment_exts=allowed_attachment_exts,
    )


def _build_openai_client(
    settings: RuntimeSettings,
    openai_client_factory: Callable[..., OpenAI],
) -> OpenAI | None:
    if not settings.openai_models:
        return None
    return openai_client_factory(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def _build_google_client(
    settings: RuntimeSettings,
    google_client_factory: Callable[..., Any],
) -> Any | None:
    if not settings.google_models:
        return None
    return google_client_factory(api_key=settings.google_api_key)


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


def apply_runtime_env_values(
    app: Flask,
    base_config: AppConfig,
    new_env_values: dict[str, str],
) -> dict[str, list[str]]:
    runtime_state: RuntimeState = app.extensions["runtime_state"]
    old_env_values = dict(runtime_state.env_values)
    old_settings = runtime_state.settings
    new_settings = build_runtime_settings(base_config, env_values=new_env_values)

    changed_keys = sorted(
        key
        for key in (set(old_env_values) | set(new_env_values))
        if old_env_values.get(key, "") != new_env_values.get(key, "")
    )
    applied_keys = [key for key in changed_keys if key in HOT_RELOADABLE_ENV_KEYS]
    restart_required_keys = [key for key in changed_keys if key not in HOT_RELOADABLE_ENV_KEYS]

    runtime_state.settings = new_settings
    runtime_state.env_values = dict(new_env_values)

    if (
        old_settings.openai_base_url != new_settings.openai_base_url
        or old_settings.openai_api_key != new_settings.openai_api_key
        or old_settings.openai_models != new_settings.openai_models
    ):
        openai_client_factory = app.extensions["openai_client_factory"]
        runtime_state.openai_client = _build_openai_client(new_settings, openai_client_factory)

    if (
        old_settings.google_api_key != new_settings.google_api_key
        or old_settings.google_models != new_settings.google_models
    ):
        google_client_factory = app.extensions["google_client_factory"]
        runtime_state.google_client = _build_google_client(new_settings, google_client_factory)

    return {
        "applied_keys": applied_keys,
        "restart_required_keys": restart_required_keys,
    }
