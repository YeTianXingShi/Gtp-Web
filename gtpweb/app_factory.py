"""
Flask 应用工厂模块

本模块负责创建和配置 Flask 应用实例，采用应用工厂模式以支持测试和灵活部署。

主要功能：
- 创建 OpenAI 和 Google AI 客户端
- 初始化 Flask 应用
- 配置数据库、会话、日志
- 注册蓝图和扩展
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask
from flask_cors import CORS
from openai import OpenAI

from .blueprints import register_blueprints
from .config import BASE_DIR, load_config
from .db import init_db
from .logging_config import configure_logging, register_request_logging
from .runtime_state import create_runtime_state

logger = logging.getLogger(__name__)


def build_openai_client(**kwargs: Any) -> OpenAI:
    """
    创建 OpenAI 客户端实例

    Args:
        **kwargs: 传递给 OpenAI 构造函数的参数（如 api_key, base_url 等）

    Returns:
        OpenAI: 配置好的 OpenAI 客户端实例
    """
    kwargs.setdefault("max_retries", 0)
    return OpenAI(**kwargs)


def build_google_client(*, api_key: str, base_url: str = "") -> Any:
    """
    创建 Google AI 客户端实例

    Args:
        api_key: Google API 密钥
        base_url: 自定义 API 基础 URL（可选）

    Returns:
        genai.Client: 配置好的 Google AI 客户端实例

    Raises:
        RuntimeError: 当缺少 google-genai 依赖时抛出
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "当前环境缺少 `google-genai` 依赖，请先执行 `pip install -r requirements.txt`。"
        ) from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["http_options"] = types.HttpOptions(base_url=base_url)
    return genai.Client(**client_kwargs)


def build_claude_client(*, api_key: str, base_url: str = "") -> Any:
    """
    创建 Anthropic Claude 客户端实例

    Args:
        api_key: Anthropic API 密钥
        base_url: 自定义 API 基础 URL（可选）

    Returns:
        anthropic.Anthropic: 配置好的 Claude 客户端实例

    Raises:
        RuntimeError: 当缺少 anthropic 依赖时抛出
    """
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "当前环境缺少 `anthropic` 依赖，请先执行 `pip install -r requirements.txt`。"
        ) from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
    if base_url:
        client_kwargs["base_url"] = base_url
    return anthropic.Anthropic(**client_kwargs)


def create_app() -> Flask:
    """
    创建并配置 Flask 应用实例

    该函数执行完整的初始化流程：
    1. 加载配置
    2. 配置日志
    3. 创建 Flask 应用
    4. 初始化数据库
    5. 创建运行时状态
    6. 注册蓝图

    Returns:
        Flask: 完全配置好的 Flask 应用实例
    """
    # 加载配置
    config = load_config()
    configure_logging(config)

    logger.info(
        "应用启动: 配置已加载 用户配置=%s 数据库=%s 上传目录=%s 模型=%s 日志级别=%s",
        config.users_file,
        config.db_file,
        config.upload_dir,
        ",".join(config.models),
        config.log_level,
    )

    # 创建 Flask 应用
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
    )

    # 配置应用密钥（保留为 Flask itsdangerous 默认签名等用途）
    app.secret_key = config.secret_key
    app.config["JWT_SECRET"] = config.jwt_secret

    # 开发期允许 Vite dev server 跨域；生产同源部署时 ALLOWED_ORIGINS 留空即不放行
    dev_origin = os.getenv("FRONTEND_DEV_ORIGIN", "http://localhost:5173").strip()
    debug_mode = os.getenv("FLASK_DEBUG", "0").strip() in {"1", "true", "True"}
    allowed_origins = [dev_origin] if debug_mode and dev_origin else []
    if allowed_origins:
        CORS(
            app,
            resources={r"/api/*": {"origins": allowed_origins}},
            supports_credentials=True,
            expose_headers=["X-Accel-Buffering"],
            max_age=600,
        )
        logger.info("CORS 已启用: 允许来源=%s", allowed_origins)

    # 保存配置路径到应用配置
    app.config["ENV_DIR"] = str(config.env_dir)
    app.config["ENV_FILES"] = [str(path) for path in config.env_files]
    app.config["USERS_FILE"] = str(config.users_file)
    app.config["MODEL_CONFIG_FILE"] = str(config.model_config_file)

    # 初始化数据库
    init_db(config.db_file)
    logger.info("应用启动: 数据库初始化完成 数据库=%s", config.db_file)

    # 创建上传目录
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("应用启动: 上传目录已就绪 路径=%s", config.upload_dir)

    # 配置 AI 客户端工厂函数
    openai_client_factory = build_openai_client
    google_client_factory = build_google_client
    claude_client_factory = build_claude_client

    # 注册到 Flask 扩展
    app.extensions["openai_client_factory"] = openai_client_factory
    app.extensions["google_client_factory"] = google_client_factory
    app.extensions["claude_client_factory"] = claude_client_factory
    app.extensions["runtime_base_config"] = config

    # 创建运行时状态管理器
    app.extensions["runtime_state"] = create_runtime_state(
        config,
        openai_client_factory,
        google_client_factory,
        claude_client_factory,
    )

    logger.info(
        "应用启动: 运行时配置初始化完成 OpenAI模型=%s Google模型=%s Claude模型=%s",
        ",".join(app.extensions["runtime_state"].settings.openai_models),
        ",".join(app.extensions["runtime_state"].settings.google_models),
        ",".join(app.extensions["runtime_state"].settings.claude_models),
    )

    # 注册请求日志记录和蓝图
    register_request_logging(app)
    register_blueprints(app, config)
    logger.info("应用启动完成: 已注册蓝图=%s", ",".join(sorted(app.blueprints.keys())))

    return app
