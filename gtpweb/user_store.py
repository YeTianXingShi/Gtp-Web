"""
用户存储和管理模块

负责用户配置的加载、保存和管理，包括：
- 用户配置的加载和验证
- 用户认证（登录验证）
- 用户 CRUD 操作
- 权限管理（管理员/普通用户）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _normalize_user_record(raw_record: Any, index: int) -> dict[str, Any]:
    """
    规范化用户记录

    Args:
        raw_record: 原始用户记录
        index: 在数组中的索引（用于错误消息）

    Returns:
        规范化后的用户记录

    Raises:
        ValueError: 当记录格式无效时
    """
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
    """
    规范化用户配置

    Args:
        raw_data: 原始配置数据
        require_admin: 是否要求至少有一个管理员

    Returns:
        规范化后的用户配置

    Raises:
        ValueError: 当配置格式无效时
    """
    if not isinstance(raw_data, dict):
        raise ValueError("用户配置格式错误: 根节点必须是对象")

    raw_users = raw_data.get("users")
    normalized_users: list[dict[str, Any]] = []

    # 支持对象格式（{username: password}）
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
    # 支持数组格式（[{username, password, is_admin}, ...]）
    elif isinstance(raw_users, list):
        for index, raw_record in enumerate(raw_users):
            normalized_users.append(_normalize_user_record(raw_record, index))
    else:
        raise ValueError("用户配置格式错误: 'users' 必须是对象或数组")

    if not normalized_users:
        raise ValueError("用户配置格式错误: 至少需要一个用户")

    # 检查重复用户名
    seen_usernames: set[str] = set()
    for record in normalized_users:
        username = record["username"]
        if username in seen_usernames:
            raise ValueError(f"用户配置格式错误: 用户名重复 {username}")
        seen_usernames.add(username)

    # 检查管理员账号
    if require_admin and not any(record["is_admin"] for record in normalized_users):
        raise ValueError("用户配置格式错误: 至少需要保留一个管理员账号")

    return {"users": normalized_users}


def load_users_config(users_file: Path, *, require_admin: bool = False) -> dict[str, list[dict[str, Any]]]:
    """
    从文件加载用户配置

    Args:
        users_file: 用户配置文件路径
        require_admin: 是否要求至少有一个管理员

    Returns:
        规范化后的用户配置

    Raises:
        FileNotFoundError: 当配置文件不存在时
        ValueError: 当配置格式无效时
    """
    if not users_file.exists():
        raise FileNotFoundError(
            f"Users config not found: {users_file}. Copy config/users.example.json to config/users.json first."
        )
    raw_data = json.loads(users_file.read_text(encoding="utf-8"))
    return normalize_users_config(raw_data, require_admin=require_admin)


def users_config_to_text(config_data: dict[str, list[dict[str, Any]]]) -> str:
    """
    将用户配置转换为 JSON 文本

    Args:
        config_data: 用户配置数据

    Returns:
        格式化的 JSON 文本
    """
    return json.dumps(config_data, ensure_ascii=False, indent=2) + "\n"


def save_users_config(users_file: Path, config_data: dict[str, Any], *, require_admin: bool = False) -> None:
    """
    保存用户配置到文件

    Args:
        users_file: 用户配置文件路径
        config_data: 用户配置数据
        require_admin: 是否要求至少有一个管理员

    Raises:
        ValueError: 当配置无效时
    """
    normalized = normalize_users_config(config_data, require_admin=require_admin)
    users_file.parent.mkdir(parents=True, exist_ok=True)
    users_file.write_text(users_config_to_text(normalized), encoding="utf-8")


def save_users_config_text(users_file: Path, raw_text: str, *, require_admin: bool = False) -> None:
    """
    保存用户配置文本到文件

    Args:
        users_file: 用户配置文件路径
        raw_text: 配置文件文本内容
        require_admin: 是否要求至少有一个管理员

    Raises:
        ValueError: 当 JSON 解析失败或配置无效时
    """
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: 第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}") from exc
    save_users_config(users_file, raw_data, require_admin=require_admin)


def load_user_password_map(users_file: Path) -> dict[str, str]:
    """
    加载用户密码映射

    Args:
        users_file: 用户配置文件路径

    Returns:
        用户名到密码的映射字典
    """
    config_data = load_users_config(users_file)
    return {record["username"]: record["password"] for record in config_data["users"]}


def list_users(users_file: Path) -> list[dict[str, Any]]:
    """
    获取用户列表

    Args:
        users_file: 用户配置文件路径

    Returns:
        用户列表（按管理员优先、用户名字母顺序排序）
    """
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
    """
    获取用户记录

    Args:
        users_file: 用户配置文件路径
        username: 用户名

    Returns:
        用户记录，不存在则返回 None
    """
    clean_username = str(username).strip()
    if not clean_username:
        return None
    config_data = load_users_config(users_file)
    for record in config_data["users"]:
        if record["username"] == clean_username:
            return dict(record)
    return None


def verify_user_credentials(users_file: Path, username: str, password: str) -> dict[str, Any] | None:
    """
    验证用户凭据

    Args:
        users_file: 用户配置文件路径
        username: 用户名
        password: 密码

    Returns:
        用户记录，验证失败则返回 None
    """
    record = get_user_record(users_file, username)
    if record is None or record["password"] != password:
        return None
    return record


def create_user(users_file: Path, username: str, password: str, is_admin: bool) -> dict[str, Any]:
    """
    创建新用户

    Args:
        users_file: 用户配置文件路径
        username: 用户名
        password: 密码
        is_admin: 是否为管理员

    Returns:
        新创建的用户记录

    Raises:
        ValueError: 当用户名已存在或参数无效时
    """
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
    """
    更新用户信息

    Args:
        users_file: 用户配置文件路径
        username: 要更新的用户名
        password: 新密码（可选）
        is_admin: 新管理员状态（可选）
        current_username: 当前登录用户名（用于防止取消自己的管理员权限）

    Returns:
        更新后的用户记录

    Raises:
        ValueError: 当参数无效或操作不合法时
    """
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

    # 防止取消自己的管理员权限
    if current_username and clean_username == current_username and not target_record["is_admin"]:
        raise ValueError("当前登录管理员不能取消自己的管理员权限")

    save_users_config(users_file, config_data, require_admin=True)
    return {
        "username": target_record["username"],
        "is_admin": target_record["is_admin"],
    }


def delete_user(users_file: Path, username: str, *, current_username: str | None = None) -> None:
    """
    删除用户

    Args:
        users_file: 用户配置文件路径
        username: 要删除的用户名
        current_username: 当前登录用户名（用于防止删除自己）

    Raises:
        ValueError: 当参数无效或操作不合法时
    """
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
