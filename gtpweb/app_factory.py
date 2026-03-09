from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask
from openai import OpenAI

from .blueprints import register_blueprints
from .config import BASE_DIR, load_config
from .db import init_db
from .logging_config import configure_logging, register_request_logging

logger = logging.getLogger(__name__)


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

    init_db(config.db_file)
    logger.info("应用启动: 数据库初始化完成 数据库=%s", config.db_file)
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("应用启动: 上传目录已就绪 路径=%s", config.upload_dir)

    openai_client = OpenAI(
        api_key=config.ai_api_key,
        base_url=config.ai_base_url,
    )
    logger.info("应用启动: AI 客户端初始化完成 base_url=%s", config.ai_base_url)

    register_request_logging(app)
    register_blueprints(app, config, openai_client)
    logger.info("应用启动完成: 已注册蓝图=%s", ",".join(sorted(app.blueprints.keys())))
    return app
