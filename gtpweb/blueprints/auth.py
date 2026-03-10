from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from gtpweb.config import AppConfig
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record, verify_user_credentials

logger = logging.getLogger(__name__)


def _get_current_user_record(users_file: Path) -> dict[str, Any] | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None

    record = get_user_record(users_file, username)
    if record is None:
        logger.warning("会话用户不存在，已清理登录态: 用户名=%s", username)
        session.clear()
        return None
    return record


def _get_current_user(users_file: Path) -> str | None:
    record = _get_current_user_record(users_file)
    if record is None:
        return None
    return str(record["username"])


def create_auth_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("auth", __name__)

    users_file = config.users_file

    @bp.get("/")
    def index() -> Any:
        record = _get_current_user_record(users_file)
        if record is None:
            return redirect(url_for("auth.login_page"))
        if record["is_admin"]:
            return redirect(url_for("admin.admin_page"))
        return redirect(url_for("auth.chat_page"))

    @bp.get("/login")
    def login_page() -> str:
        record = _get_current_user_record(users_file)
        if record is not None:
            if record["is_admin"]:
                return redirect(url_for("admin.admin_page"))
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

        user_record = verify_user_credentials(users_file, username, password)
        if user_record is None:
            logger.warning("登录失败: 账号或密码错误 用户名=%s", username)
            return jsonify({"ok": False, "error": "账号或密码错误"}), 401

        session.permanent = True
        session["username"] = user_record["username"]
        logger.info("登录成功: 用户名=%s 管理员=%s", username, user_record["is_admin"])
        return jsonify(
            {
                "ok": True,
                "is_admin": bool(user_record["is_admin"]),
                "redirect_to": "/admin" if user_record["is_admin"] else "/chat",
            }
        )

    @bp.post("/api/logout")
    def logout() -> Any:
        username = _get_current_user(users_file) or "<anonymous>"
        logger.info("退出登录: 用户名=%s", username)
        session.clear()
        return jsonify({"ok": True})

    @bp.get("/chat")
    def chat_page() -> Any:
        record = _get_current_user_record(users_file)
        if record is None:
            return redirect(url_for("auth.login_page"))

        runtime_settings = get_runtime_state().settings
        return render_template(
            "chat.html",
            username=record["username"],
            is_admin=bool(record["is_admin"]),
            models=runtime_settings.models,
            max_attachments_per_message=runtime_settings.max_attachments_per_message,
            max_upload_mb=runtime_settings.max_upload_mb,
            allowed_attachment_exts=sorted(runtime_settings.allowed_attachment_exts),
        )

    return bp
