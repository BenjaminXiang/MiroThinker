"""UTF-8 snapshot truncation contract (fix-web-lane-timeout-and-utf8-truncation).

Regression documented 2026-08-28: snapshot builders byte-sliced encoded
content at max_snapshot_bytes (16 384); a boundary inside a 3-byte CJK
character left invalid UTF-8 in WebSnapshotPayload.content and the contract
round-trip `model_dump(mode="json")` (knowledge_read._validate_recorded)
raised UnicodeDecodeError, killing the whole turn (internal_error on the
早稻田 test-set query).
"""

from __future__ import annotations

import json

import pytest

from src.data_agents.canonical_v2.knowledge_read import WebSnapshotPayload
from src.data_agents.canonical_v2.knowledge_serving_isolated import _utf8_truncated

# CJK-dense payload: after the ASCII JSON prefix every char is 3 bytes, so
# most byte offsets split a character.
PAYLOAD_TEXT = json.dumps(
    {"k": "深圳科创数据平台中文内容" * 40}, ensure_ascii=False
)


def _first_splitting_offset(encoded: bytes) -> int:
    """Smallest p such that encoded[:p] ends inside a multi-byte character."""
    i = 0
    while i < len(encoded):
        lead = encoded[i]
        if lead < 0x80:
            char_len = 1
        elif lead >= 0xF0:
            char_len = 4
        elif lead >= 0xE0:
            char_len = 3
        elif lead >= 0xC0:
            char_len = 2
        else:  # continuation byte without lead — defensive, not expected
            char_len = 1
        if char_len > 1:
            return i + 1  # cutting anywhere inside this char splits it
        i += char_len
    raise AssertionError("payload has no multi-byte character")


def test_documented_regression_byte_slice_crashes_contract_roundtrip():
    """Locks the OLD defect: a char-splitting byte slice is undecodable and
    blows up the contract model's JSON serialization (turn-killing)."""
    encoded = PAYLOAD_TEXT.encode("utf-8")
    split_at = _first_splitting_offset(encoded)
    with pytest.raises(UnicodeDecodeError):
        WebSnapshotPayload(
            snapshot_id="web-snapshot:sha256:test", content=encoded[:split_at]
        ).model_dump(mode="json")


def test_utf8_truncated_is_always_decodable_and_capped():
    encoded = PAYLOAD_TEXT.encode("utf-8")
    caps = [*range(1, 120), 16383, 16384, 16385, len(encoded) - 1]
    for cap in caps:
        cut = _utf8_truncated(PAYLOAD_TEXT, cap)
        assert len(cut) <= cap, f"cap={cap} len={len(cut)}"
        cut.decode("utf-8")  # must never raise at any cap


def test_utf8_truncated_passes_through_when_it_fits():
    encoded = PAYLOAD_TEXT.encode("utf-8")
    assert _utf8_truncated(PAYLOAD_TEXT, len(encoded)) == encoded
    assert _utf8_truncated(PAYLOAD_TEXT, len(encoded) + 10) == encoded


def test_utf8_truncated_keeps_prefix_bytes():
    """Truncation only ever drops a tail — the kept prefix is unchanged."""
    encoded = PAYLOAD_TEXT.encode("utf-8")
    cut = _utf8_truncated(PAYLOAD_TEXT, 16384)
    assert encoded.startswith(cut)


def test_snapshot_roundtrip_survives_at_16k_cap():
    """The production cap (16 384) must round-trip the contract model."""
    content = _utf8_truncated(PAYLOAD_TEXT, 16384)
    dumped = WebSnapshotPayload(
        snapshot_id="web-snapshot:sha256:test", content=content
    ).model_dump(mode="json")
    assert dumped["content"]
