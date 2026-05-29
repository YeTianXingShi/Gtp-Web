"""审计日志模块"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from gtpweb.db import open_db_connection

logger = logging.getLogger(__name__)


def log_audit(
    db_file: Path,
    *,
    username: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
    ip_address: str = "",
) -> None:
    try:
        with open_db_connection(db_file) as conn:
            conn.execute(
                """INSERT INTO audit_logs (username, action, target_type, target_id, detail, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (username, action, target_type, target_id, detail, ip_address),
            )
            conn.commit()
    except Exception:
        logger.exception("审计日志写入失败")


def query_audit_logs(
    db_file: Path,
    *,
    username: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = "SELECT id, username, action, target_type, target_id, detail, ip_address, created_at FROM audit_logs WHERE 1=1"
    params: list[Any] = []
    if username:
        query += " AND username = ?"
        params.append(username)
    if action:
        query += " AND action = ?"
        params.append(action)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with open_db_connection(db_file) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]
