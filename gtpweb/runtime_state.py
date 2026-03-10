from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from dotenv import dotenv_values
from flask import Flask, current_app
from openai import OpenAI

from gtpweb.attachments import parse_allowed_attachment_exts
from gtpweb.config import AppConfig, parse_models
from gtpweb.utils import safe_int

HOT_RELOADABLE_ENV_KEYS = {
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODELS",
    "MAX_UPLOAD_MB",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_TEXT_FILE_CHARS",
    "ALLOWED_ATTACHMENT_EXTS",
}


@dataclass
class RuntimeSettings:
    ai_base_url: str
    ai_api_key: str
    models: list[str]
    max_upload_mb: int
    max_upload_bytes: int
    max_attachments_per_message: int
    max_text_file_chars: int
    allowed_attachment_exts: set[str]


@dataclass
class RuntimeState:
    settings: RuntimeSettings
    env_values: dict[str, str]
    openai_client: OpenAI


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
    current_settings: RuntimeSettings | None = None,
) -> RuntimeSettings:
    previous = current_settings

    def choose_text(key: str, fallback: str) -> str:
        if key not in env_values:
            return fallback
        value = str(env_values[key]).strip()
        return value or fallback

    def choose_int(key: str, fallback: int) -> int:
        if key not in env_values:
            return fallback
        parsed = safe_int(str(env_values[key]))
        return parsed or fallback

    def choose_models(fallback: list[str]) -> list[str]:
        if "AI_MODELS" not in env_values:
            return list(fallback)
        raw_models = str(env_values["AI_MODELS"]).strip()
        return parse_models(raw_models) if raw_models else list(fallback)

    def choose_allowed_exts(fallback: set[str]) -> set[str]:
        if "ALLOWED_ATTACHMENT_EXTS" not in env_values:
            return set(fallback)
        raw_exts = str(env_values["ALLOWED_ATTACHMENT_EXTS"]).strip()
        return parse_allowed_attachment_exts(raw_exts) if raw_exts else set(fallback)

    ai_base_url = choose_text(
        "AI_BASE_URL",
        previous.ai_base_url if previous else base_config.ai_base_url,
    )
    ai_api_key = choose_text(
        "AI_API_KEY",
        previous.ai_api_key if previous else base_config.ai_api_key,
    )
    models = choose_models(previous.models if previous else base_config.models)
    max_upload_mb = choose_int(
        "MAX_UPLOAD_MB",
        previous.max_upload_mb if previous else base_config.max_upload_mb,
    )
    max_attachments_per_message = choose_int(
        "MAX_ATTACHMENTS_PER_MESSAGE",
        previous.max_attachments_per_message
        if previous
        else base_config.max_attachments_per_message,
    )
    max_text_file_chars = choose_int(
        "MAX_TEXT_FILE_CHARS",
        previous.max_text_file_chars if previous else base_config.max_text_file_chars,
    )
    allowed_attachment_exts = choose_allowed_exts(
        previous.allowed_attachment_exts if previous else base_config.allowed_attachment_exts,
    )

    return RuntimeSettings(
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
        models=models,
        max_upload_mb=max_upload_mb,
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_attachments_per_message=max_attachments_per_message,
        max_text_file_chars=max_text_file_chars,
        allowed_attachment_exts=allowed_attachment_exts,
    )


def create_runtime_state(
    base_config: AppConfig,
    openai_client_factory: Callable[..., OpenAI],
) -> RuntimeState:
    env_values = read_env_files_values(base_config.env_files)
    settings = build_runtime_settings(base_config, env_values=env_values)
    openai_client = openai_client_factory(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
    )
    return RuntimeState(
        settings=settings,
        env_values=env_values,
        openai_client=openai_client,
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
    new_settings = build_runtime_settings(
        base_config,
        env_values=new_env_values,
        current_settings=old_settings,
    )

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
        old_settings.ai_base_url != new_settings.ai_base_url
        or old_settings.ai_api_key != new_settings.ai_api_key
    ):
        openai_client_factory = app.extensions["openai_client_factory"]
        runtime_state.openai_client = openai_client_factory(
            api_key=new_settings.ai_api_key,
            base_url=new_settings.ai_base_url,
        )

    return {
        "applied_keys": applied_keys,
        "restart_required_keys": restart_required_keys,
    }
