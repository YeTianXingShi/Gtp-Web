"""
Token 用量记录与查询模块
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gtpweb.db import open_db_connection


def record_token_usage(
    db_file: Path,
    *,
    username: str,
    conversation_id: int | None,
    message_id: int | None,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    if input_tokens <= 0 and output_tokens <= 0:
        return
    with open_db_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO token_usage
                (username, conversation_id, message_id, model, provider, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, conversation_id, message_id, model, provider,
             max(0, input_tokens), max(0, output_tokens)),
        )
        conn.commit()


def get_user_usage_summary(
    db_file: Path,
    username: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT model, provider,
               SUM(input_tokens) AS total_input,
               SUM(output_tokens) AS total_output,
               COUNT(*) AS request_count
        FROM token_usage
        WHERE username = ?
    """
    params: list[Any] = [username]
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at < ?"
        params.append(end_date)
    query += " GROUP BY model, provider ORDER BY total_output DESC"

    with open_db_connection(db_file) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [
        {
            "model": row["model"],
            "provider": row["provider"],
            "input_tokens": row["total_input"],
            "output_tokens": row["total_output"],
            "request_count": row["request_count"],
        }
        for row in rows
    ]


def get_all_users_usage(
    db_file: Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT username, model, provider,
               SUM(input_tokens) AS total_input,
               SUM(output_tokens) AS total_output,
               COUNT(*) AS request_count
        FROM token_usage
        WHERE 1=1
    """
    params: list[Any] = []
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at < ?"
        params.append(end_date)
    query += " GROUP BY username, model, provider ORDER BY username, total_output DESC"

    with open_db_connection(db_file) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [
        {
            "username": row["username"],
            "model": row["model"],
            "provider": row["provider"],
            "input_tokens": row["total_input"],
            "output_tokens": row["total_output"],
            "request_count": row["request_count"],
        }
        for row in rows
    ]


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    return (
        input_tokens * input_price_per_million / 1_000_000
        + output_tokens * output_price_per_million / 1_000_000
    )
