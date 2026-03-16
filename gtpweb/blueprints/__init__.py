"""
蓝图注册模块

负责注册所有 Flask 蓝图到应用。
"""

from __future__ import annotations

from flask import Flask

from gtpweb.blueprints.admin import create_admin_blueprint
from gtpweb.blueprints.auth import create_auth_blueprint
from gtpweb.blueprints.chat import create_chat_blueprint
from gtpweb.blueprints.conversation import create_conversation_blueprint
from gtpweb.blueprints.pdf_workbench import create_pdf_workbench_blueprint
from gtpweb.config import AppConfig


def register_blueprints(app: Flask, config: AppConfig) -> None:
    """
    注册所有蓝图到 Flask 应用

    Args:
        app: Flask 应用实例
        config: 应用配置

    Returns:
        无
    """
    app.register_blueprint(create_auth_blueprint(config))
    app.register_blueprint(create_admin_blueprint(config))
    app.register_blueprint(create_conversation_blueprint(config))
    app.register_blueprint(create_pdf_workbench_blueprint(config))
    app.register_blueprint(create_chat_blueprint(config))
