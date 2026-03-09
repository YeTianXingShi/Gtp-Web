from __future__ import annotations

from gtpweb.attachments import (
    normalize_uploaded_file_name,
    parse_allowed_attachment_exts,
    validate_attachment,
)


def test_parse_allowed_attachment_exts_normalizes_dot_and_case():
    exts = parse_allowed_attachment_exts("DOCX, .XLSX, txt")
    assert ".docx" in exts
    assert ".xlsx" in exts
    assert ".txt" in exts


def test_validate_attachment_rejects_non_whitelist_extension():
    ok, message = validate_attachment("report.pdf", "application/pdf", {".docx", ".xlsx"})
    assert not ok
    assert message is not None
    assert "不支持的文件类型" in message


def test_validate_attachment_accepts_expected_mime():
    ok, message = validate_attachment(
        "sheet.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        {".xlsx"},
    )
    assert ok
    assert message is None


def test_normalize_uploaded_file_name_preserves_ext_for_unicode_name():
    normalized = normalize_uploaded_file_name(
        "📊 平台奖励政策与结算执行总表.docx",
        "file_abc12345",
    )
    assert normalized.endswith(".docx")
