from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from gtpweb.config import AppConfig

logger = logging.getLogger(__name__)


def _get_current_user() -> str | None:
    username = session.get("username")
    return username if isinstance(username, str) and username else None


def create_auth_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("auth", __name__)

    users = config.users

    @bp.get("/")
    def index() -> Any:
        if not _get_current_user():
            return redirect(url_for("auth.login_page"))
        return redirect(url_for("auth.chat_page"))

    @bp.get("/login")
    def login_page() -> str:
        if _get_current_user():
            return redirect(url_for("auth.chat_page"))
        return render_template("login.html")

    @bp.post("/api/login")
    def login() -> Any:
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        logger.info("登录尝试: 用户名=%s", username or "<empty>")

        if not username or not password:
            logger.warning("登录失败: 参数缺失 用户名=%s", username or "<empty>")
            return jsonify({"ok": False, "error": "账号和密码不能为空"}), 400

        expected_password = users.get(username)
        if expected_password is None or expected_password != password:
            logger.warning("登录失败: 账号或密码错误 用户名=%s", username)
            return jsonify({"ok": False, "error": "账号或密码错误"}), 401

        session.permanent = True
        session["username"] = username
        logger.info("登录成功: 用户名=%s", username)
        return jsonify({"ok": True})

    @bp.post("/api/logout")
    def logout() -> Any:
        username = _get_current_user() or "<anonymous>"
        logger.info("退出登录: 用户名=%s", username)
        session.clear()
        return jsonify({"ok": True})

    @bp.get("/chat")
    def chat_page() -> Any:
        username = _get_current_user()
        if not username:
            return redirect(url_for("auth.login_page"))
        return render_template(
            "chat.html",
            username=username,
            models=config.models,
            max_attachments_per_message=config.max_attachments_per_message,
            max_upload_mb=config.max_upload_mb,
            allowed_attachment_exts=sorted(config.allowed_attachment_exts),
        )

    return bp
