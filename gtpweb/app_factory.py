from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from flask import Flask
from openai import OpenAI

from .blueprints import register_blueprints
from .config import BASE_DIR, load_config
from .db import init_db
from .logging_config import configure_logging, register_request_logging
from .runtime_state import create_runtime_state

logger = logging.getLogger(__name__)



def build_openai_client(**kwargs: Any) -> OpenAI:
    return OpenAI(**kwargs)



def build_google_client(*, api_key: str, base_url: str = "") -> Any:
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



def create_app() -> Flask:
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

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
    )
    app.secret_key = config.secret_key
    app.permanent_session_lifetime = timedelta(hours=12)
    app.config["ENV_DIR"] = str(config.env_dir)
    app.config["ENV_FILES"] = [str(path) for path in config.env_files]
    app.config["USERS_FILE"] = str(config.users_file)
    app.config["MODEL_CONFIG_FILE"] = str(config.model_config_file)

    init_db(config.db_file)
    logger.info("应用启动: 数据库初始化完成 数据库=%s", config.db_file)
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("应用启动: 上传目录已就绪 路径=%s", config.upload_dir)

    openai_client_factory = build_openai_client
    google_client_factory = build_google_client
    app.extensions["openai_client_factory"] = openai_client_factory
    app.extensions["google_client_factory"] = google_client_factory
    app.extensions["runtime_base_config"] = config
    app.extensions["runtime_state"] = create_runtime_state(
        config,
        openai_client_factory,
        google_client_factory,
    )
    logger.info(
        "应用启动: 运行时配置初始化完成 OpenAI模型=%s Google模型=%s",
        ",".join(app.extensions["runtime_state"].settings.openai_models),
        ",".join(app.extensions["runtime_state"].settings.google_models),
    )

    register_request_logging(app)
    register_blueprints(app, config)
    logger.info("应用启动完成: 已注册蓝图=%s", ",".join(sorted(app.blueprints.keys())))
    return app
