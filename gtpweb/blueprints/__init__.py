"""
蓝图注册模块

负责注册所有 Flask 蓝图到应用。
"""

from __future__ import annotations

from flask import Flask

from gtpweb.blueprints.admin import create_admin_blueprint
from gtpweb.blueprints.auth import create_auth_blueprint
from gtpweb.blueprints.bootstrap import create_bootstrap_blueprint
from gtpweb.blueprints.chat import create_chat_blueprint
from gtpweb.blueprints.conversation import create_conversation_blueprint
from gtpweb.blueprints.documents import create_documents_blueprint
from gtpweb.blueprints.spa import create_spa_blueprint
from gtpweb.config import AppConfig, BASE_DIR


def register_blueprints(app: Flask, config: AppConfig) -> None:
    """
    注册所有蓝图到 Flask 应用

    Args:
        app: Flask 应用实例
        config: 应用配置

    Returns:
        无
    """
    # API 蓝图先注册，确保 /api/* 优先匹配 SPA 兜底
    app.register_blueprint(create_auth_blueprint(config))
    app.register_blueprint(create_bootstrap_blueprint(config))
    app.register_blueprint(create_admin_blueprint(config))
    app.register_blueprint(create_conversation_blueprint(config))
    app.register_blueprint(create_chat_blueprint(config))
    app.register_blueprint(create_documents_blueprint(config))

    # SPA 蓝图最后注册：
    # - 已存在的 dist 目录会服务前端构建产物
    # - dist 不存在时返回 503，引导开发者执行 pnpm build
    dist_dir = BASE_DIR / "static" / "dist"
    app.register_blueprint(create_spa_blueprint(dist_dir))
