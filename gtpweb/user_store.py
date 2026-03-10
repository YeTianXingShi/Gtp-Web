from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _normalize_user_record(raw_record: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw_record, dict):
        raise ValueError(f"用户配置格式错误: users[{index}] 必须是对象")

    username = str(raw_record.get("username", "")).strip()
    password = raw_record.get("password", "")
    is_admin = raw_record.get("is_admin", False)

    if not username:
        raise ValueError(f"用户配置格式错误: users[{index}].username 不能为空")
    if not isinstance(password, str) or not password:
        raise ValueError(f"用户配置格式错误: users[{index}].password 不能为空")
    if not isinstance(is_admin, bool):
        raise ValueError(f"用户配置格式错误: users[{index}].is_admin 必须是布尔值")

    return {
        "username": username,
        "password": password,
        "is_admin": is_admin,
    }


def normalize_users_config(raw_data: Any, *, require_admin: bool = False) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw_data, dict):
        raise ValueError("用户配置格式错误: 根节点必须是对象")

    raw_users = raw_data.get("users")
    normalized_users: list[dict[str, Any]] = []

    if isinstance(raw_users, dict):
        for username, password in raw_users.items():
            clean_username = str(username).strip()
            if not clean_username:
                raise ValueError("用户配置格式错误: 用户名不能为空")
            if not isinstance(password, str) or not password:
                raise ValueError(f"用户配置格式错误: 用户 {clean_username} 的密码不能为空")
            normalized_users.append(
                {
                    "username": clean_username,
                    "password": password,
                    "is_admin": False,
                }
            )
    elif isinstance(raw_users, list):
        for index, raw_record in enumerate(raw_users):
            normalized_users.append(_normalize_user_record(raw_record, index))
    else:
        raise ValueError("用户配置格式错误: 'users' 必须是对象或数组")

    if not normalized_users:
        raise ValueError("用户配置格式错误: 至少需要一个用户")

    seen_usernames: set[str] = set()
    for record in normalized_users:
        username = record["username"]
        if username in seen_usernames:
            raise ValueError(f"用户配置格式错误: 用户名重复 {username}")
        seen_usernames.add(username)

    if require_admin and not any(record["is_admin"] for record in normalized_users):
        raise ValueError("用户配置格式错误: 至少需要保留一个管理员账号")

    return {"users": normalized_users}


def load_users_config(users_file: Path, *, require_admin: bool = False) -> dict[str, list[dict[str, Any]]]:
    if not users_file.exists():
        raise FileNotFoundError(
            f"Users config not found: {users_file}. Copy config/users.example.json to config/users.json first."
        )
    raw_data = json.loads(users_file.read_text(encoding="utf-8"))
    return normalize_users_config(raw_data, require_admin=require_admin)


def users_config_to_text(config_data: dict[str, list[dict[str, Any]]]) -> str:
    return json.dumps(config_data, ensure_ascii=False, indent=2) + "\n"


def save_users_config(users_file: Path, config_data: dict[str, Any], *, require_admin: bool = False) -> None:
    normalized = normalize_users_config(config_data, require_admin=require_admin)
    users_file.parent.mkdir(parents=True, exist_ok=True)
    users_file.write_text(users_config_to_text(normalized), encoding="utf-8")


def save_users_config_text(users_file: Path, raw_text: str, *, require_admin: bool = False) -> None:
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: 第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}") from exc
    save_users_config(users_file, raw_data, require_admin=require_admin)


def load_user_password_map(users_file: Path) -> dict[str, str]:
    config_data = load_users_config(users_file)
    return {record["username"]: record["password"] for record in config_data["users"]}


def list_users(users_file: Path) -> list[dict[str, Any]]:
    config_data = load_users_config(users_file)
    return sorted(
        [
            {
                "username": record["username"],
                "is_admin": record["is_admin"],
            }
            for record in config_data["users"]
        ],
        key=lambda item: (not item["is_admin"], item["username"].lower()),
    )


def get_user_record(users_file: Path, username: str) -> dict[str, Any] | None:
    clean_username = str(username).strip()
    if not clean_username:
        return None
    config_data = load_users_config(users_file)
    for record in config_data["users"]:
        if record["username"] == clean_username:
            return dict(record)
    return None


def verify_user_credentials(users_file: Path, username: str, password: str) -> dict[str, Any] | None:
    record = get_user_record(users_file, username)
    if record is None or record["password"] != password:
        return None
    return record


def create_user(users_file: Path, username: str, password: str, is_admin: bool) -> dict[str, Any]:
    clean_username = str(username).strip()
    if not clean_username:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")

    config_data = load_users_config(users_file)
    if any(record["username"] == clean_username for record in config_data["users"]):
        raise ValueError("用户名已存在")

    config_data["users"].append(
        {
            "username": clean_username,
            "password": password,
            "is_admin": bool(is_admin),
        }
    )
    save_users_config(users_file, config_data, require_admin=True)
    return {
        "username": clean_username,
        "is_admin": bool(is_admin),
    }


def update_user(
    users_file: Path,
    username: str,
    *,
    password: str | None = None,
    is_admin: bool | None = None,
    current_username: str | None = None,
) -> dict[str, Any]:
    clean_username = str(username).strip()
    if not clean_username:
        raise ValueError("用户名不能为空")

    config_data = load_users_config(users_file)
    target_record: dict[str, Any] | None = None
    for record in config_data["users"]:
        if record["username"] == clean_username:
            target_record = record
            break
    if target_record is None:
        raise ValueError("用户不存在")

    if password is not None:
        if not password:
            raise ValueError("密码不能为空")
        target_record["password"] = password
    if is_admin is not None:
        target_record["is_admin"] = bool(is_admin)

    if current_username and clean_username == current_username and not target_record["is_admin"]:
        raise ValueError("当前登录管理员不能取消自己的管理员权限")

    save_users_config(users_file, config_data, require_admin=True)
    return {
        "username": target_record["username"],
        "is_admin": target_record["is_admin"],
    }


def delete_user(users_file: Path, username: str, *, current_username: str | None = None) -> None:
    clean_username = str(username).strip()
    if not clean_username:
        raise ValueError("用户名不能为空")
    if current_username and clean_username == current_username:
        raise ValueError("不能删除当前登录账号")

    config_data = load_users_config(users_file)
    remaining_users = [record for record in config_data["users"] if record["username"] != clean_username]
    if len(remaining_users) == len(config_data["users"]):
        raise ValueError("用户不存在")

    save_users_config(users_file, {"users": remaining_users}, require_admin=True)
