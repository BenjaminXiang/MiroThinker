#!/usr/bin/env python3
"""Gate high-risk behavior edits behind an OpenSpec verification contract."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SENSITIVE_EXACT = {
    "apps/admin-console/backend/api/chat.py",
    "apps/admin-console/backend/services/chat_context.py",
}

SENSITIVE_PREFIXES = (
    "apps/miroflow-agent/src/core/",
    "apps/miroflow-agent/src/llm/",
    "apps/miroflow-agent/src/data_agents/service/",
    "apps/miroflow-agent/src/data_agents/providers/",
)

SENSITIVE_REGEXES = (
    re.compile(r"^apps/miroflow-agent/src/data_agents/[^/]+/.*(llm|prompt|routing|policy|memory).*\.py$"),
    re.compile(r"^apps/miroflow-agent/src/data_agents/[^/]+/(vectorizer|quality_gate|summary_generator)\.py$"),
)

PROCESS_PREFIXES = (
    ".agents/",
    ".github/",
    "docs/",
    "openspec/",
    "scripts/hooks/",
)

PROCESS_EXACT = {
    "AGENTS.md",
    "CLAUDE.md",
    "openspec/config.yaml",
}

VALID_CHANGE_TYPES = {
    "deterministic_module",
    "tool_contract",
    "data_contract_or_storage",
    "agentic_rag_or_chat_behavior",
    "agent_behavior_or_policy",
    "systemic_or_recurring_defect",
    "badcase_regression",
    "refactor_behavior_preserving",
}

VALID_MODES = {
    "full_tdd_allowed",
    "contract_first",
    "eval_first_required",
    "trace_debug_required",
    "diagnosis_first_required",
    "baseline_required",
}

REQUIRED_SECTIONS = (
    "## Change",
    "## Change Type",
    "## Superpowers Mode",
    "## RED Artifact",
    "## Oracle Strength",
    "## Diagnosis / Anti-Overfit Check",
    "## Context / Dependency Surface",
    "## Mock Policy",
    "## GREEN Criteria",
    "## Verification Plan",
)

REQUIRED_FIELDS = {
    "## Change": ("Change ID", "OpenSpec path", "Run workspace"),
    "## RED Artifact": ("Type", "Path", "Expected failing reason", "Behavior class covered"),
    "## Oracle Strength": (
        "Observable behavior checked",
        "Why this is stronger than a single string, DOM node, snapshot, or visible example",
        "For web/UI changes, browser/API/state workflow to verify",
        "For LLM/agentic changes, scenario/eval/trace contract to verify",
    ),
    "## Diagnosis / Anti-Overfit Check": (
        "Root-cause hypothesis",
        "Sibling patterns searched",
        "Why this RED covers a behavior class rather than one visible example",
        "Why the implementation cannot pass by hardcoding or bypassing the case",
    ),
    "## Context / Dependency Surface": (
        "Source OpenSpec requirement(s)",
        "Legacy/source-of-truth docs consulted",
        "Affected modules",
        "Existing tests/evals likely affected",
        "Regression surface",
        "External/provider/browser/storage dependencies",
    ),
    "## Mock Policy": (
        "Mocks used",
        "Behavior not mocked away",
        "Complementary real interaction / contract / trace / browser check",
    ),
    "## Verification Plan": (
        "RED command",
        "Focused GREEN command",
        "Regression command",
        "Browser/API/state workflow command",
        "Real interaction / contract / trace command",
        "OpenSpec validation command",
    ),
}

PLACEHOLDER_VALUES = {
    "",
    "todo",
    "tbd",
    "fixme",
    "n/a?",
    "unknown",
}


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def repo_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return Path(out)
    except Exception:
        return Path.cwd()


def relpath(path: str, root: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix().lstrip("./")


def is_process_path(path: str) -> bool:
    return path in PROCESS_EXACT or any(path.startswith(prefix) for prefix in PROCESS_PREFIXES)


def is_sensitive_path(path: str) -> bool:
    if is_process_path(path):
        return False
    if path in SENSITIVE_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in SENSITIVE_PREFIXES):
        return True
    return any(pattern.match(path) for pattern in SENSITIVE_REGEXES)


def active_changes(root: Path) -> list[str]:
    try:
        raw = subprocess.check_output(
            ["openspec", "list", "--json"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item["name"] for item in data.get("changes", []) if item.get("name")]


def selected_change(root: Path) -> str:
    explicit = os.environ.get("OPENSPEC_CHANGE_ID") or os.environ.get("OPEN_SPEC_CHANGE_ID")
    if explicit:
        return explicit

    changes = active_changes(root)
    if len(changes) == 1:
        return changes[0]
    if not changes:
        deny(
            "OpenSpec/Superpowers gate failed: behavior-sensitive edit without an active OpenSpec change. "
            "Create a change and verification contract first."
        )
    deny(
        "OpenSpec/Superpowers gate failed: multiple active OpenSpec changes. "
        "Set OPENSPEC_CHANGE_ID before editing behavior-sensitive paths.\n"
        f"Active changes: {', '.join(changes)}"
    )
    raise AssertionError("unreachable")


def contract_path(root: Path, change: str) -> Path:
    return root / ".agents" / "runs" / change / "verification-contract.md"


def section_text(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        return ""
    next_section = text.find("\n## ", start + len(marker))
    if next_section < 0:
        return text[start:]
    return text[start:next_section]


def selected_option(text: str, marker: str, valid: set[str], path: Path) -> str:
    body = section_text(text, marker)
    options = [
        match.group(1)
        for match in re.finditer(r"^\s*-\s+`([^`]+)`\s*$", body, flags=re.MULTILINE)
        if match.group(1) in valid
    ]
    if len(options) != 1:
        deny(
            "OpenSpec/Superpowers gate failed: verification contract must keep exactly one "
            f"option under {marker}.\n"
            f"Found: {', '.join(options) if options else 'none'}\nPath: {path}"
        )
    return options[0]


def field_value(text: str, marker: str, label: str) -> str | None:
    body = section_text(text, marker)
    pattern = rf"^\s*-\s+{re.escape(label)}:\s*(.*)$"
    match = re.search(pattern, body, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("`").lower()
    return (
        normalized in PLACEHOLDER_VALUES
        or normalized.startswith("<")
        or normalized.endswith("...")
        or normalized in {"not sure", "to be filled"}
    )


def validate_required_fields(text: str, path: Path) -> None:
    missing: list[str] = []
    for section, labels in REQUIRED_FIELDS.items():
        for label in labels:
            value = field_value(text, section, label)
            if value is None or is_placeholder(value):
                missing.append(f"{section} / {label}")
    if missing:
        deny(
            "OpenSpec/Superpowers gate failed: verification contract has empty or placeholder fields.\n"
            + "\n".join(f"- {item}" for item in missing)
            + f"\nPath: {path}"
        )


def validate_semantics(text: str, change_type: str, mode: str, path: Path) -> None:
    red_type = field_value(text, "## RED Artifact", "Type") or ""
    red_lower = red_type.lower()
    oracle = (field_value(text, "## Oracle Strength", "Observable behavior checked") or "").lower()
    mock_check = (
        field_value(text, "## Mock Policy", "Complementary real interaction / contract / trace / browser check")
        or ""
    ).lower()

    if change_type in {"agentic_rag_or_chat_behavior", "agent_behavior_or_policy", "badcase_regression"}:
        weak_types = {"unit test", "snapshot", "dom node", "exact string"}
        if red_lower in weak_types or "unit" in red_lower and "contract" not in red_lower:
            deny(
                "OpenSpec/Superpowers gate failed: agentic/chat/badcase changes cannot use unit-only RED.\n"
                f"RED Type: {red_type}\nPath: {path}"
            )
        if mode not in {"eval_first_required", "trace_debug_required", "diagnosis_first_required"}:
            deny(
                "OpenSpec/Superpowers gate failed: agentic/chat/badcase changes require eval, trace, "
                f"or diagnosis first mode.\nMode: {mode}\nPath: {path}"
            )

    if change_type == "systemic_or_recurring_defect" and mode != "diagnosis_first_required":
        deny(
            "OpenSpec/Superpowers gate failed: systemic or recurring defects require diagnosis_first_required.\n"
            f"Mode: {mode}\nPath: {path}"
        )

    if "snapshot" in oracle or "dom node only" in oracle or "single string" in oracle:
        deny(
            "OpenSpec/Superpowers gate failed: oracle description is explicitly weak.\n"
            f"Oracle: {oracle}\nPath: {path}"
        )

    mock_used = (field_value(text, "## Mock Policy", "Mocks used") or "").lower()
    if mock_used not in {"none", "no", "not applicable", "n/a"}:
        if mock_check in {"none", "no", "not applicable", "n/a"}:
            deny(
                "OpenSpec/Superpowers gate failed: mocks are used but no complementary real interaction "
                f"check is declared.\nPath: {path}"
            )


def validate_contract(path: Path) -> None:
    if not path.exists():
        deny(
            "OpenSpec/Superpowers gate failed: verification contract missing.\n"
            f"Expected: {path}\n"
            "Create it from .agents/runs/verification-contract.template.md and choose RED before editing."
        )
    text = path.read_text(encoding="utf-8")
    if "<change-id>" in text or "Choose one and delete the rest" in text:
        deny(
            "OpenSpec/Superpowers gate failed: verification contract still looks like an unfilled template.\n"
            f"Path: {path}"
        )
    for marker in REQUIRED_SECTIONS:
        if marker not in text:
            deny(
                "OpenSpec/Superpowers gate failed: verification contract is missing a required section.\n"
                f"Missing: {marker}\nPath: {path}"
            )
    change_type = selected_option(text, "## Change Type", VALID_CHANGE_TYPES, path)
    mode = selected_option(text, "## Superpowers Mode", VALID_MODES, path)
    validate_required_fields(text, path)
    validate_semantics(text, change_type, mode, path)


def paths_from_hook_payload(root: Path) -> list[str]:
    raw = sys.stdin.read()
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    tool_input = payload.get("tool_input") or payload.get("input") or {}
    paths: list[str] = []

    if isinstance(tool_input, dict):
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.append(value)

        edits = tool_input.get("edits")
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    value = edit.get("file_path") or edit.get("path")
                    if isinstance(value, str):
                        paths.append(value)

        for key in ("command", "cmd", "patch"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.extend(extract_paths_from_text(value))

    return sorted({relpath(path, root) for path in paths})


def extract_paths_from_text(text: str) -> Iterable[str]:
    for line in text.splitlines():
        match = re.match(r"\*\*\*\s+(?:Update|Add|Delete) File:\s+(.+)$", line.strip())
        if match:
            yield match.group(1).strip()


def paths_from_git_diff(root: Path) -> list[str]:
    paths: set[str] = set()
    commands = (
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"],
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"],
    )
    for cmd in commands:
        try:
            raw = subprocess.check_output(cmd, cwd=root, text=True, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        paths.update(line.strip() for line in raw.splitlines() if line.strip())
    return sorted(paths)


def main() -> None:
    root = repo_root()
    mode = sys.argv[1] if len(sys.argv) > 1 else "pretool"

    if mode == "contract":
        if len(sys.argv) != 3:
            deny("Usage: openspec_superpowers_gate.py contract <verification-contract.md>")
        validate_contract(Path(sys.argv[2]))
        return

    if mode == "diff":
        paths = paths_from_git_diff(root)
    else:
        paths = paths_from_hook_payload(root)

    sensitive = [path for path in paths if is_sensitive_path(path)]
    if not sensitive:
        return

    change = selected_change(root)
    path = contract_path(root, change)
    validate_contract(path)


if __name__ == "__main__":
    main()
