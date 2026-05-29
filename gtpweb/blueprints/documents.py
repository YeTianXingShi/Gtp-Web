"""
文档下载中心蓝图

提供 SOP/通知等文档的浏览、下载和管理功能。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request, send_file, session

from gtpweb.config import AppConfig
from gtpweb.db import open_db_connection
from gtpweb.user_store import get_user_record

logger = logging.getLogger(__name__)


def _get_current_user(users_file: Path) -> str | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None
    record = get_user_record(users_file, username)
    if record is None:
        return None
    return str(record["username"])


def _require_admin(users_file: Path) -> tuple[dict[str, Any] | None, Response | None]:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None, (jsonify({"ok": False, "error": "请先登录"}), 401)
    record = get_user_record(users_file, username)
    if record is None or not record.get("is_admin"):
        return None, (jsonify({"ok": False, "error": "需要管理员权限"}), 403)
    return record, None


def create_documents_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("documents", __name__)

    db_file = config.db_file
    users_file = config.users_file
    upload_dir = config.upload_dir
    documents_dir = upload_dir.parent / "documents"

    @bp.get("/api/documents")
    def list_documents() -> Response:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        category = request.args.get("category", "").strip()
        query = "SELECT id, title, category, file_name, file_size, mime_type, uploaded_by, created_at, updated_at FROM documents"
        params: list[Any] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY category, updated_at DESC"

        with open_db_connection(db_file) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        documents = [
            {
                "id": row["id"],
                "title": row["title"],
                "category": row["category"],
                "file_name": row["file_name"],
                "file_size": row["file_size"],
                "mime_type": row["mime_type"],
                "uploaded_by": row["uploaded_by"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        return jsonify({"ok": True, "documents": documents})

    @bp.get("/api/documents/<int:doc_id>/download")
    def download_document(doc_id: int) -> Response:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        with open_db_connection(db_file) as conn:
            row = conn.execute(
                "SELECT file_path, file_name, mime_type FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()

        if row is None:
            return jsonify({"ok": False, "error": "文档不存在"}), 404

        file_path = Path(row["file_path"])
        if not file_path.exists():
            return jsonify({"ok": False, "error": "文件不存在"}), 404

        return send_file(
            file_path,
            mimetype=row["mime_type"],
            as_attachment=True,
            download_name=row["file_name"],
        )

    @bp.post("/api/admin/documents")
    def upload_document() -> Response:
        admin, err = _require_admin(users_file)
        if err:
            return err

        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"ok": False, "error": "请选择文件"}), 400

        title = request.form.get("title", "").strip() or file.filename
        category = request.form.get("category", "").strip() or "未分类"

        raw = file.read()
        if not raw:
            return jsonify({"ok": False, "error": "文件为空"}), 400

        file_name = file.filename
        mime_type = (file.mimetype or "application/octet-stream").strip()
        file_size = len(raw)

        documents_dir.mkdir(parents=True, exist_ok=True)
        saved_name = f"{uuid4().hex}_{file_name}"
        saved_path = documents_dir / saved_name
        saved_path.write_bytes(raw)

        with open_db_connection(db_file) as conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (title, category, file_path, file_name, file_size, mime_type, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, str(saved_path), file_name, file_size, mime_type, admin["username"]),
            )
            doc_id = cursor.lastrowid
            conn.commit()

        logger.info("文档上传完成: ID=%s 标题=%s 分类=%s 上传者=%s", doc_id, title, category, admin["username"])
        return jsonify({"ok": True, "document": {"id": doc_id, "title": title, "category": category}}), 201

    @bp.put("/api/admin/documents/<int:doc_id>")
    def update_document(doc_id: int) -> Response:
        admin, err = _require_admin(users_file)
        if err:
            return err

        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        category = str(payload.get("category", "")).strip()

        if not title and not category:
            return jsonify({"ok": False, "error": "至少提供 title 或 category"}), 400

        with open_db_connection(db_file) as conn:
            row = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row is None:
                return jsonify({"ok": False, "error": "文档不存在"}), 404

            updates: list[str] = []
            params: list[Any] = []
            if title:
                updates.append("title = ?")
                params.append(title)
            if category:
                updates.append("category = ?")
                params.append(category)
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(doc_id)

            conn.execute(
                f"UPDATE documents SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()

        return jsonify({"ok": True})

    @bp.delete("/api/admin/documents/<int:doc_id>")
    def delete_document(doc_id: int) -> Response:
        admin, err = _require_admin(users_file)
        if err:
            return err

        with open_db_connection(db_file) as conn:
            row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row is None:
                return jsonify({"ok": False, "error": "文档不存在"}), 404

            file_path = Path(row["file_path"])
            if file_path.exists():
                file_path.unlink()

            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()

        logger.info("文档删除完成: ID=%s 操作者=%s", doc_id, admin["username"])
        return jsonify({"ok": True})

    return bp
