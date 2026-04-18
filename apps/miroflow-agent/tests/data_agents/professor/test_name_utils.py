# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.name_utils import (
    derive_english_name_candidates_from_url,
    sanitize_english_person_name,
)


def test_derive_english_name_candidates_from_url_supports_xian_slug():
    candidates = derive_english_name_candidates_from_url(
        "https://homepage.hit.edu.cn/xianchengqian"
    )

    assert "Chengqian Xian" in candidates
    assert "Xian Chengqian" in candidates


def test_derive_english_name_candidates_from_url_supports_camel_case_slug():
    candidates = derive_english_name_candidates_from_url(
        "http://ise.sysu.edu.cn/teacher/CaiMing"
    )

    assert "Ming Cai" in candidates
    assert "Cai Ming" in candidates


def test_sanitize_english_person_name_rejects_early_access():
    assert sanitize_english_person_name("Early Access") is None


def test_derive_english_name_candidates_from_url_rejects_generic_slug():
    assert derive_english_name_candidates_from_url("https://example.edu.cn/faculty/main.htm") == []
