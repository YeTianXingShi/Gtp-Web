"""
PDF 工作台蓝图

负责上传、解析、浏览 PDF，并将节选文本发送到聊天页。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from gtpweb.attachments import normalize_uploaded_file_name
from gtpweb.config import AppConfig
from gtpweb.db import open_db_connection
from gtpweb.pdf_workbench import (
    PDF_MAX_EXCERPT_CHARS,
    PDF_PARSE_STATUS_FAILED,
    PDF_PARSE_STATUS_PROCESSING,
    PDF_PARSE_STATUS_READY,
    build_excerpt_text_blocks,
    build_pdf_section_tree,
    parse_pdf_document,
    serialize_pdf_document_row,
)
from gtpweb.runtime_state import get_runtime_state
from gtpweb.user_store import get_user_record
from gtpweb.utils import safe_filename, safe_int

logger = logging.getLogger(__name__)


def _get_current_user_record(users_file: Path) -> dict[str, Any] | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None
    return get_user_record(users_file, username)


def _get_current_user(users_file: Path) -> str | None:
    record = _get_current_user_record(users_file)
    if record is None:
        return None
    return str(record["username"])


def _load_owned_document(conn: Any, document_id: int, username: str) -> Any:
    return conn.execute(
        """
        SELECT id, username, original_file_name, storage_path, display_title, parse_status,
               parse_error, parse_warning, section_source, file_size_bytes,
               page_count, total_chars, created_at, updated_at, parsed_at
        FROM pdf_documents
        WHERE id = ? AND username = ?
        """,
        (document_id, username),
    ).fetchone()


def create_pdf_workbench_blueprint(config: AppConfig) -> Blueprint:
    bp = Blueprint("pdf_workbench", __name__)
    users_file = config.users_file
    db_file = config.db_file
    upload_dir = config.upload_dir

    @bp.get("/pdf-workbench")
    def pdf_workbench_page() -> Any:
        record = _get_current_user_record(users_file)
        if record is None:
            return redirect(url_for("auth.login_page"))

        runtime_settings = get_runtime_state().settings
        return render_template(
            "pdf_workbench.html",
            username=record["username"],
            is_admin=bool(record["is_admin"]),
            max_upload_mb=runtime_settings.max_upload_mb,
            max_excerpt_chars=PDF_MAX_EXCERPT_CHARS,
        )

    @bp.get("/api/pdf-documents")
    def list_pdf_documents() -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        with open_db_connection(db_file) as conn:
            rows = conn.execute(
                """
                SELECT id, username, original_file_name, storage_path, display_title, parse_status,
                       parse_error, parse_warning, section_source, file_size_bytes,
                       page_count, total_chars, created_at, updated_at, parsed_at
                FROM pdf_documents
                WHERE username = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (username,),
            ).fetchall()

        return jsonify(
            {
                "ok": True,
                "documents": [serialize_pdf_document_row(row) for row in rows],
            }
        )

    @bp.post("/api/pdf-documents")
    def upload_pdf_document() -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        runtime_settings = get_runtime_state().settings
        uploaded_file = request.files.get("file")
        if uploaded_file is None:
            return jsonify({"ok": False, "error": "请上传 PDF 文件"}), 400

        original_name = normalize_uploaded_file_name(uploaded_file.filename or "document.pdf", "document")
        if not original_name.lower().endswith(".pdf"):
            return jsonify({"ok": False, "error": "仅支持上传 .pdf 文件"}), 400

        raw = uploaded_file.read()
        if not raw:
            return jsonify({"ok": False, "error": "上传文件为空"}), 400
        if len(raw) > runtime_settings.max_upload_bytes:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"PDF 文件过大，当前上限为 {runtime_settings.max_upload_mb} MB",
                    }
                ),
                400,
            )

        display_title = Path(original_name).stem[:120]
        with open_db_connection(db_file) as conn:
            cursor = conn.execute(
                """
                INSERT INTO pdf_documents (
                    username, original_file_name, storage_path, display_title,
                    parse_status, parse_error, parse_warning, section_source,
                    file_size_bytes, page_count, total_chars, created_at, updated_at
                )
                VALUES (?, ?, '', ?, 'processing', '', '', 'pages', ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (username, original_name, display_title, len(raw)),
            )
            document_id = int(cursor.lastrowid)
            conn.commit()

        user_dir = upload_dir / "pdf-workbench" / safe_filename(username)
        user_dir.mkdir(parents=True, exist_ok=True)
        storage_path = user_dir / f"{document_id}_{safe_filename(display_title)}.pdf"
        storage_path.write_bytes(raw)

        logger.info("PDF 上传完成，开始解析: 用户=%s 文档ID=%s 文件=%s", username, document_id, storage_path)
        try:
            parsed = parse_pdf_document(storage_path, display_name=display_title)
            with open_db_connection(db_file) as conn:
                conn.execute(
                    """
                    UPDATE pdf_documents
                    SET storage_path = ?, display_title = ?, parse_status = ?, parse_error = '',
                        parse_warning = ?, section_source = ?, file_size_bytes = ?,
                        page_count = ?, total_chars = ?, parsed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        str(storage_path),
                        parsed.display_title[:120],
                        PDF_PARSE_STATUS_READY,
                        "\n".join(parsed.warnings),
                        parsed.section_source,
                        len(raw),
                        parsed.page_count,
                        parsed.total_chars,
                        document_id,
                    ),
                )
                conn.execute("DELETE FROM pdf_pages WHERE document_id = ?", (document_id,))
                conn.execute("DELETE FROM pdf_sections WHERE document_id = ?", (document_id,))
                for page in parsed.pages:
                    conn.execute(
                        """
                        INSERT INTO pdf_pages (document_id, page_number, text, char_count, created_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (document_id, page.page_number, page.text, page.char_count),
                    )

                section_id_by_sort: dict[int, int] = {}
                for section in parsed.sections:
                    parent_id = (
                        section_id_by_sort.get(section.parent_sort_index)
                        if section.parent_sort_index is not None
                        else None
                    )
                    cursor = conn.execute(
                        """
                        INSERT INTO pdf_sections (
                            document_id, parent_id, title, level, start_page, end_page, sort_index, source, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (
                            document_id,
                            parent_id,
                            section.title[:200],
                            section.level,
                            section.start_page,
                            section.end_page,
                            section.sort_index,
                            section.source,
                        ),
                    )
                    section_id_by_sort[section.sort_index] = int(cursor.lastrowid)
                conn.commit()

                row = _load_owned_document(conn, document_id, username)
        except Exception as exc:
            error_message = str(exc).strip() or "PDF 解析失败"
            logger.exception("PDF 解析失败: 用户=%s 文档ID=%s", username, document_id)
            with open_db_connection(db_file) as conn:
                conn.execute(
                    """
                    UPDATE pdf_documents
                    SET storage_path = ?, parse_status = ?, parse_error = ?, parse_warning = '',
                        section_source = 'pages', page_count = 0, total_chars = 0,
                        parsed_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (str(storage_path), PDF_PARSE_STATUS_FAILED, error_message[:500], document_id),
                )
                conn.commit()
                row = _load_owned_document(conn, document_id, username)
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": error_message,
                        "document": serialize_pdf_document_row(row),
                    }
                ),
                400,
            )

        return jsonify({"ok": True, "document": serialize_pdf_document_row(row)}), 201

    @bp.get("/api/pdf-documents/<int:document_id>")
    def get_pdf_document(document_id: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        with open_db_connection(db_file) as conn:
            row = _load_owned_document(conn, document_id, username)
            if row is None:
                return jsonify({"ok": False, "error": "PDF 文档不存在"}), 404

            pages = []
            sections_tree = []
            if str(row["parse_status"]) == PDF_PARSE_STATUS_READY:
                pages = [
                    {
                        "page_number": int(page_row["page_number"]),
                        "char_count": int(page_row["char_count"]),
                        "has_text": bool(str(page_row["text"] or "").strip()),
                    }
                    for page_row in conn.execute(
                        """
                        SELECT page_number, text, char_count
                        FROM pdf_pages
                        WHERE document_id = ?
                        ORDER BY page_number ASC
                        """,
                        (document_id,),
                    ).fetchall()
                ]
                sections_rows = conn.execute(
                    """
                    SELECT id, parent_id, title, level, start_page, end_page, sort_index, source
                    FROM pdf_sections
                    WHERE document_id = ?
                    ORDER BY sort_index ASC
                    """,
                    (document_id,),
                ).fetchall()
                sections_tree = build_pdf_section_tree(sections_rows)

        return jsonify(
            {
                "ok": True,
                "document": serialize_pdf_document_row(row),
                "pages": pages,
                "sections": sections_tree,
            }
        )

    @bp.get("/api/pdf-documents/<int:document_id>/pages/<int:page_number>")
    def get_pdf_page(document_id: int, page_number: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        if page_number <= 0:
            return jsonify({"ok": False, "error": "页码必须大于 0"}), 400

        with open_db_connection(db_file) as conn:
            document_row = _load_owned_document(conn, document_id, username)
            if document_row is None:
                return jsonify({"ok": False, "error": "PDF 文档不存在"}), 404
            if str(document_row["parse_status"]) != PDF_PARSE_STATUS_READY:
                return jsonify({"ok": False, "error": "PDF 尚未完成解析"}), 409

            page_row = conn.execute(
                """
                SELECT page_number, text, char_count
                FROM pdf_pages
                WHERE document_id = ? AND page_number = ?
                """,
                (document_id, page_number),
            ).fetchone()
            if page_row is None:
                return jsonify({"ok": False, "error": "页码不存在"}), 404

        return jsonify(
            {
                "ok": True,
                "document": serialize_pdf_document_row(document_row),
                "page": {
                    "page_number": int(page_row["page_number"]),
                    "text": str(page_row["text"] or ""),
                    "char_count": int(page_row["char_count"] or 0),
                },
            }
        )

    @bp.post("/api/pdf-documents/<int:document_id>/excerpt")
    def build_pdf_excerpt_api(document_id: int) -> Any:
        username = _get_current_user(users_file)
        if not username:
            return jsonify({"ok": False, "error": "请先登录"}), 401

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "请求体必须是 JSON 对象"}), 400

        mode = str(payload.get("mode", "")).strip()
        with open_db_connection(db_file) as conn:
            document_row = _load_owned_document(conn, document_id, username)
            if document_row is None:
                return jsonify({"ok": False, "error": "PDF 文档不存在"}), 404
            if str(document_row["parse_status"]) != PDF_PARSE_STATUS_READY:
                return jsonify({"ok": False, "error": "PDF 尚未完成解析"}), 409

            if mode == "page_range":
                start_page = safe_int(payload.get("start_page"))
                end_page = safe_int(payload.get("end_page"))
                if not start_page or not end_page:
                    return jsonify({"ok": False, "error": "请提供有效的页码范围"}), 400
                if start_page > end_page:
                    return jsonify({"ok": False, "error": "起始页不能大于结束页"}), 400
                page_rows = conn.execute(
                    """
                    SELECT page_number, text, char_count
                    FROM pdf_pages
                    WHERE document_id = ? AND page_number BETWEEN ? AND ?
                    ORDER BY page_number ASC
                    """,
                    (document_id, start_page, end_page),
                ).fetchall()
                if not page_rows:
                    return jsonify({"ok": False, "error": "页码范围不存在"}), 404
                label = f"第 {start_page} - {end_page} 页"
                excerpt = build_excerpt_text_blocks(
                    document_row,
                    page_rows,
                    mode=mode,
                    label=label,
                )
                return jsonify({"ok": True, "excerpt": excerpt})

            if mode == "section":
                section_id = safe_int(payload.get("section_id"))
                if not section_id:
                    return jsonify({"ok": False, "error": "请提供章节 ID"}), 400
                section_row = conn.execute(
                    """
                    SELECT id, title, start_page, end_page
                    FROM pdf_sections
                    WHERE document_id = ? AND id = ?
                    """,
                    (document_id, section_id),
                ).fetchone()
                if section_row is None:
                    return jsonify({"ok": False, "error": "章节不存在"}), 404
                page_rows = conn.execute(
                    """
                    SELECT page_number, text, char_count
                    FROM pdf_pages
                    WHERE document_id = ? AND page_number BETWEEN ? AND ?
                    ORDER BY page_number ASC
                    """,
                    (
                        document_id,
                        int(section_row["start_page"]),
                        int(section_row["end_page"]),
                    ),
                ).fetchall()
                excerpt = build_excerpt_text_blocks(
                    document_row,
                    page_rows,
                    mode=mode,
                    label=f"{section_row['title']}（第 {section_row['start_page']} - {section_row['end_page']} 页）",
                )
                excerpt["section_id"] = int(section_row["id"])
                excerpt["section_title"] = str(section_row["title"])
                return jsonify({"ok": True, "excerpt": excerpt})

        return jsonify({"ok": False, "error": "不支持的节选模式"}), 400

    return bp
