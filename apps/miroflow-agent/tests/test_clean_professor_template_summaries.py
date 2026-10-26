"""Source-side template cleanup: sentence removal, idempotence, record safety."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "clean_professor_template_summaries.py"
)
_spec = importlib.util.spec_from_file_location("clean_professor_template_summaries", _SCRIPT)
assert _spec and _spec.loader
cleaner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cleaner
_spec.loader.exec_module(cleaner)

PAD = "该教授在深圳科创领域有持续贡献。"


def test_strip_padding_removes_only_padding() -> None:
    text = f"王伟研究机器人控制。{PAD}研究成果具有重要学术价值。他在南科大任教。"

    assert cleaner.strip_padding(text) == "王伟研究机器人控制。他在南科大任教。"


def test_strip_padding_is_idempotent() -> None:
    text = f"王伟研究机器人控制。{PAD}"

    once = cleaner.strip_padding(text)

    assert cleaner.strip_padding(once) == once


def test_clean_record_only_touches_the_summary() -> None:
    record = {
        "name": "王伟",
        "email": "w@x.edu",
        "profile_summary": f"王伟研究机器人控制。{PAD}{PAD}",
    }

    updated, changed = cleaner.clean_record(record)

    assert changed is True
    assert updated["profile_summary"] == "王伟研究机器人控制。"
    assert updated["name"] == "王伟" and updated["email"] == "w@x.edu"
    assert record["profile_summary"].endswith(PAD)  # original untouched


def test_clean_record_ignores_records_without_padding() -> None:
    record = {"name": "李静", "profile_summary": "李静研究光学。"}

    updated, changed = cleaner.clean_record(record)

    assert changed is False
    assert updated is record


def test_main_writes_a_new_file_with_the_same_rows(tmp_path: Path) -> None:
    source = tmp_path / "in.source"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {"name": "王伟", "profile_summary": f"王伟研究机器人。{PAD}"},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"name": "李静", "profile_summary": "李静研究光学。"},
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.source"

    assert cleaner.main(["--source", str(source), "--out", str(out)]) == 0

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["profile_summary"] == "王伟研究机器人。"
    assert rows[1]["profile_summary"] == "李静研究光学。"
    assert source.read_text().count(PAD) == 1  # original untouched
