"""
工具函数模块

提供各种辅助工具函数，包括：
- 文件名安全处理
- 类型安全转换
- 模型名称匹配
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from typing import Any, Iterable


def safe_filename(raw: str) -> str:
    """
    生成安全的文件名

    将文件名中的非法字符替换为下划线，并限制长度。

    Args:
        raw: 原始文件名

    Returns:
        清理后的安全文件名（最长 80 字符）
    """
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("_")
    return cleaned[:80] or "conversation"


def safe_int(value: Any) -> int | None:
    """
    安全地转换为整数

    Args:
        value: 待转换的值

    Returns:
        转换后的非负整数，转换失败则返回 None
    """
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_model_match_patterns(
    raw_value: str,
    *,
    default: Iterable[str] = (),
) -> list[str]:
    """
    解析模型匹配模式列表

    Args:
        raw_value: 逗号分隔的模式字符串
        default: 默认模式列表

    Returns:
        模式列表（转小写）
    """
    patterns = [item.strip().lower() for item in str(raw_value or "").split(",") if item.strip()]
    return patterns or [item.strip().lower() for item in default if str(item).strip()]


def model_name_matches_patterns(model_name: str, patterns: Iterable[str]) -> bool:
    """
    检查模型名称是否匹配任一模式

    Args:
        model_name: 模型名称
        patterns: 模式列表（支持通配符）

    Returns:
        是否匹配成功
    """
    normalized_name = str(model_name or "").strip().lower()
    if not normalized_name:
        return False

    for pattern in patterns:
        normalized_pattern = str(pattern or "").strip().lower()
        if not normalized_pattern:
            continue
        if fnmatchcase(normalized_name, normalized_pattern):
            return True
    return False
