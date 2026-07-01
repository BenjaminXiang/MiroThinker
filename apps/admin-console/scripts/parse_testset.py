"""Parse docs/测试集答案.xlsx → tests/fixtures/test_cases.yaml.

The xlsx is the frozen human golden set (42 rows: 问题 / 答案 / 关键点). It is multi-turn:
rows are grouped under 问题N header rows; followup rows refer to prior turns (他/上述企业/这论文).
This parser skips header rows, groups followups, and auto-derives required/forbidden entities +
coref/refusal/disambiguation flags from 关键点. Uncertain derivations are flagged for a one-time
labeling pass; the parser does NOT trust heuristics for final GT.

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  UV_OFFLINE=1 uv run python scripts/parse_testset.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import openpyxl
import yaml

# Meta-phrases in 关键点 that are NOT entities (do not treat as required entities).
_META_PHRASES = (
    "需要在回答", "需要识别", "上下文识别", "获取知识库", "关联到知识库",
    "知识库获取", "获取数据库", "不能回答", "会搜索出", "不应该出现",
    "这里的答案是不准确",
)
_FORBIDDEN_RE = re.compile(r"不应该出现(.+?)(?:;|;|。|$)")
_NEED_MARKER_RE = re.compile(r"\s*需要(?:在回答(?:结果|中)?|出现)?\s*$")


def _split_entities(kp: str) -> list[str]:
    """Split 关键点 on Chinese/ASCII separators, strip whitespace."""
    parts = re.split(r"[；;,，、]", kp)
    return [p.strip() for p in parts if p.strip()]


_CITY_PREFIX_RE = re.compile(r"^(深圳|北京|上海|广州|杭州|南京|武汉|成都|西安|苏州|东莞)[市]?")
_LEGAL_SUFFIX_RE = re.compile(r"(股份有限公司|有限公司|责任公司|科技|集团|控股|公司|技术|有限)$")


def _normalize_core(name: str) -> str:
    """Strip city prefix + legal suffix -> short matchable core ('深圳市普渡科技股份有限公司' -> '普渡')."""
    s = _CITY_PREFIX_RE.sub("", name)
    prev = None
    while prev != s:
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    return s or name


def _derive_required(kp: str) -> list[str]:
    """Best-effort extract required entities from 关键点 as short matchable cores."""
    if not kp:
        return []
    out: list[str] = []
    for token in _split_entities(kp):
        token = _NEED_MARKER_RE.sub("", token)
        if not token or token.startswith(_META_PHRASES):
            continue
        out.append(_normalize_core(token))
    return out


def _derive_forbidden(kp: str) -> list[str]:
    """Extract forbidden entities (from '不应该出现X')."""
    if not kp:
        return []
    m = _FORBIDDEN_RE.search(kp)
    if not m:
        return []
    return [m.group(1).strip().rstrip("。;；")]


def _needs_coref(kp: str, query: str) -> bool:
    text = f"{kp} {query}"
    return any(t in text for t in ("上下文识别", "他指", "上述企业", "上述", "这论文", "这家公司"))


def _refusal_expected(kp: str) -> bool:
    return "不能回答" in (kp or "")


def _disambiguation(kp: str) -> bool:
    return "会搜索出" in (kp or "")


def _is_head_turn(cases: list[dict], group: str | None) -> bool:
    """A case is a head turn if no prior case in the same group exists."""
    return not any(c["turn_group"] == group for c in cases)


def parse_workbook(path: Path) -> list[dict]:
    """Parse the xlsx into a list of case dicts (no yaml write)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    cases: list[dict] = []
    current_group: str | None = None
    qid = 0
    for row in ws.iter_rows(values_only=True):
        q = (row[0] or "").strip() if len(row) > 0 else ""
        answer = (row[1] or "").strip() if len(row) > 1 else ""
        kp = (row[2] or "").strip() if len(row) > 2 else ""
        if not q:
            continue
        if re.fullmatch(r"问题\d+", q):
            current_group = q
            continue
        qid += 1
        cases.append({
            "qid": qid,
            "turn_group": current_group,
            "is_head_turn": _is_head_turn(cases, current_group),
            "query": q,
            "answer": answer,
            "key_point": kp,
            "required_entities": _derive_required(kp),
            "forbidden_entities": _derive_forbidden(kp),
            "coref_needs_label": _needs_coref(kp, q),
            "refusal_expected": _refusal_expected(kp),
            "disambiguation_expected": _disambiguation(kp),
        })
    return cases


def main() -> int:
    xlsx = Path(__file__).resolve().parents[3] / "docs" / "测试集答案.xlsx"
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    cases = parse_workbook(xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"cases": cases}, fh, allow_unicode=True, sort_keys=False)
    n_coref = sum(1 for c in cases if c["coref_needs_label"])
    n_req = sum(1 for c in cases if c["required_entities"])
    print(f"parsed {len(cases)} cases -> {out}")
    print(f"  with required_entities: {n_req}")
    print(f"  coref_needs_label (one-time labeling pass): {n_coref}")
    print("NOTE: auto-derived required/forbidden are best-effort; review the flagged coref cases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
