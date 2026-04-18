# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for research direction cleaner."""
from __future__ import annotations

import pytest

from src.data_agents.professor.direction_cleaner import clean_directions


class TestCleanDirections:
    """Test clean_directions function."""

    def test_clean_list_passes_through(self):
        """Happy path: already clean directions pass through unchanged."""
        raw = ["机器视觉", "图像处理"]
        assert clean_directions(raw) == ["机器视觉", "图像处理"]

    def test_truncation_at_sentinel(self):
        """Truncate at sentinel phrase, keeping text before it."""
        raw = ["微流控 主讲本科课程：《传感器与检测技术》"]
        result = clean_directions(raw)
        assert result == ["微流控"]

    def test_truncation_at_course_sentinel(self):
        """Truncate at '课程' sentinel."""
        raw = ["信号处理 课程：数字信号处理"]
        assert clean_directions(raw) == ["信号处理"]

    def test_keeps_curriculum_theory_as_legitimate_hss_direction(self):
        """Do not drop legitimate HSS fields that happen to contain '课程'."""
        raw = ["课程与教学论"]
        assert clean_directions(raw) == ["课程与教学论"]

    def test_truncation_at_teaching_sentinel(self):
        """Truncate at '教学' sentinel."""
        raw = ["人工智能 教学成果：获奖"]
        assert clean_directions(raw) == ["人工智能"]

    def test_year_range_dropped(self):
        """Items with year ranges are dropped entirely."""
        raw = ["2012–2017 博士研究生"]
        assert clean_directions(raw) == []

    def test_sentinel_truncates_before_year_range(self):
        """Sentinel truncation happens before year-range check; prefix is kept."""
        raw = ["《C语言》 教育背景： 2012–2017"]
        # Truncated at '教育背景' → '《C语言》', which is valid
        assert clean_directions(raw) == ["《C语言》"]

    def test_year_range_with_dash(self):
        """Year range with ASCII dash."""
        raw = ["2018-2022 某某项目"]
        assert clean_directions(raw) == []

    def test_long_item_dropped(self):
        """Items longer than 30 characters are dropped."""
        raw = ["这是一个非常长的字符串，它不是一个真正的研究方向，应该被过滤掉因为它太长了超过三十个字"]
        assert len(raw[0]) > 30
        assert clean_directions(raw) == []

    def test_compound_split(self):
        """Compound items with '、' are split into separate directions."""
        raw = ["机器视觉、图像处理"]
        assert clean_directions(raw) == ["机器视觉", "图像处理"]

    def test_compound_split_semicolon(self):
        """Compound items with '；' are split."""
        raw = ["深度学习；自然语言处理"]
        assert clean_directions(raw) == ["深度学习", "自然语言处理"]

    def test_deduplication_case_insensitive(self):
        """Deduplicate case-insensitively, keeping first occurrence."""
        raw = ["ML", "ml", "ML"]
        assert clean_directions(raw) == ["ML"]

    def test_deduplication_chinese(self):
        """Chinese duplicates are removed."""
        raw = ["机器学习", "深度学习", "机器学习"]
        assert clean_directions(raw) == ["机器学习", "深度学习"]

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert clean_directions([]) == []

    def test_all_items_cleaned_out(self):
        """When all items are junk, return empty list."""
        raw = ["主讲课程A", "2020-2024 教育背景"]
        assert clean_directions(raw) == []

    def test_strip_punctuation(self):
        """Leading/trailing punctuation is stripped."""
        raw = ["，机器视觉。", "、深度学习；"]
        assert clean_directions(raw) == ["机器视觉", "深度学习"]

    def test_html_tags_removed(self):
        """HTML tag remnants are stripped."""
        raw = ["<b>机器视觉</b>", "<span>图像处理</span>"]
        assert clean_directions(raw) == ["机器视觉", "图像处理"]

    def test_whitespace_only_items_dropped(self):
        """Whitespace-only items are dropped."""
        raw = ["", "  ", "\t", "机器视觉"]
        assert clean_directions(raw) == ["机器视觉"]

    def test_mixed_junk_and_valid(self):
        """Mix of valid and junk items — only valid ones survive."""
        raw = [
            "机器视觉",
            "微流控 主讲本科课程",
            "图像处理、模式识别",
            "2012-2017 博士",
            "这是一段非常非常长的文字，它描述的不是研究方向而是某个教授的个人经历和背景信息",
            "深度学习",
        ]
        result = clean_directions(raw)
        assert result == ["机器视觉", "微流控", "图像处理", "模式识别", "深度学习"]

    def test_sentinel_at_start_drops_item(self):
        """If sentinel is at the very start, nothing remains → dropped."""
        raw = ["主讲课程：传感器技术"]
        assert clean_directions(raw) == []

    def test_multiple_sentinels(self):
        """First sentinel wins truncation."""
        raw = ["智能控制 教学改革 课程建设"]
        result = clean_directions(raw)
        assert result == ["智能控制"]

    def test_exactly_30_chars_kept(self):
        """Item exactly 30 characters long is kept."""
        item = "a" * 30
        assert clean_directions([item]) == [item]

    def test_31_chars_dropped(self):
        """Item 31 characters long is dropped."""
        item = "a" * 31
        assert clean_directions([item]) == []
