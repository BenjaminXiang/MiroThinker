from __future__ import annotations

import re

_PUBLICATIONS_HEADING_KEYWORDS = (
    "selected publications",
    "selected papers",
    "representative papers",
    "representative publications",
    "publications",
    "papers",
    "journal articles",
    "research output",
    "学术著作",
    "学术论文",
    "科研论文",
    "论文著作",
    "发表论文",
    "代表论文",
    "主要论文",
    "论著",
    "论文",
)

_PUBLICATIONS_HEADING_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(keyword) for keyword in _PUBLICATIONS_HEADING_KEYWORDS)
    + r")$",
    re.IGNORECASE,
)
