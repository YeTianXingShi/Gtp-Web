from __future__ import annotations

import io

from gtpweb.pdf_workbench import (
    PDF_PARSE_STATUS_FAILED,
    PDF_SECTION_SOURCE_OUTLINE,
    ParsedPdfDocument,
    ParsedPdfPage,
    ParsedPdfSection,
)


def test_pdf_workbench_page_requires_login(client):
    resp = client.get("/pdf-workbench")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_pdf_workbench_upload_browse_and_excerpt(logged_in_client, monkeypatch):
    from gtpweb.blueprints import pdf_workbench as pdf_workbench_blueprint

    def _fake_parse(_file_path, *, display_name=""):
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

    monkeypatch.setattr(pdf_workbench_blueprint, "parse_pdf_document", _fake_parse)

    upload_resp = logged_in_client.post(
        "/api/pdf-documents",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "whitepaper.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_resp.status_code == 201
    upload_data = upload_resp.get_json()
    document_id = int(upload_data["document"]["id"])
    assert upload_data["document"]["parse_status"] == "ready"

    list_resp = logged_in_client.get("/api/pdf-documents")
    assert list_resp.status_code == 200
    assert any(doc["id"] == document_id for doc in list_resp.get_json()["documents"])

    detail_resp = logged_in_client.get(f"/api/pdf-documents/{document_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.get_json()
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

    def _raise_parse_error(_file_path, *, display_name=""):
        raise ValueError("未提取到可用文本")

    monkeypatch.setattr(pdf_workbench_blueprint, "parse_pdf_document", _raise_parse_error)

    upload_resp = logged_in_client.post(
        "/api/pdf-documents",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "broken.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_resp.status_code == 400
    upload_data = upload_resp.get_json()
    assert upload_data["document"]["parse_status"] == PDF_PARSE_STATUS_FAILED
    assert "未提取到可用文本" in upload_data["document"]["parse_error"]
