from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .ai_providers import (
    PROVIDER_GOOGLE,
    PROVIDER_OPENAI,
    GoogleThinkingSettings,
    ModelOption,
    OpenAIReasoningSettings,
    ProviderModelConfig,
    build_model_options,
)
from .attachments import parse_allowed_attachment_exts
from .jsonc import jsonc_loads
from .user_store import load_user_password_map
from .utils import safe_int

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_DIR = BASE_DIR / "config" / "env"
DEFAULT_USERS_FILE = BASE_DIR / "config" / "users.json"
DEFAULT_MODEL_CONFIG_FILE = BASE_DIR / "config" / "models.jsonc"
DEFAULT_DB_FILE = BASE_DIR / "data" / "chat.db"
DEFAULT_UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_LOG_FILE = BASE_DIR / "logs" / "app.log"


@dataclass(frozen=True)
class EnvGroupSpec:
    key: str
    filename: str
    label: str
    description: str


ENV_GROUP_SPECS = (
    EnvGroupSpec(
        key="app",
        filename="app.env",
        label="应用基础配置",
        description="维护应用密钥、登录配置路径、端口、调试开关与图片工具来源。",
    ),
    EnvGroupSpec(
        key="openai",
        filename="openai.env",
        label="OpenAI 接入配置",
        description="维护 OPENAI_BASE_URL 与 OPENAI_API_KEY；模型列表与 reasoning 参数请改 `config/models.jsonc`。",
    ),
    EnvGroupSpec(
        key="google",
        filename="google.env",
        label="Google Gemini 接入配置",
        description="维护 GOOGLE_BASE_URL 与 GOOGLE_API_KEY；模型列表与 thinking 参数请改 `config/models.jsonc`。",
    ),
    EnvGroupSpec(
        key="storage",
        filename="storage.env",
        label="存储路径配置",
        description="维护数据库与上传目录等存储路径。",
    ),
    EnvGroupSpec(
        key="attachments",
        filename="attachments.env",
        label="附件限制配置",
        description="维护附件大小、数量、文本长度与扩展名白名单。",
    ),
    EnvGroupSpec(
        key="logging",
        filename="logging.env",
        label="日志配置",
        description="维护日志级别、日志文件与轮转策略。",
    ),
)


@dataclass(frozen=True)
class ProviderModelCatalog:
    image_model: str
    models: tuple[ProviderModelConfig, ...]


@dataclass(frozen=True)
class ModelCatalog:
    openai: ProviderModelCatalog
    google: ProviderModelCatalog


@dataclass(frozen=True)
class AppConfig:
    secret_key: str
    env_files: tuple[Path, ...]
    env_dir: Path
    users_file: Path
    users: dict[str, str]
    model_config_file: Path
    image_tool_provider: str
    openai_base_url: str
    openai_api_key: str
    openai_models: list[str]
    openai_image_model: str
    google_base_url: str
    google_api_key: str
    google_models: list[str]
    google_image_model: str
    db_file: Path
    upload_dir: Path
    max_upload_mb: int
    max_upload_bytes: int
    max_attachments_per_message: int
    max_text_file_chars: int
    allowed_attachment_exts: set[str]
    models: list[str]
    model_options: tuple[ModelOption, ...]
    log_level: str
    log_file: Path
    log_max_bytes: int
    log_backup_count: int
    log_to_stdout: bool


MISSING = object()


def load_users(users_file: Path) -> dict[str, str]:
    return load_user_password_map(users_file)



def parse_bool(raw_value: str, default: bool) -> bool:
    value = raw_value.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default



def parse_image_tool_provider(raw_value: str) -> str:
    provider = str(raw_value or "").strip().lower() or PROVIDER_OPENAI
    if provider not in {PROVIDER_OPENAI, PROVIDER_GOOGLE}:
        raise ValueError("IMAGE_TOOL_PROVIDER 仅支持 openai 或 google。")
    return provider



def build_grouped_env_files(env_dir: Path) -> tuple[Path, ...]:
    return tuple(env_dir / item.filename for item in ENV_GROUP_SPECS)



def resolve_env_dir() -> Path:
    env_dir = Path(os.getenv("ENV_DIR", str(DEFAULT_ENV_DIR))).expanduser()
    if env_dir.exists() and not env_dir.is_dir():
        raise ValueError("ENV_DIR must point to a directory.")
    return env_dir



def load_env_files(env_files: tuple[Path, ...]) -> None:
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=False)



def _ensure_json_object(raw_value: Any, *, context: str) -> dict[str, Any]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是 JSON 对象")
    return raw_value



