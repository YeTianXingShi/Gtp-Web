from __future__ import annotations

import json
from typing import Any


def _strip_jsonc_comments(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    index = 0
    length = len(raw_text)

    while index < length:
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < length else ""

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

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            result.extend([" ", " "])
            index += 2
            while index < length and raw_text[index] not in {"\n", "\r"}:
                result.append(" ")
                index += 1
            continue

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
                result.append("\n" if comment_char == "\n" else "\r" if comment_char == "\r" else " ")
                index += 1
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _strip_trailing_commas(raw_text: str) -> str:
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

        look_ahead = index + 1
        while look_ahead < length and chars[look_ahead] in {" ", "\t", "\n", "\r"}:
            look_ahead += 1
        if look_ahead < length and chars[look_ahead] in {"]", "}"}:
            chars[index] = " "
        index += 1

    return "".join(chars)


def jsonc_loads(raw_text: str) -> Any:
    normalized = _strip_jsonc_comments(str(raw_text or ""))
    normalized = _strip_trailing_commas(normalized)
    return json.loads(normalized)
