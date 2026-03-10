from __future__ import annotations

from flask import Flask

from gtpweb.blueprints.admin import create_admin_blueprint
from gtpweb.blueprints.auth import create_auth_blueprint
from gtpweb.blueprints.chat import create_chat_blueprint
from gtpweb.blueprints.conversation import create_conversation_blueprint
from gtpweb.config import AppConfig


def register_blueprints(app: Flask, config: AppConfig) -> None:
    app.register_blueprint(create_auth_blueprint(config))
    app.register_blueprint(create_admin_blueprint(config))
    app.register_blueprint(create_conversation_blueprint(config))
    app.register_blueprint(create_chat_blueprint(config))
