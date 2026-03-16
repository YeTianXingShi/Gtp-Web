"""
配置管理模块

本模块负责加载和解析应用的所有配置，包括：
- 环境变量（从 .env 文件加载）
- 模型配置（从 JSONC 文件）
- 用户配置（从 JSON 文件）
- 应用运行时参数

配置来源优先级：环境变量 > 配置文件 > 默认值
"""

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

# 基础目录（项目根目录）
BASE_DIR = Path(__file__).resolve().parent.parent

# 默认配置路径
DEFAULT_ENV_DIR = BASE_DIR / "config" / "env"
DEFAULT_USERS_FILE = BASE_DIR / "config" / "users.json"
DEFAULT_MODEL_CONFIG_FILE = BASE_DIR / "config" / "models.jsonc"
DEFAULT_DB_FILE = BASE_DIR / "data" / "chat.db"
DEFAULT_UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_LOG_FILE = BASE_DIR / "logs" / "app.log"


@dataclass(frozen=True)
class EnvGroupSpec:
    """
    环境配置组规范

    用于定义每个环境配置文件的元数据，帮助生成配置文档。

    Attributes:
        key: 配置组标识符
        filename: 环境文件名
        label: 配置组显示名称
        description: 配置组说明
    """
    key: str
    filename: str
    label: str
    description: str


# 环境配置组定义
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
        label="存储配置",
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
    """
    单个 AI 提供商的模型目录

    Attributes:
        image_model: 用于图像生成的模型名称
        models: 模型配置列表
    """
    image_model: str
    models: tuple[ProviderModelConfig, ...]


@dataclass(frozen=True)
class ModelCatalog:
    """
    所有 AI 提供商的模型目录

    Attributes:
        openai: OpenAI 模型目录
        google: Google Gemini 模型目录
    """
    openai: ProviderModelCatalog
    google: ProviderModelCatalog


@dataclass(frozen=True)
class AppConfig:
    """
    应用配置类

    包含应用运行所需的所有配置参数。

    Attributes:
        secret_key: Flask 会话密钥
        env_files: 环境配置文件列表
        env_dir: 环境配置目录
        users_file: 用户配置文件路径
        users: 用户名到密码哈希的映射
        model_config_file: 模型配置文件路径
        image_tool_provider: 图像工具提供商 (openai/google)
        magic_login_secret: 免登录链接签名密钥
        magic_login_default_max_age: 免登录链接默认有效期（秒）
        openai_base_url: OpenAI API 基础 URL
        openai_api_key: OpenAI API 密钥
        openai_models: OpenAI 模型列表
        openai_image_model: OpenAI 图像生成模型
        google_base_url: Google API 基础 URL
        google_api_key: Google API 密钥
        google_models: Google 模型列表
        google_image_model: Google 图像生成模型
        db_file: 数据库文件路径
        upload_dir: 上传文件目录
        max_upload_mb: 最大上传文件大小（MB）
        max_upload_bytes: 最大上传文件大小（字节）
        max_pdf_upload_mb: PDF 工作台最大上传大小（MB）
        max_pdf_upload_bytes: PDF 工作台最大上传大小（字节）
        max_attachments_per_message: 每条消息最大附件数
        max_text_file_chars: 文本文件最大字符数
        allowed_attachment_exts: 允许的附件扩展名集合
        models: 所有可用模型 ID 列表
        model_options: 模型选项详情列表
        log_level: 日志级别
        log_file: 日志文件路径
        log_max_bytes: 日志文件最大大小（字节）
        log_backup_count: 日志备份文件数量
        log_to_stdout: 是否输出到标准输出
    """
    secret_key: str
    env_files: tuple[Path, ...]
    env_dir: Path
    users_file: Path
    users: dict[str, str]
    model_config_file: Path
    image_tool_provider: str
    magic_login_secret: str
    magic_login_default_max_age: int
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
    max_pdf_upload_mb: int
    max_pdf_upload_bytes: int
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


# 用于标识缺失值的标记对象
MISSING = object()


