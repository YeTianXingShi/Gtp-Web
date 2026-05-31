"""
JWT 鉴权模块

提供 access / refresh 双 Token 的签发、解码、装饰器，以及 refresh token 的
撤销列表（保存在 SQLite `revoked_refresh_jti` 表）。

Token 模型：
- access：放在前端内存，每个 API 请求带 Authorization: Bearer <token>，TTL 15 分钟。
- refresh：HttpOnly + SameSite Cookie，调用 /api/refresh 换新 access，TTL 7 天，可撤销。

Payload 字段：
- access ：{ sub, is_admin, type: "access",  iat, exp, jti }
- refresh：{ sub,             type: "refresh", iat, exp, jti }
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import jwt
from flask import current_app, g, jsonify, request

from gtpweb.db import open_db_connection

logger = logging.getLogger(__name__)

# Token 默认有效期
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)

# Refresh Cookie 名称（前端不可见、仅在 /api/refresh 路径携带）
REFRESH_COOKIE_NAME = "gtp_refresh"
REFRESH_COOKIE_PATH = "/api"

JWT_ALGORITHM = "HS256"


def _secret() -> str:
    """从 Flask 应用配置读取 JWT 签名密钥。"""
    secret = current_app.config.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET 未配置")
    return str(secret)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def issue_tokens(username: str, is_admin: bool) -> tuple[str, str, str, datetime]:
    """
    签发一对 access + refresh token。

    Returns:
        (access_token, refresh_token, refresh_jti, refresh_exp)
        refresh_jti 与 refresh_exp 由调用方写入撤销列表表，便于后续清理。
    """
    now = _utcnow()
    access_jti = secrets.token_urlsafe(16)
    refresh_jti = secrets.token_urlsafe(16)
    refresh_exp = now + REFRESH_TTL

    access = jwt.encode(
        {
            "sub": username,
            "is_admin": bool(is_admin),
            "type": "access",
            "iat": now,
            "exp": now + ACCESS_TTL,
            "jti": access_jti,
        },
        _secret(),
        algorithm=JWT_ALGORITHM,
    )
    refresh = jwt.encode(
        {
            "sub": username,
            "type": "refresh",
            "iat": now,
            "exp": refresh_exp,
            "jti": refresh_jti,
        },
        _secret(),
        algorithm=JWT_ALGORITHM,
    )
    return access, refresh, refresh_jti, refresh_exp


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """
    解码并校验 token；type 不匹配视为无效。

    Raises:
        jwt.PyJWTError: 签名错误、过期、type 不匹配等
    """
    payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    actual_type = payload.get("type")
    if actual_type != expected_type:
        raise jwt.InvalidTokenError(f"token type 不匹配: 期望 {expected_type}，实际 {actual_type}")
    return payload


def require_login(fn: Callable[..., Any]) -> Callable[..., Any]:
    """
    要求请求带有效 access token；解析后写入 `g.user = {username, is_admin}`。
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"ok": False, "error": "请先登录"}), 401

        token = auth_header[len("Bearer "):].strip()
        if not token:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        try:
            payload = decode_token(token, expected_type="access")
        except jwt.ExpiredSignatureError:
            return jsonify({"ok": False, "error": "登录已过期"}), 401
        except jwt.PyJWTError as exc:
            logger.warning("access token 校验失败: %s", exc)
            return jsonify({"ok": False, "error": "令牌无效"}), 401

        username = str(payload.get("sub", "")).strip()
        if not username:
            return jsonify({"ok": False, "error": "令牌无效"}), 401

        g.user = {
            "username": username,
            "is_admin": bool(payload.get("is_admin", False)),
        }
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn: Callable[..., Any]) -> Callable[..., Any]:
    """
    要求 access token 且 is_admin=True。
    """

    @wraps(fn)
    @require_login
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not g.user.get("is_admin"):
            return jsonify({"ok": False, "error": "需要管理员权限"}), 403
        return fn(*args, **kwargs)

    return wrapper


def current_username() -> str:
    """从 g 读取当前用户名。仅可在 require_login/require_admin 之后调用。"""
    user = getattr(g, "user", None)
    if not isinstance(user, dict):
        raise RuntimeError("当前请求未通过 require_login 鉴权")
    return str(user["username"])


# ---- Refresh Token 撤销列表 ----

def revoke_refresh_jti(db_file: Path, jti: str, exp: datetime) -> None:
    """将 refresh token 的 jti 写入撤销列表。"""
    if not jti:
        return
    with open_db_connection(db_file) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO revoked_refresh_jti (jti, revoked_at, exp_at) VALUES (?, ?, ?)",
            (jti, _utcnow().isoformat(), exp.isoformat()),
        )
        conn.commit()


def is_refresh_jti_revoked(db_file: Path, jti: str) -> bool:
    """检查 refresh token 是否已被撤销。"""
    if not jti:
        return True
    with open_db_connection(db_file) as conn:
        row = conn.execute(
            "SELECT 1 FROM revoked_refresh_jti WHERE jti = ?",
            (jti,),
        ).fetchone()
    return row is not None


def cleanup_expired_revocations(db_file: Path) -> int:
    """
    清理 exp_at < now 的撤销记录（已自然过期的 token 即使留在表里也无意义）。

    Returns:
        被清理的行数
    """
    try:
        with open_db_connection(db_file) as conn:
            cursor = conn.execute(
                "DELETE FROM revoked_refresh_jti WHERE exp_at < ?",
                (_utcnow().isoformat(),),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
    except sqlite3.Error:
        logger.exception("清理过期 refresh 撤销记录失败")
        return 0


# ---- Refresh Cookie 工具 ----

def set_refresh_cookie(response: Any, refresh_token: str, *, secure: bool) -> None:
    """
    把 refresh token 写入 HttpOnly Cookie。
    Path 限定 /api 以确保仅在调用 API 时被浏览器携带。
    """
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="Lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Any) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def read_refresh_cookie() -> str:
    return str(request.cookies.get(REFRESH_COOKIE_NAME, "")).strip()
