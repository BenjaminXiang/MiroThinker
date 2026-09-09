"""Unit tests for eval_precision pure functions (no live DB needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_precision import _walk_candidates, _count_unsourced_web, _display_name


def test_walk_candidates_collects_typed_dicts():
    response = {
        "query_type": "B_company_topic",
        "candidates": [
            {"type": "company", "name": "普渡科技", "snippet": "普渡科技是一家..."},
            {"type": "web", "title": "云迹科技", "url": "https://x.com", "snippet": "云迹..."},
            {"type": "web", "title": "无源条目", "url": "", "snippet": "..."},
            {"type": "paper", "label": "pFedGPA", "url": "/browse#paper/X"},
        ],
        "nested": {"results": [{"type": "professor", "name": "王学谦", "snippet": "王学谦"}]},
    }
    names = [_display_name(c) for c in _walk_candidates(response)]
    assert "普渡科技" in names
    assert "王学谦" in names
    assert "云迹科技" in names
    assert "pFedGPA" in names  # rendered candidates carry name as "label"


def test_count_unsourced_web_flags_urlless_web():
    response = {
        "candidates": [
            {"type": "web", "title": "a", "url": "https://a.com"},
            {"type": "web", "title": "b", "url": ""},
            {"source_type": "web", "title": "c"},
            {"type": "company", "name": "x", "url": ""},
        ]
    }
    assert _count_unsourced_web(response) == 2