def _resolve_project_path(path_value: str | Path) -> Path:
    """
    将配置中的路径解析为项目根目录下的绝对路径。

    规则：
    - `~` 路径先展开
    - 绝对路径直接返回
    - 相对路径统一相对于项目根目录解析
    """
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return BASE_DIR / path


def load_users(users_file: Path) -> dict[str, str]:
    """
    加载用户配置

    Args:
        users_file: 用户配置文件路径

    Returns:
        用户名到密码哈希的映射字典
    """
    return load_user_password_map(users_file)


def parse_bool(raw_value: str, default: bool) -> bool:
    """
    解析布尔值字符串

    Args:
        raw_value: 待解析的字符串
        default: 默认值（当字符串为空时返回）

    Returns:
        解析后的布尔值

    Examples:
        >>> parse_bool("true", False) -> True
        >>> parse_bool("0", True) -> False
        >>> parse_bool("", True) -> True
    """
    value = raw_value.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def parse_image_tool_provider(raw_value: str) -> str:
    """
    解析图像工具提供商

    Args:
        raw_value: 提供商名称字符串

    Returns:
        标准化的提供商名称 (openai 或 google)

    Raises:
        ValueError: 当提供商名称无效时
    """
    provider = str(raw_value or "").strip().lower() or PROVIDER_OPENAI
    if provider not in {PROVIDER_OPENAI, PROVIDER_GOOGLE}:
        raise ValueError("IMAGE_TOOL_PROVIDER 仅支持 openai 或 google。")
    return provider


def build_grouped_env_files(env_dir: Path) -> tuple[Path, ...]:
    """
    构建环境配置文件路径列表

    Args:
        env_dir: 环境配置目录

    Returns:
        所有环境配置文件的路径元组
    """
    return tuple(env_dir / item.filename for item in ENV_GROUP_SPECS)


def resolve_env_dir() -> Path:
    """
    解析环境配置目录路径

    优先使用环境变量 ENV_DIR，否则使用默认路径。

    Args:
        无

    Returns:
        解析后的环境配置目录路径

    Raises:
        ValueError: 当路径存在但不是目录时
    """
    env_dir = Path(os.getenv("ENV_DIR", str(DEFAULT_ENV_DIR))).expanduser()
    if env_dir.exists() and not env_dir.is_dir():
        raise ValueError("ENV_DIR must point to a directory.")
    return env_dir


def load_env_files(env_files: tuple[Path, ...]) -> None:
    """
    加载环境变量文件

    Args:
        env_files: 环境配置文件路径列表

    Returns:
        无
    """
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _ensure_json_object(raw_value: Any, *, context: str) -> dict[str, Any]:
    """
    确保值为 JSON 对象

    Args:
        raw_value: 待检查的值
        context: 错误信息上下文

    Returns:
        解析后的 JSON 对象

    Raises:
        ValueError: 当值不是字典类型时
    """
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是 JSON 对象")
    return raw_value


def _parse_json_bool(raw_value: Any, *, context: str, default: bool) -> bool:
    """
    解析 JSON 中的布尔值

    Args:
        raw_value: 待解析的值
        context: 错误信息上下文
        default: 默认值

    Returns:
        解析后的布尔值

    Raises:
        ValueError: 当值类型无效时
    """
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return parse_bool(raw_value, default)
    raise ValueError(f"{context} 必须是布尔值")


def _parse_optional_text(raw_value: Any, *, context: str, lowercase: bool = False) -> str:
    """
    解析可选文本字段

    Args:
        raw_value: 待解析的值
        context: 错误信息上下文
        lowercase: 是否转换为小写

    Returns:
        解析后的文本（去除首尾空格）

    Raises:
        ValueError: 当值不是字符串时
    """
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raise ValueError(f"{context} 必须是字符串")
    text = raw_value.strip()
    return text.lower() if lowercase else text


