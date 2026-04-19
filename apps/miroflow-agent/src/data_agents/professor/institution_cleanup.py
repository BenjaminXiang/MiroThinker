# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Institution-field scraper-pollution helpers (Round 7.18c).

Some scraper runs glued a professor's personal name to their institution,
producing primary affiliations like:

    "中山大学（深圳） 陈伟津"
    "香港中文大学（深圳） Jianwei Huang"

and — on the same person — created a second professor row with
institution="UNKNOWN_INSTITUTION" containing the rest of the enrichment
data. Downstream this shows up in the dashboard institution dropdown as
"中山大学（深圳） 陈伟津 (1)" and inflates the unique professor count.

This module provides the narrow utilities the cleanup script uses:

* `strip_trailing_person_name` — remove a " <person name>" suffix that
  was never part of the institution (Chinese 2-5 chars or "Capitalized
  Capitalized" English names).
"""

from __future__ import annotations

import re

# Known Shenzhen primary-institution prefixes. We only strip a trailing name
# when the prefix BEFORE the trailing name matches one of these exactly —
# this prevents false-positives on institution names that happen to end
# with a 2-4 char dept word ("生态学院", "信息学部", "戴维斯分校").
_KNOWN_SZ_PRIMARY_INSTITUTIONS = frozenset(
    {
        "中山大学（深圳）",
        "香港中文大学（深圳）",
        "清华大学深圳国际研究生院",
        "清华大学深圳研究生院",
        "北京大学深圳研究生院",
        "哈尔滨工业大学（深圳）",
        "深圳技术大学",
        "深圳理工大学",
        "南方科技大学",
        "深圳大学",
        "中国科学院深圳先进技术研究院",
    }
)

# Trailing "<whitespace><name>" pattern. We only match 2-4 chars (CN) or
# 2-3 tokens (EN) to keep the regex anchored to human-name shapes; we then
# verify the prefix is a known institution before stripping.
_TRAILING_CN_NAME_RE = re.compile(r"^(.+?)\s+([\u4e00-\u9fff]{2,4})\s*$")
_TRAILING_EN_NAME_RE = re.compile(
    r"^(.+?)\s+([A-Z][a-z]+(?:-[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?){1,2})\s*$"
)

# Suffix tokens that are CLEARLY department/lab names, not personal names.
# If the captured suffix contains any of these, don't strip.
_DEPT_SUFFIX_MARKERS = (
    "学院",
    "学部",
    "学系",
    "学科",
    "系",
    "部",
    "所",
    "室",
    "组",
    "中心",
    "实验室",
    "分校",
    "Lab",
    "Department",
    "Dept",
    "School",
    "College",
    "Institute",
    "Center",
    "Centre",
    "Group",
)

# Chinese characters that a suffix ending in one of these likely indicates a
# department/organization (e.g. "数信院" for 数据信息学院). Personal names
# almost never end with these characters.
_CN_DEPT_SUFFIX_CHARS = ("院", "系", "所", "室", "组", "校", "苑", "园")


def strip_trailing_person_name(institution: str | None) -> str | None:
    """Return *institution* with a trailing personal-name suffix stripped,
    but ONLY when the prefix matches a known Shenzhen primary institution.

    This is a narrow fix for a scraper bug that produces values like
    "中山大学（深圳） 陈伟津" and "香港中文大学（深圳） Jianwei Huang".
    It deliberately does NOT attempt to split arbitrary "<inst> <dept>"
    strings because those ARE legitimate concatenations (e.g.
    "清华大学深圳研究生院 信息学部").

    Returns the input unchanged when no known-institution + trailing-name
    pattern is detected. `None` in → `None` out.
    """
    if institution is None:
        return None
    if not institution.strip():
        return institution
    for regex in (_TRAILING_CN_NAME_RE, _TRAILING_EN_NAME_RE):
        match = regex.match(institution)
        if not match:
            continue
        prefix = match.group(1).strip()
        suffix = match.group(2).strip()
        if prefix not in _KNOWN_SZ_PRIMARY_INSTITUTIONS:
            continue
        if any(marker in suffix for marker in _DEPT_SUFFIX_MARKERS):
            continue
        if suffix and suffix[-1] in _CN_DEPT_SUFFIX_CHARS:
            continue
        return prefix
    return institution
