from __future__ import annotations

import io

from gtpweb.pdf_workbench import (
    PDF_PARSE_STATUS_FAILED,
    PDF_PARSE_STATUS_PENDING,
    PDF_PARSE_STATUS_READY,
    PDF_SECTION_SOURCE_OUTLINE,
    ParsedPdfDocument,
    ParsedPdfPage,
    ParsedPdfSection,
)


def test_pdf_workbench_page_requires_login(client):
    resp = client.get("/pdf-workbench")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_pdf_workbench_upload_returns_pending_and_json_uses_utf8(logged_in_client, monkeypatch):
    from gtpweb.blueprints import pdf_workbench as pdf_workbench_blueprint

    monkeypatch.setattr(pdf_workbench_blueprint, "enqueue_pdf_parse_job", lambda **kwargs: None)

    upload_resp = logged_in_client.post(
        "/api/pdf-documents",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "queued.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_resp.status_code == 202
    upload_data = upload_resp.get_json()
    assert upload_data["document"]["parse_status"] == PDF_PARSE_STATUS_PENDING
    assert upload_data["document"]["parse_progress"] == 0
    assert upload_data["document"]["parse_stage"] == "等待后台任务排队"

    raw_body = upload_resp.get_data(as_text=True)
    assert "等待后台任务排队" in raw_body
    assert "\\u7b49\\u5f85\\u540e\\u53f0\\u4efb\\u52a1\\u6392\\u961f" not in raw_body


def test_pdf_workbench_upload_browse_and_excerpt(logged_in_client, monkeypatch):
    from gtpweb.blueprints import pdf_workbench as pdf_workbench_blueprint
    from gtpweb import pdf_workbench_tasks

    def _fake_parse(_file_path, *, display_name="", progress_callback=None):
        if progress_callback is not None:
            progress_callback(15, "正在读取 PDF 页面")
            progress_callback(70, "正在识别章节结构")
        return ParsedPdfDocument(
            display_title=display_name or "技术白皮书",
            page_count=4,
            total_chars=48,
            section_source=PDF_SECTION_SOURCE_OUTLINE,
            pages=(
                ParsedPdfPage(page_number=1, text="第一页内容", char_count=5),
                ParsedPdfPage(page_number=2, text="第二页内容", char_count=5),
                ParsedPdfPage(page_number=3, text="第三页内容", char_count=5),
                ParsedPdfPage(page_number=4, text="第四页内容", char_count=5),
            ),
            sections=(
                ParsedPdfSection(
                    title="第一章 概览",
                    level=1,
                    start_page=1,
                    end_page=2,
                    sort_index=1,
                    parent_sort_index=None,
                    source=PDF_SECTION_SOURCE_OUTLINE,
                ),
                ParsedPdfSection(
                    title="第二章 细节",
                    level=1,
                    start_page=3,
                    end_page=4,
                    sort_index=2,
                    parent_sort_index=None,
                    source=PDF_SECTION_SOURCE_OUTLINE,
                ),
            ),
            warnings=(),
        )

    monkeypatch.setattr(pdf_workbench_tasks, "parse_pdf_document", _fake_parse)

    def _enqueue_inline(**kwargs):
        pdf_workbench_tasks.run_pdf_parse_job(**kwargs)
        return None

    monkeypatch.setattr(pdf_workbench_blueprint, "enqueue_pdf_parse_job", _enqueue_inline)

    upload_resp = logged_in_client.post(
        "/api/pdf-documents",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "whitepaper.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_resp.status_code == 202
    upload_data = upload_resp.get_json()
    document_id = int(upload_data["document"]["id"])
    assert upload_data["document"]["parse_status"] == PDF_PARSE_STATUS_PENDING

    list_resp = logged_in_client.get("/api/pdf-documents")
    assert list_resp.status_code == 200
    assert any(
        doc["id"] == document_id and doc["parse_status"] == PDF_PARSE_STATUS_READY
        for doc in list_resp.get_json()["documents"]
    )

    detail_resp = logged_in_client.get(f"/api/pdf-documents/{document_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.get_json()
    assert detail_data["document"]["parse_status"] == PDF_PARSE_STATUS_READY
    assert detail_data["document"]["parse_progress"] == 100
    assert detail_data["document"]["page_count"] == 4
    assert len(detail_data["pages"]) == 4
    assert len(detail_data["sections"]) == 2

    first_section_id = int(detail_data["sections"][0]["id"])
    excerpt_resp = logged_in_client.post(
        f"/api/pdf-documents/{document_id}/excerpt",
        json={"mode": "section", "section_id": first_section_id},
    )
    assert excerpt_resp.status_code == 200
    excerpt_data = excerpt_resp.get_json()["excerpt"]
    assert excerpt_data["mode"] == "section"
    assert "第一章 概览" in excerpt_data["text"]
    assert "第一页内容" in excerpt_data["text"]

    page_excerpt_resp = logged_in_client.post(
        f"/api/pdf-documents/{document_id}/excerpt",
        json={"mode": "page_range", "start_page": 2, "end_page": 3},
    )
    assert page_excerpt_resp.status_code == 200
    page_excerpt = page_excerpt_resp.get_json()["excerpt"]
    assert page_excerpt["start_page"] == 2
    assert page_excerpt["end_page"] == 3
    assert "第二页内容" in page_excerpt["text"]
    assert "第三页内容" in page_excerpt["text"]


def test_pdf_workbench_upload_records_failed_status(logged_in_client, monkeypatch):
    from gtpweb.blueprints import pdf_workbench as pdf_workbench_blueprint
    from gtpweb import pdf_workbench_tasks

    def _raise_parse_error(_file_path, *, display_name="", progress_callback=None):
        if progress_callback is not None:
            progress_callback(36, "正在读取 PDF 页面")
        raise ValueError("未提取到可用文本")

    monkeypatch.setattr(pdf_workbench_tasks, "parse_pdf_document", _raise_parse_error)

    def _enqueue_inline(**kwargs):
        pdf_workbench_tasks.run_pdf_parse_job(**kwargs)
        return None

    monkeypatch.setattr(pdf_workbench_blueprint, "enqueue_pdf_parse_job", _enqueue_inline)

    upload_resp = logged_in_client.post(
        "/api/pdf-documents",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "broken.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_resp.status_code == 202
    upload_data = upload_resp.get_json()
    document_id = int(upload_data["document"]["id"])
    assert upload_data["document"]["parse_status"] == PDF_PARSE_STATUS_PENDING

    detail_resp = logged_in_client.get(f"/api/pdf-documents/{document_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.get_json()
    assert detail_data["document"]["parse_status"] == PDF_PARSE_STATUS_FAILED
    assert detail_data["document"]["parse_progress"] == 36
    assert "未提取到可用文本" in detail_data["document"]["parse_error"]
