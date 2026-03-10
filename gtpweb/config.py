from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .attachments import parse_allowed_attachment_exts
from .user_store import load_user_password_map
from .utils import safe_int

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = BASE_DIR / ".env"
DEFAULT_USERS_FILE = BASE_DIR / "config" / "users.json"
DEFAULT_DB_FILE = BASE_DIR / "data" / "chat.db"
DEFAULT_UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_LOG_FILE = BASE_DIR / "logs" / "app.log"
load_dotenv(DEFAULT_ENV_FILE)


@dataclass(frozen=True)
class AppConfig:
    secret_key: str
    env_file: Path
    users_file: Path
    users: dict[str, str]
    ai_base_url: str
    ai_api_key: str
    db_file: Path
    upload_dir: Path
    max_upload_mb: int
    max_upload_bytes: int
    max_attachments_per_message: int
    max_text_file_chars: int
    allowed_attachment_exts: set[str]
    models: list[str]
    log_level: str
    log_file: Path
    log_max_bytes: int
    log_backup_count: int
    log_to_stdout: bool


def load_users(users_file: Path) -> dict[str, str]:
    return load_user_password_map(users_file)


def parse_models(raw_models: str) -> list[str]:
    models = [item.strip() for item in raw_models.split(",") if item.strip()]
    if not models:
        raise ValueError("AI_MODELS must contain at least one model.")
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


def load_config() -> AppConfig:
    env_file = Path(os.getenv("ENV_FILE", str(DEFAULT_ENV_FILE)))
    load_dotenv(env_file, override=False)

    users_file = Path(os.getenv("USERS_FILE", str(DEFAULT_USERS_FILE)))
    users = load_users(users_file)

    ai_base_url = os.getenv("AI_BASE_URL", "").strip()
    ai_api_key = os.getenv("AI_API_KEY", "")
    db_file = Path(os.getenv("CHAT_DB_FILE", str(DEFAULT_DB_FILE)))
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))
    max_upload_mb = safe_int(os.getenv("MAX_UPLOAD_MB", "15")) or 15
    max_upload_bytes = max_upload_mb * 1024 * 1024
    max_attachments_per_message = safe_int(os.getenv("MAX_ATTACHMENTS_PER_MESSAGE", "5")) or 5
    max_text_file_chars = safe_int(os.getenv("MAX_TEXT_FILE_CHARS", "12000")) or 12000
    allowed_attachment_exts = parse_allowed_attachment_exts(os.getenv("ALLOWED_ATTACHMENT_EXTS", ""))
    models = parse_models(os.getenv("AI_MODELS", "gpt-4o-mini,gpt-4.1-mini"))
    log_level = os.getenv("LOG_LEVEL", "DEBUG").strip().upper() or "DEBUG"
    log_file_raw = os.getenv("LOG_FILE", "").strip()
    log_file = Path(log_file_raw) if log_file_raw else DEFAULT_LOG_FILE
    log_max_bytes = safe_int(os.getenv("LOG_MAX_BYTES", "10485760")) or 10485760
    log_backup_count = safe_int(os.getenv("LOG_BACKUP_COUNT", "5")) or 5
    log_to_stdout = parse_bool(os.getenv("LOG_TO_STDOUT", "1"), default=True)

    if not ai_base_url:
        raise ValueError("AI_BASE_URL is required.")
    if not ai_api_key:
        raise ValueError("AI_API_KEY is required.")

    return AppConfig(
        secret_key=os.getenv("APP_SECRET_KEY", "dev-secret-change-me"),
        env_file=env_file,
        users_file=users_file,
        users=users,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
        db_file=db_file,
        upload_dir=upload_dir,
        max_upload_mb=max_upload_mb,
        max_upload_bytes=max_upload_bytes,
        max_attachments_per_message=max_attachments_per_message,
        max_text_file_chars=max_text_file_chars,
        allowed_attachment_exts=allowed_attachment_exts,
        models=models,
        log_level=log_level,
        log_file=log_file,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        log_to_stdout=log_to_stdout,
    )
