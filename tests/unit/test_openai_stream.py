from __future__ import annotations

from gtpweb.openai_stream import sse_payload


def test_sse_payload_uses_real_newline_separator() -> None:
    payload = sse_payload({"type": "delta", "text": "hi"})
    assert payload.endswith("\n\n")
    assert "\\n\\n" not in payload
