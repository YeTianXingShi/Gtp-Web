"""
JSONC 解析模块

支持 JSONC 格式（带注释的 JSON）的解析，包括：
- 单行注释（//）
- 多行注释（/* */）
- 尾随逗号
"""

from __future__ import annotations

import json
from typing import Any


def _strip_jsonc_comments(raw_text: str) -> str:
    """
    移除 JSONC 注释（单行和多行）

    Args:
        raw_text: 原始 JSONC 文本

    Returns:
        移除注释后的 JSON 文本
    """
    result: list[str] = []
    in_string = False
    escape = False
    index = 0
    length = len(raw_text)

    while index < length:
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < length else ""

        # 在字符串内直接添加
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        # 进入字符串
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        # 处理单行注释 //
        if char == "/" and next_char == "/":
            result.extend([" ", " "])
            index += 2
            while index < length and raw_text[index] not in {"\n", "\r"}:
                result.append(" ")
                index += 1
            continue

        # 处理多行注释 /* */
        if char == "/" and next_char == "*":
            result.extend([" ", " "])
            index += 2
            while index < length:
                comment_char = raw_text[index]
                comment_next = raw_text[index + 1] if index + 1 < length else ""
                if comment_char == "*" and comment_next == "/":
                    result.extend([" ", " "])
                    index += 2
                    break
                # 保留换行符以维持错误信息中的行号
                result.append("\n" if comment_char == "\n" else "\r" if comment_char == "\r" else " ")
                index += 1
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _strip_trailing_commas(raw_text: str) -> str:
    """
    移除尾随逗号

    Args:
        raw_text: JSON 文本

    Returns:
        移除尾随逗号后的 JSON 文本
    """
    chars = list(raw_text)
    in_string = False
    escape = False
    length = len(chars)
    index = 0

    while index < length:
        char = chars[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            index += 1
            continue

        if char != ",":
            index += 1
            continue

        # 检查逗号后是否为结束标记
        look_ahead = index + 1
        while look_ahead < length and chars[look_ahead] in {" ", "\t", "\n", "\r"}:
            look_ahead += 1
        if look_ahead < length and chars[look_ahead] in {"]", "}"}:
            chars[index] = " "  # 将尾随逗号替换为空格
        index += 1

    return "".join(chars)


def jsonc_loads(raw_text: str) -> Any:
    """
    解析 JSONC 文本

    Args:
        raw_text: JSONC 文本

    Returns:
        解析后的 Python 对象

    Raises:
        json.JSONDecodeError: 当 JSON 格式无效时
    """
    # 移除注释
    normalized = _strip_jsonc_comments(str(raw_text or ""))
    # 移除尾随逗号
    normalized = _strip_trailing_commas(normalized)
    return json.loads(normalized)
