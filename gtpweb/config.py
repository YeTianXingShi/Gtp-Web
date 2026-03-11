from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .ai_providers import PROVIDER_GOOGLE, PROVIDER_OPENAI, ModelOption, build_model_options
from .attachments import parse_allowed_attachment_exts
from .user_store import load_user_password_map
from .utils import safe_int

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_DIR = BASE_DIR / "config" / "env"
DEFAULT_USERS_FILE = BASE_DIR / "config" / "users.json"
DEFAULT_DB_FILE = BASE_DIR / "data" / "chat.db"
DEFAULT_UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_LOG_FILE = BASE_DIR / "logs" / "app.log"
DEFAULT_OPENAI_IMAGE_MODEL = "dall-e-3"


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
        label="OpenAI 配置",
        description="维护 OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODELS、OPENAI_IMAGE_MODEL 与推理摘要相关配置。",
    ),
    EnvGroupSpec(
        key="google",
        filename="google.env",
        label="Google Gemini 配置",
        description="维护 GOOGLE_BASE_URL、GOOGLE_API_KEY、GOOGLE_MODELS、GOOGLE_IMAGE_MODEL 与 thinking 配置。",
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
class AppConfig:
    secret_key: str
    env_files: tuple[Path, ...]
    env_dir: Path
    users_file: Path
    users: dict[str, str]
    image_tool_provider: str
    openai_base_url: str
    openai_api_key: str
    openai_models: list[str]
    openai_image_model: str
    openai_reasoning_effort: str
    openai_reasoning_summary: str
    google_base_url: str
    google_api_key: str
    google_models: list[str]
    google_image_model: str
    google_include_thoughts: bool
    google_thinking_level: str
    google_thinking_budget: int | None
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


def load_users(users_file: Path) -> dict[str, str]:
    return load_user_password_map(users_file)



def parse_models(raw_models: str, *, allow_empty: bool = False) -> list[str]:
    models = [item.strip() for item in raw_models.split(",") if item.strip()]
    if not models and not allow_empty:
        raise ValueError("至少需要配置一个模型。")
    return models



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



def load_config() -> AppConfig:
    env_dir = resolve_env_dir()
    env_files = build_grouped_env_files(env_dir)
    load_env_files(env_files)

    users_file = Path(os.getenv("USERS_FILE", str(DEFAULT_USERS_FILE)))
    users = load_users(users_file)

    image_tool_provider = parse_image_tool_provider(os.getenv("IMAGE_TOOL_PROVIDER", PROVIDER_OPENAI))

    openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_models = parse_models(os.getenv("OPENAI_MODELS", ""), allow_empty=True)
    raw_openai_image_model = os.getenv("OPENAI_IMAGE_MODEL")
    if raw_openai_image_model is None:
        openai_image_model = DEFAULT_OPENAI_IMAGE_MODEL if openai_models else ""
    else:
        openai_image_model = raw_openai_image_model.strip()
    openai_reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium").strip().lower()
    openai_reasoning_summary = os.getenv("OPENAI_REASONING_SUMMARY", "auto").strip().lower()

    google_base_url = os.getenv("GOOGLE_BASE_URL", "").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    google_models = parse_models(os.getenv("GOOGLE_MODELS", ""), allow_empty=True)
    google_image_model = os.getenv("GOOGLE_IMAGE_MODEL", "").strip()
    google_include_thoughts = parse_bool(os.getenv("GOOGLE_INCLUDE_THOUGHTS", "1"), default=True)
    google_thinking_level = os.getenv("GOOGLE_THINKING_LEVEL", "medium").strip().lower()
    google_thinking_budget = safe_int(os.getenv("GOOGLE_THINKING_BUDGET", ""))

    db_file = Path(os.getenv("CHAT_DB_FILE", str(DEFAULT_DB_FILE)))
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))
    max_upload_mb = safe_int(os.getenv("MAX_UPLOAD_MB", "15")) or 15
    max_upload_bytes = max_upload_mb * 1024 * 1024
    max_attachments_per_message = safe_int(os.getenv("MAX_ATTACHMENTS_PER_MESSAGE", "5")) or 5
    max_text_file_chars = safe_int(os.getenv("MAX_TEXT_FILE_CHARS", "12000")) or 12000
    allowed_attachment_exts = parse_allowed_attachment_exts(os.getenv("ALLOWED_ATTACHMENT_EXTS", ""))
    model_options = build_model_options(openai_models, google_models)
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
        image_tool_provider=image_tool_provider,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        openai_models=openai_models,
        openai_image_model=openai_image_model,
        openai_reasoning_effort=openai_reasoning_effort,
        openai_reasoning_summary=openai_reasoning_summary,
        google_base_url=google_base_url,
        google_api_key=google_api_key,
        google_models=google_models,
        google_image_model=google_image_model,
        google_include_thoughts=google_include_thoughts,
        google_thinking_level=google_thinking_level,
        google_thinking_budget=google_thinking_budget,
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
