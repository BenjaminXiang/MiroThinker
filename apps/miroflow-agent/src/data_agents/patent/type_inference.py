from __future__ import annotations

import re


_KIND_CODE_TO_PATENT_TYPE = {
    "A": "发明",
    "B": "发明",
    "U": "实用新型",
    "Y": "实用新型",
    "S": "外观设计",
    "D": "外观设计",
}
_LEADING_DIGIT_TO_PATENT_TYPE = {
    "1": "发明",
    "2": "实用新型",
    "3": "外观设计",
    "8": "发明",
    "9": "实用新型",
}
_WHITESPACE_RE = re.compile(r"\s+")


def infer_patent_type(
    patent_number: object,
    *,
    current_type: str | None = None,
) -> str | None:
    if current_type is not None and str(current_type).strip():
        return current_type

    if patent_number is None:
        return None

    text = _WHITESPACE_RE.sub("", str(patent_number)).upper()
    if not text:
        return None

    kind_code = text[-1]
    if kind_code in _KIND_CODE_TO_PATENT_TYPE:
        return _KIND_CODE_TO_PATENT_TYPE[kind_code]

    numeric_portion = text[2:] if text.startswith("CN") else text
    if not numeric_portion or not numeric_portion[0].isdigit():
        return None

    return _LEADING_DIGIT_TO_PATENT_TYPE.get(numeric_portion[0])