def _parse_json_bool(raw_value: Any, *, context: str, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return parse_bool(raw_value, default)
    raise ValueError(f"{context} 必须是布尔值")



def _parse_optional_text(raw_value: Any, *, context: str, lowercase: bool = False) -> str:
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raise ValueError(f"{context} 必须是字符串")
    text = raw_value.strip()
    return text.lower() if lowercase else text



def _parse_reasoning_settings(raw_value: Any, *, context: str) -> OpenAIReasoningSettings | None:
    if raw_value is None or raw_value is False:
        return None
    if raw_value is True:
        raw_value = {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是对象、true/false 或 null")
    return OpenAIReasoningSettings(
        effort=_parse_optional_text(raw_value.get("effort"), context=f"{context}.effort", lowercase=True),
        summary=_parse_optional_text(raw_value.get("summary"), context=f"{context}.summary", lowercase=True),
    )



def _merge_reasoning_settings(
    base_settings: OpenAIReasoningSettings | None,
    override_settings: OpenAIReasoningSettings | None,
) -> OpenAIReasoningSettings | None:
    if override_settings is None:
        return base_settings
    if base_settings is None:
        return override_settings
    return OpenAIReasoningSettings(
        effort=override_settings.effort or base_settings.effort,
        summary=override_settings.summary or base_settings.summary,
    )



def _parse_thinking_settings(raw_value: Any, *, context: str) -> GoogleThinkingSettings | None:
    if raw_value is None or raw_value is False:
        return None
    if raw_value is True:
        raw_value = {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是对象、true/false 或 null")
    budget = safe_int(raw_value.get("budget"))
    return GoogleThinkingSettings(
        include_thoughts=_parse_json_bool(
            raw_value.get("include_thoughts"),
            context=f"{context}.include_thoughts",
            default=True,
        ),
        level=_parse_optional_text(raw_value.get("level"), context=f"{context}.level", lowercase=True),
        budget=budget,
    )



def _merge_thinking_settings(
    base_settings: GoogleThinkingSettings | None,
    override_settings: GoogleThinkingSettings | None,
) -> GoogleThinkingSettings | None:
    if override_settings is None:
        return base_settings
    if base_settings is None:
        return override_settings
    return GoogleThinkingSettings(
        include_thoughts=override_settings.include_thoughts,
        level=override_settings.level or base_settings.level,
        budget=override_settings.budget if override_settings.budget is not None else base_settings.budget,
    )



def _parse_provider_model(
    provider: str,
    raw_item: Any,
    *,
    index: int,
    default_reasoning: OpenAIReasoningSettings | None,
    default_thinking: GoogleThinkingSettings | None,
) -> ProviderModelConfig:
    context = f"{provider}.models[{index}]"
    if isinstance(raw_item, str):
        model_name = raw_item.strip()
        raw_data: dict[str, Any] = {}
    elif isinstance(raw_item, dict):
        raw_data = raw_item
        model_name = _parse_optional_text(raw_data.get("name"), context=f"{context}.name")
    else:
        raise ValueError(f"{context} 必须是字符串或对象")

    if not model_name:
        raise ValueError(f"{context}.name 不能为空")

    label = model_name
    if isinstance(raw_item, dict):
        label = _parse_optional_text(raw_data.get("label"), context=f"{context}.label") or model_name

    openai_reasoning = default_reasoning
    google_thinking = default_thinking

    if provider == PROVIDER_OPENAI and isinstance(raw_item, dict):
        raw_reasoning = raw_data.get("reasoning", MISSING)
        if raw_reasoning is False or raw_reasoning is None:
            openai_reasoning = None
        elif raw_reasoning is not MISSING:
            openai_reasoning = _merge_reasoning_settings(
                default_reasoning,
                _parse_reasoning_settings(raw_reasoning, context=f"{context}.reasoning"),
            )

    if provider == PROVIDER_GOOGLE and isinstance(raw_item, dict):
        raw_thinking = raw_data.get("thinking", MISSING)
        if raw_thinking is False or raw_thinking is None:
            google_thinking = None
        elif raw_thinking is not MISSING:
            google_thinking = _merge_thinking_settings(
                default_thinking,
                _parse_thinking_settings(raw_thinking, context=f"{context}.thinking"),
            )

    return ProviderModelConfig(
        name=model_name,
        label=label,
        openai_reasoning=openai_reasoning if provider == PROVIDER_OPENAI else None,
        google_thinking=google_thinking if provider == PROVIDER_GOOGLE else None,
    )



def _parse_provider_catalog(provider: str, raw_provider: Any) -> ProviderModelCatalog:
    provider_data = _ensure_json_object(raw_provider, context=provider)
    image_model = _parse_optional_text(provider_data.get("image_model"), context=f"{provider}.image_model")
    defaults = _ensure_json_object(provider_data.get("defaults"), context=f"{provider}.defaults")

    default_reasoning: OpenAIReasoningSettings | None = None
    default_thinking: GoogleThinkingSettings | None = None
    if provider == PROVIDER_OPENAI and "reasoning" in defaults:
        default_reasoning = _parse_reasoning_settings(
            defaults.get("reasoning"),
            context=f"{provider}.defaults.reasoning",
        )
    if provider == PROVIDER_GOOGLE and "thinking" in defaults:
        default_thinking = _parse_thinking_settings(
            defaults.get("thinking"),
            context=f"{provider}.defaults.thinking",
        )

    raw_models = provider_data.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError(f"{provider}.models 必须是数组")

    models = tuple(
        _parse_provider_model(
            provider,
            item,
            index=index,
            default_reasoning=default_reasoning,
            default_thinking=default_thinking,
        )
        for index, item in enumerate(raw_models, start=1)
    )
    return ProviderModelCatalog(image_model=image_model, models=models)



def parse_model_catalog_text(raw_text: str) -> ModelCatalog:
    try:
        raw_data = jsonc_loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型配置解析失败: 第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError("模型配置必须是 JSON 对象")

    return ModelCatalog(
        openai=_parse_provider_catalog(PROVIDER_OPENAI, raw_data.get(PROVIDER_OPENAI)),
        google=_parse_provider_catalog(PROVIDER_GOOGLE, raw_data.get(PROVIDER_GOOGLE)),
    )



def load_model_catalog(model_config_file: Path) -> ModelCatalog:
    path = Path(model_config_file).expanduser()
    if not path.exists():
        raise ValueError(
            f"模型配置文件不存在: {path}。请创建 `config/models.jsonc`，并按新的 JSONC 格式配置模型。"
        )
    return parse_model_catalog_text(path.read_text(encoding="utf-8"))



def load_config() -> AppConfig:
    env_dir = resolve_env_dir()
    env_files = build_grouped_env_files(env_dir)
    load_env_files(env_files)

    users_file = Path(os.getenv("USERS_FILE", str(DEFAULT_USERS_FILE)))
    users = load_users(users_file)
    model_config_file = Path(os.getenv("MODEL_CONFIG_FILE", str(DEFAULT_MODEL_CONFIG_FILE))).expanduser()
    model_catalog = load_model_catalog(model_config_file)

    image_tool_provider = parse_image_tool_provider(os.getenv("IMAGE_TOOL_PROVIDER", PROVIDER_OPENAI))

    openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_models = [item.name for item in model_catalog.openai.models]
    openai_image_model = model_catalog.openai.image_model

    google_base_url = os.getenv("GOOGLE_BASE_URL", "").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    google_models = [item.name for item in model_catalog.google.models]
    google_image_model = model_catalog.google.image_model

    db_file = Path(os.getenv("CHAT_DB_FILE", str(DEFAULT_DB_FILE)))
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))
    max_upload_mb = safe_int(os.getenv("MAX_UPLOAD_MB", "15")) or 15
    max_upload_bytes = max_upload_mb * 1024 * 1024
    max_attachments_per_message = safe_int(os.getenv("MAX_ATTACHMENTS_PER_MESSAGE", "5")) or 5
    max_text_file_chars = safe_int(os.getenv("MAX_TEXT_FILE_CHARS", "12000")) or 12000
    allowed_attachment_exts = parse_allowed_attachment_exts(os.getenv("ALLOWED_ATTACHMENT_EXTS", ""))
    model_options = build_model_options(model_catalog.openai.models, model_catalog.google.models)
    models = [item.id for item in model_options]
    log_level = os.getenv("LOG_LEVEL", "DEBUG").strip().upper() or "DEBUG"
    log_file_raw = os.getenv("LOG_FILE", "").strip()
    log_file = Path(log_file_raw) if log_file_raw else DEFAULT_LOG_FILE
    log_max_bytes = safe_int(os.getenv("LOG_MAX_BYTES", "10485760")) or 10485760
    log_backup_count = safe_int(os.getenv("LOG_BACKUP_COUNT", "5")) or 5
    log_to_stdout = parse_bool(os.getenv("LOG_TO_STDOUT", "1"), default=True)

    use_openai = bool(openai_models or openai_image_model)
    use_google = bool(google_models or google_image_model)

    if use_openai and not openai_base_url:
        raise ValueError("OPENAI_BASE_URL is required when OpenAI is configured.")
    if use_openai and not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when OpenAI is configured.")
    if use_google and not google_api_key:
        raise ValueError("GOOGLE_API_KEY is required when Google is configured.")

    return AppConfig(
        secret_key=os.getenv("APP_SECRET_KEY", "dev-secret-change-me"),
        env_files=env_files,
        env_dir=env_dir,
        users_file=users_file,
        users=users,
        model_config_file=model_config_file,
        image_tool_provider=image_tool_provider,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        openai_models=openai_models,
        openai_image_model=openai_image_model,
        google_base_url=google_base_url,
        google_api_key=google_api_key,
        google_models=google_models,
        google_image_model=google_image_model,
        db_file=db_file,
        upload_dir=upload_dir,
        max_upload_mb=max_upload_mb,
        max_upload_bytes=max_upload_bytes,
        max_attachments_per_message=max_attachments_per_message,
        max_text_file_chars=max_text_file_chars,
        allowed_attachment_exts=allowed_attachment_exts,
        models=models,
        model_options=model_options,
        log_level=log_level,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        log_to_stdout=log_to_stdout,
    )