def _parse_text_options(raw_value: Any, *, context: str) -> tuple[str, ...]:
    """
    解析文本选项数组

    去重并返回选项元组。

    Args:
        raw_value: 待解析的值
        context: 错误信息上下文

    Returns:
        去重后的选项元组

    Raises:
        ValueError: 当值不是数组或包含空字符串时
    """
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise ValueError(f"{context} 必须是字符串数组")

    seen: set[str] = set()
    options: list[str] = []
    for index, item in enumerate(raw_value, start=1):
        value = _parse_optional_text(item, context=f"{context}[{index}]", lowercase=True)
        if not value:
            raise ValueError(f"{context}[{index}] 不能为空")
        if value in seen:
            continue
        seen.add(value)
        options.append(value)
    return tuple(options)


def _parse_reasoning_settings(
    raw_value: Any,
    *,
    context: str,
    base_settings: OpenAIReasoningSettings | None = None,
) -> OpenAIReasoningSettings:
    """
    解析 OpenAI 推理设置

    Args:
        raw_value: 待解析的值（可以是 true/false/对象/null）
        context: 错误信息上下文
        base_settings: 基础设置（用于继承默认值）

    Returns:
        解析后的推理设置

    Raises:
        ValueError: 当配置格式无效时
    """
    # 从基础设置获取默认值
    default_effort = "" if base_settings is None else base_settings.effort
    default_summary = "" if base_settings is None else base_settings.summary
    default_effort_options = () if base_settings is None else base_settings.effort_options

    # 处理禁用或简化配置
    if raw_value is None or raw_value is False:
        return OpenAIReasoningSettings(
            enabled=False,
            effort=default_effort,
            summary=default_summary,
            effort_options=default_effort_options,
        )
    if raw_value is True:
        raw_value = {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是对象、true/false 或 null")

    # 解析 effort 参数
    effort = default_effort
    if "effort" in raw_value:
        effort = _parse_optional_text(raw_value.get("effort"), context=f"{context}.effort", lowercase=True)

    # 解析 effort_options 参数
    effort_options = default_effort_options
    if "effort_options" in raw_value:
        effort_options = _parse_text_options(raw_value.get("effort_options"), context=f"{context}.effort_options")

    # 解析 summary 参数
    summary = default_summary
    if "summary" in raw_value:
        summary = _parse_optional_text(raw_value.get("summary"), context=f"{context}.summary", lowercase=True)

    # 自动设置默认 effort
    if not effort and effort_options:
        effort = effort_options[0]

    # 验证 effort 是否在选项列表中
    if effort and effort_options and effort not in effort_options:
        raise ValueError(f"{context}.effort 必须在 effort_options 中")

    return OpenAIReasoningSettings(
        enabled=_parse_json_bool(raw_value.get("enabled"), context=f"{context}.enabled", default=True),
        effort=effort,
        summary=summary,
        effort_options=effort_options,
    )


def _parse_thinking_settings(
    raw_value: Any,
    *,
    context: str,
    base_settings: GoogleThinkingSettings | None = None,
) -> GoogleThinkingSettings:
    """
    解析 Google Thinking 设置

    Args:
        raw_value: 待解析的值（可以是 true/false/对象/null）
        context: 错误信息上下文
        base_settings: 基础设置（用于继承默认值）

    Returns:
        解析后的 Thinking 设置

    Raises:
        ValueError: 当配置格式无效时
    """
    # 从基础设置获取默认值
    default_include_thoughts = True if base_settings is None else base_settings.include_thoughts
    default_level = "" if base_settings is None else base_settings.level
    default_level_options = () if base_settings is None else base_settings.level_options

    # 处理禁用或简化配置
    if raw_value is None or raw_value is False:
        return GoogleThinkingSettings(
            enabled=False,
            include_thoughts=default_include_thoughts,
            level=default_level,
            level_options=default_level_options,
        )
    if raw_value is True:
        raw_value = {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{context} 必须是对象、true/false 或 null")

    # 解析 level 参数
    level = default_level
    if "level" in raw_value:
        level = _parse_optional_text(raw_value.get("level"), context=f"{context}.level", lowercase=True)

    # 解析 level_options 参数
    level_options = default_level_options
    if "level_options" in raw_value:
        level_options = _parse_text_options(raw_value.get("level_options"), context=f"{context}.level_options")

    # 自动设置默认 level
    if not level and level_options:
        level = level_options[0]

    # 验证 level 是否在选项列表中
    if level and level_options and level not in level_options:
        raise ValueError(f"{context}.level 必须在 level_options 中")

    return GoogleThinkingSettings(
        enabled=_parse_json_bool(raw_value.get("enabled"), context=f"{context}.enabled", default=True),
        include_thoughts=_parse_json_bool(
            raw_value.get("include_thoughts"),
            context=f"{context}.include_thoughts",
            default=default_include_thoughts,
        ),
        level=level,
        level_options=level_options,
    )


def _parse_provider_model(
    provider: str,
    raw_item: Any,
    *,
    index: int,
    default_reasoning: OpenAIReasoningSettings | None,
    default_thinking: GoogleThinkingSettings | None,
) -> ProviderModelConfig:
    """
    解析单个提供商的模型配置

    Args:
        provider: 提供商名称 (openai/google)
        raw_item: 原始配置（可以是字符串或对象）
        index: 模型在列表中的索引
        default_reasoning: 默认 OpenAI 推理设置
        default_thinking: 默认 Google Thinking 设置

    Returns:
        解析后的模型配置

    Raises:
        ValueError: 当配置格式无效时
    """
    context = f"{provider}.models[{index}]"

    # 支持简写字符串配置和详细对象配置
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

    # 解析标签（默认使用模型名）
    label = model_name
    if isinstance(raw_item, dict):
        label = _parse_optional_text(raw_data.get("label"), context=f"{context}.label") or model_name

    # 初始化推理/Thinking 设置
    openai_reasoning = default_reasoning
    google_thinking = default_thinking

    # 解析 OpenAI 特定的 reasoning 设置
    if provider == PROVIDER_OPENAI and isinstance(raw_item, dict):
        raw_reasoning = raw_data.get("reasoning", MISSING)
        if raw_reasoning is not MISSING:
            openai_reasoning = _parse_reasoning_settings(
                raw_reasoning,
                context=f"{context}.reasoning",
                base_settings=default_reasoning,
            )

    # 解析 Google 特定的 thinking 设置
    if provider == PROVIDER_GOOGLE and isinstance(raw_item, dict):
        raw_thinking = raw_data.get("thinking", MISSING)
        if raw_thinking is not MISSING:
            google_thinking = _parse_thinking_settings(
                raw_thinking,
                context=f"{context}.thinking",
                base_settings=default_thinking,
            )

    return ProviderModelConfig(
        name=model_name,
        label=label,
        openai_reasoning=openai_reasoning if provider == PROVIDER_OPENAI else None,
        google_thinking=google_thinking if provider == PROVIDER_GOOGLE else None,
    )


def _parse_provider_catalog(provider: str, raw_provider: Any) -> ProviderModelCatalog:
    """
    解析单个提供商的模型目录

    Args:
        provider: 提供商名称 (openai/google)
        raw_provider: 原始配置对象

    Returns:
        解析后的模型目录

    Raises:
        ValueError: 当配置格式无效时
    """
    provider_data = _ensure_json_object(raw_provider, context=provider)

    # 解析图像模型
    image_model = _parse_optional_text(provider_data.get("image_model"), context=f"{provider}.image_model")
    defaults = _ensure_json_object(provider_data.get("defaults"), context=f"{provider}.defaults")

    # 解析默认推理/Thinking 设置
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

    # 解析模型列表
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
    """
    解析模型目录文本（JSONC 格式）

    Args:
        raw_text: 模型配置文本内容

    Returns:
        解析后的模型目录

    Raises:
        ValueError: 当 JSON 解析失败或格式无效时
    """
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
    """
    从文件加载模型目录

    Args:
        model_config_file: 模型配置文件路径

    Returns:
        解析后的模型目录

    Raises:
        ValueError: 当文件不存在时
    """
    path = Path(model_config_file).expanduser()
    if not path.exists():
        raise ValueError(
            f"模型配置文件不存在: {path}。请创建 `config/models.jsonc`，并按新的 JSONC 格式配置模型。"
        )
    return parse_model_catalog_text(path.read_text(encoding="utf-8"))


def load_config() -> AppConfig:
    """
    加载完整的应用配置

    执行以下步骤：
    1. 解析环境配置目录
    2. 加载所有 .env 文件
    3. 加载用户配置
    4. 加载模型配置
    5. 解析所有环境变量
    6. 验证配置完整性

    Returns:
        完整的应用配置对象

    Raises:
        ValueError: 当配置验证失败时
    """
    # 解析环境目录并加载环境变量
    env_dir = resolve_env_dir()
    env_files = build_grouped_env_files(env_dir)
    load_env_files(env_files)

    # 加载用户配置
    users_file = _resolve_project_path(os.getenv("USERS_FILE", str(DEFAULT_USERS_FILE)))
    users = load_users(users_file)

    # 加载模型配置
    model_config_file = _resolve_project_path(os.getenv("MODEL_CONFIG_FILE", str(DEFAULT_MODEL_CONFIG_FILE)))
    model_catalog = load_model_catalog(model_config_file)

    # 解析图像工具提供商
    image_tool_provider = parse_image_tool_provider(os.getenv("IMAGE_TOOL_PROVIDER", PROVIDER_OPENAI))
    magic_login_secret = os.getenv("MAGIC_LOGIN_SECRET", "").strip() or os.getenv(
        "APP_SECRET_KEY", "dev-secret-change-me"
    )
    magic_login_default_max_age = safe_int(os.getenv("MAGIC_LOGIN_DEFAULT_MAX_AGE", "604800")) or 604800

    # OpenAI 配置
    openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_models = [item.name for item in model_catalog.openai.models]
    openai_image_model = model_catalog.openai.image_model

    # Google 配置
    google_base_url = os.getenv("GOOGLE_BASE_URL", "").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    google_models = [item.name for item in model_catalog.google.models]
    google_image_model = model_catalog.google.image_model

    # 存储配置
    db_file = _resolve_project_path(os.getenv("CHAT_DB_FILE", str(DEFAULT_DB_FILE)))
    upload_dir = _resolve_project_path(os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))

    # 附件限制配置
    max_upload_mb = safe_int(os.getenv("MAX_UPLOAD_MB", "15")) or 15
    max_upload_bytes = max_upload_mb * 1024 * 1024
    max_pdf_upload_mb = safe_int(os.getenv("MAX_PDF_UPLOAD_MB", "100")) or 100
    max_pdf_upload_bytes = max_pdf_upload_mb * 1024 * 1024
    max_attachments_per_message = safe_int(os.getenv("MAX_ATTACHMENTS_PER_MESSAGE", "5")) or 5
    max_text_file_chars = safe_int(os.getenv("MAX_TEXT_FILE_CHARS", "12000")) or 12000
    allowed_attachment_exts = parse_allowed_attachment_exts(os.getenv("ALLOWED_ATTACHMENT_EXTS", ""))

    # 构建模型选项
    model_options = build_model_options(model_catalog.openai.models, model_catalog.google.models)
    models = [item.id for item in model_options]

    # 日志配置
    log_level = os.getenv("LOG_LEVEL", "DEBUG").strip().upper() or "DEBUG"
    log_file_raw = os.getenv("LOG_FILE", "").strip()
    log_file = _resolve_project_path(log_file_raw) if log_file_raw else DEFAULT_LOG_FILE
    log_max_bytes = safe_int(os.getenv("LOG_MAX_BYTES", "10485760")) or 10485760
    log_backup_count = safe_int(os.getenv("LOG_BACKUP_COUNT", "5")) or 5
    log_to_stdout = parse_bool(os.getenv("LOG_TO_STDOUT", "1"), default=True)

    # 验证 AI 提供商配置
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
        magic_login_secret=magic_login_secret,
        magic_login_default_max_age=magic_login_default_max_age,
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
        max_pdf_upload_mb=max_pdf_upload_mb,
        max_pdf_upload_bytes=max_pdf_upload_bytes,
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
