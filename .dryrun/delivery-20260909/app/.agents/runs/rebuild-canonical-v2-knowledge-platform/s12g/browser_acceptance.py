# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""S12G synchronous browser acceptance runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


VIEWPORT_MATRIX = (
    (320, 568),
    (360, 640),
    (360, 800),
    (412, 915),
    (375, 667),
    (390, 844),
    (430, 932),
    (667, 375),
    (844, 390),
    (768, 1024),
    (1024, 768),
    (1280, 720),
    (1440, 900),
)

DEFECT_ORDER = (
    "DOCUMENT_OVERFLOW",
    "TARGET_LT_44",
    "REQUIRED_CONTROL_NOT_ACTIONABLE",
    "OPTION_FOLLOWUP_CONTRACT_FAILED",
    "DETACHED_SCROLL_DRIFT",
    "ROTATION_STALE_GEOMETRY",
    "VIEWPORT_RUNTIME_FAILURE",
)
VISIBLE_TARGET_SELECTORS = (
    "#chat-input",
    "#chat-submit",
    "#demo-toggle",
    ".demo-chip",
    ".process-stop",
    ".back-to-latest",
    ".evidence-summary",
    ".process-summary summary",
    ".option-button",
)
REQUIRED_ACTIONABLE_CONTROLS = {
    "landing": ("#chat-input", "#chat-submit", ".demo-chip"),
    "conversation": ("#chat-input", "#chat-submit", "#demo-toggle"),
    "demo-expanded": (
        "#chat-input",
        "#chat-submit",
        "#demo-toggle",
        ".demo-chip",
    ),
}
INTERNAL_MARKER_PATTERNS = (
    ("professor_internal_id", r"PROF-[0-9A-F]{12}"),
    ("company_internal_id", r"COMP-[0-9a-f]{12}"),
    (
        "canonical_internal_id",
        r"(?:company|professor|paper|patent)-c-[0-9a-f]{24}",
    ),
    ("web_object", r"web-object:"),
    ("web_handle", r"web-handle:"),
    ("current_web_source_nature", r"source_nature=current_web"),
)
SAFE_SSE_EVENT_NAMES = frozenset(
    {
        "stage",
        "plan_done",
        "retrieval_done",
        "answer_chunk",
        "answer",
        "done",
        "error",
    }
)
SSE_WIRE_STRUCTURE_MARKER_KIND = "sse_structure_field"
SSE_WIRE_STRUCTURAL_TOKENS = frozenset(
    {
        "answer_style",
        "answer_text",
        "candidates",
        "citation_map",
        "citations",
        "clarification",
        "default_id",
        "detail",
        "domain",
        "domains",
        "evidence",
        "hint",
        "id",
        "internal_stage",
        "label",
        "lane",
        "lanes",
        "name",
        "omitted",
        "options",
        "prompt",
        "query",
        "query_type",
        "release_id",
        "row_key",
        "snapshot_id",
        "source_authority",
        "source_nature",
        "status",
        "structured_payload",
        "suggested_followups",
        "text",
        "trace",
        "type",
        "url",
        "views",
    }
)
SSE_WIRE_STRUCTURAL_PATTERN = re.compile(
    rf"(?<![0-9A-Za-z_])(?:{'|'.join(sorted(map(re.escape, SSE_WIRE_STRUCTURAL_TOKENS), key=len, reverse=True))})(?![0-9A-Za-z_])",
    flags=re.IGNORECASE,
)
DOM_MARKER_PROBE_SCRIPT = """(patterns) => {
  window.__s12gDomMarkerProbe?.observer?.disconnect();
  const messages = document.getElementById("messages");
  if (!messages) return false;

  const state = { latches: [], mutationIndex: 0, pending: [] };
  const valuesForNode = (node) => {
    const values = [];
    if (!node) return values;
    if (node.nodeType === Node.TEXT_NODE) {
      values.push(node.nodeValue || "");
      return values;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return values;
    values.push(node.textContent || "");
    const collectAttributes = (element) => {
      for (const attribute of element.attributes) {
        values.push(attribute.name, attribute.value);
      }
    };
    collectAttributes(node);
    node.querySelectorAll("*").forEach(collectAttributes);
    return values;
  };
  const latchValues = (values, mutationIndex) => {
    for (const marker of patterns) {
      const expression = new RegExp(marker.pattern, "i");
      const matchedValue = values.find(
        (value) => typeof value === "string" && expression.test(value),
      );
      if (matchedValue === undefined) continue;
      const pending = crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(matchedValue),
      ).then(
        (buffer) => {
          const sha256 = [...new Uint8Array(buffer)]
            .map((byte) => byte.toString(16).padStart(2, "0"))
            .join("");
          state.latches.push({
            marker_kind: marker.kind,
            mutation_index: mutationIndex,
            sha256,
          });
        },
        () => {
          state.latches.push({
            marker_kind: marker.kind,
            mutation_index: mutationIndex,
            sha256: null,
          });
        },
      );
      state.pending.push(pending);
    }
  };
  const processRecords = (records) => {
    for (const record of records) {
      const mutationIndex = state.mutationIndex;
      state.mutationIndex += 1;
      const values = [messages.textContent || ""];
      for (const node of record.addedNodes || []) {
        values.push(...valuesForNode(node));
      }
      for (const node of record.removedNodes || []) {
        values.push(...valuesForNode(node));
      }
      if (typeof record.attributeName === "string") {
        values.push(record.attributeName);
      }
      if (typeof record.oldValue === "string") values.push(record.oldValue);
      values.push(...valuesForNode(record.target));
      latchValues(values, mutationIndex);
    }
  };
  const observer = new MutationObserver(processRecords);
  const observeOptions = {
    childList: true,
    subtree: true,
    characterData: true,
    characterDataOldValue: true,
    attributes: true,
    attributeOldValue: true,
  };
  observer.observe(messages, observeOptions);
  const initialMutationIndex = state.mutationIndex;
  state.mutationIndex += 1;
  latchValues(valuesForNode(messages), initialMutationIndex);
  state.observer = observer;
  state.observeOptions = observeOptions;
  state.processRecords = processRecords;
  window.__s12gDomMarkerProbe = state;
  return true;
}"""
LONG_CONTENT_VIEWPORTS = {(320, 568), (667, 375)}
SSE_VIEWPORT = (390, 844)
NAVIGATION_TIMEOUT_MS = 30_000
SSE_TIMEOUT_MS = 180_000
GEOMETRY_TOLERANCE_PX = 1.5


class AcceptanceRuntimeError(RuntimeError):
    """A runner failure with a safe, non-payload-bearing public message."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _remaining_timeout_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1_000)
    if remaining <= 0:
        raise AcceptanceRuntimeError(
            "SSE_DEADLINE_EXCEEDED",
            "The SSE acceptance round exceeded its single deadline.",
        )
    return remaining


def _fingerprint(value: str) -> dict[str, str | int]:
    encoded = value.encode("utf-8")
    return {
        "length": len(value),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _normalize_markdown_visible_text(value: str) -> str:
    visible_lines: list[str] = []
    in_fence = False
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            continue
        if not in_fence:
            line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
            line = re.sub(r"^\s*(?:[-*+] |\d+[.、)]\s+)", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"__(.+?)__", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        visible_lines.append(line)
    return re.sub(r"\s+", " ", " ".join(visible_lines)).strip()


def _evaluate_incremental_prefixes(
    expected: list[dict[str, Any]],
    observed: list[dict[str, Any]],
) -> dict[str, Any]:
    def key(value: Any) -> tuple[int, str] | None:
        if not isinstance(value, dict):
            return None
        length = value.get("length")
        sha256 = value.get("sha256")
        if (
            not isinstance(length, int)
            or isinstance(length, bool)
            or length < 0
            or not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
        ):
            return None
        return length, sha256

    expected_keys = [key(value) for value in expected]
    observed_keys = [key(value) for value in observed]
    shapes_valid = all(value is not None for value in expected_keys + observed_keys)
    clean_expected = [value for value in expected_keys if value is not None]
    clean_observed = [value for value in observed_keys if value is not None]
    deduped_expected = [
        value
        for index, value in enumerate(clean_expected)
        if index == 0 or value != clean_expected[index - 1]
    ]
    deduped_observed = [
        value
        for index, value in enumerate(clean_observed)
        if index == 0 or value != clean_observed[index - 1]
    ]

    all_expected = all(value in deduped_expected for value in deduped_observed)
    ordered = True
    cursor = 0
    for value in deduped_observed:
        try:
            cursor = deduped_expected.index(value, cursor) + 1
        except ValueError:
            ordered = False
            break
    terminal_matches = bool(
        deduped_expected
        and deduped_observed
        and deduped_observed[-1] == deduped_expected[-1]
    )
    checks = {
        "fingerprint_shapes_valid": shapes_valid,
        "expected_prefixes_present": bool(deduped_expected),
        "observed_prefixes_present": bool(deduped_observed),
        "all_observed_prefixes_expected": all_expected,
        "observed_prefixes_ordered": ordered,
        "terminal_prefix_matches": terminal_matches,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "expected_count": len(deduped_expected),
        "observed_count": len(deduped_observed),
        "checks": checks,
    }


class _SSEDuplicateJSONKeyError(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _SSEDuplicateJSONKeyError
        value[key] = item
    return value


def _sse_wire_marker_latches(material: str) -> list[dict[str, str]]:
    if not material:
        return []
    sha256 = hashlib.sha256(material.encode("utf-8")).hexdigest()
    latches = [
        {"marker_kind": marker_kind, "sha256": sha256}
        for marker_kind, pattern in INTERNAL_MARKER_PATTERNS
        if re.search(pattern, material, flags=re.IGNORECASE)
    ]
    if SSE_WIRE_STRUCTURAL_PATTERN.search(material):
        latches.append(
            {
                "marker_kind": SSE_WIRE_STRUCTURE_MARKER_KIND,
                "sha256": sha256,
            }
        )
    return latches


def _parse_sse_body(raw_body: bytes) -> list[dict[str, Any]]:
    try:
        text = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AcceptanceRuntimeError(
            "SSE_BODY_DECODE_FAILED",
            "The stream response body is not valid UTF-8.",
        ) from error

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    events: list[dict[str, Any]] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        event_values: list[str] = []
        data_lines: list[str] = []
        discarded_parts: list[str] = []
        for line in block:
            if line.startswith(":"):
                discarded_parts.append(line[1:])
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "event":
                event_values.append(value)
            elif field == "data":
                data_lines.append(value)
            elif field in {"id", "retry"}:
                discarded_parts.append(value)
            else:
                discarded_parts.extend((field, value) if separator else (line,))
        event_name = event_values[-1] if event_values else "message"
        discarded_parts.extend(event_values[:-1])
        if not data_lines and event_values:
            discarded_parts.append(event_name)
        wire_latches = _sse_wire_marker_latches("\n".join(discarded_parts))
        block.clear()
        if not data_lines:
            if wire_latches:
                events.append(
                    {
                        "name": "unknown",
                        "data": {},
                        "raw_data": "",
                        "wire_latches": wire_latches,
                    }
                )
            return

        raw_data = "\n".join(data_lines)
        try:
            data = json.loads(
                raw_data,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except _SSEDuplicateJSONKeyError as error:
            raise AcceptanceRuntimeError(
                "SSE_JSON_DUPLICATE_KEY",
                "A stream event contains a duplicate JSON object key.",
            ) from error
        except json.JSONDecodeError as error:
            raise AcceptanceRuntimeError(
                "SSE_JSON_DECODE_FAILED",
                "A stream event contains invalid JSON.",
            ) from error
        if not isinstance(data, dict):
            raise AcceptanceRuntimeError(
                "SSE_DATA_NOT_OBJECT",
                "A stream event JSON value is not an object.",
            )
        event = {"name": event_name, "data": data, "raw_data": raw_data}
        if wire_latches:
            event["wire_latches"] = wire_latches
        events.append(event)

    for line in text.split("\n"):
        if line == "":
            flush()
        else:
            block.append(line)
    flush()
    return events


def _nested_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            nested for item in value.values() for nested in _nested_string_values(item)
        ]
    if isinstance(value, list):
        return [nested for item in value for nested in _nested_string_values(item)]
    return []


def _sse_schema_violation(
    *,
    event_index: int,
    event: str,
    category: str,
    field_path: str,
) -> dict[str, Any]:
    return {
        "event_index": event_index,
        "event": event if event in SAFE_SSE_EVENT_NAMES else "unknown",
        "category": category,
        "field_path_sha256": hashlib.sha256(field_path.encode("utf-8")).hexdigest(),
    }


def _append_sse_schema_violation(
    violations: list[dict[str, Any]],
    *,
    event_index: int,
    event: str,
    category: str,
    field_path: str,
) -> None:
    violations.append(
        _sse_schema_violation(
            event_index=event_index,
            event=event,
            category=category,
            field_path=field_path,
        )
    )


def _validate_sse_exact_object(
    value: Any,
    expected_keys: tuple[str, ...],
    *,
    event_index: int,
    event: str,
    field_path: str,
    violations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=field_path,
        )
        return None
    for key in expected_keys:
        if key not in value:
            _append_sse_schema_violation(
                violations,
                event_index=event_index,
                event=event,
                category="missing_field",
                field_path=f"{field_path}.{key}",
            )
    for key in sorted(set(value).difference(expected_keys)):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="unknown_field",
            field_path=f"{field_path}.{key}",
        )
    return value


def _validate_sse_string(
    value: Any,
    *,
    event_index: int,
    event: str,
    field_path: str,
    violations: list[dict[str, Any]],
    allowed: frozenset[str] | None = None,
) -> None:
    if not isinstance(value, str):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=field_path,
        )
    elif allowed is not None and value not in allowed:
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_value",
            field_path=field_path,
        )


def _validate_sse_integer(
    value: Any,
    *,
    event_index: int,
    event: str,
    field_path: str,
    violations: list[dict[str, Any]],
    nonnegative: bool = False,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=field_path,
        )
    elif nonnegative and value < 0:
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_value",
            field_path=field_path,
        )


def _validate_sse_string_list(
    value: Any,
    *,
    event_index: int,
    event: str,
    field_path: str,
    violations: list[dict[str, Any]],
    max_length: int | None = None,
) -> list[Any] | None:
    if not isinstance(value, list):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=field_path,
        )
        return None
    if max_length is not None and len(value) > max_length:
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_value",
            field_path=field_path,
        )
    for item_index, item in enumerate(value):
        _validate_sse_string(
            item,
            event_index=event_index,
            event=event,
            field_path=f"{field_path}[{item_index}]",
            violations=violations,
        )
    return value


def _validate_sse_answer(
    data: dict[str, Any],
    *,
    event_index: int,
    violations: list[dict[str, Any]],
) -> None:
    event = "answer"
    field_path = "answer.data"
    payload = _validate_sse_exact_object(
        data,
        (
            "query",
            "query_type",
            "answer_text",
            "citations",
            "evidence",
            "clarification",
            "structured_payload",
            "answer_style",
            "citation_map",
            "suggested_followups",
        ),
        event_index=event_index,
        event=event,
        field_path=field_path,
        violations=violations,
    )
    if payload is None:
        return
    for key in ("query", "query_type", "answer_text"):
        if key in payload:
            _validate_sse_string(
                payload[key],
                event_index=event_index,
                event=event,
                field_path=f"{field_path}.{key}",
                violations=violations,
            )

    citation_ids: list[str] = []
    citations = payload.get("citations")
    if not isinstance(citations, list):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=f"{field_path}.citations",
        )
    else:
        for citation_index, citation in enumerate(citations):
            citation_path = f"{field_path}.citations[{citation_index}]"
            citation_payload = _validate_sse_exact_object(
                citation,
                ("type", "id", "label", "url"),
                event_index=event_index,
                event=event,
                field_path=citation_path,
                violations=violations,
            )
            if citation_payload is None:
                continue
            if "type" in citation_payload:
                _validate_sse_string(
                    citation_payload["type"],
                    event_index=event_index,
                    event=event,
                    field_path=f"{citation_path}.type",
                    violations=violations,
                    allowed=frozenset({"professor", "paper", "patent", "company"}),
                )
            for key in ("id", "label"):
                if key in citation_payload:
                    _validate_sse_string(
                        citation_payload[key],
                        event_index=event_index,
                        event=event,
                        field_path=f"{citation_path}.{key}",
                        violations=violations,
                    )
            citation_id = citation_payload.get("id")
            if isinstance(citation_id, str):
                citation_ids.append(citation_id)
            url = citation_payload.get("url")
            if "url" in citation_payload and url is not None:
                _validate_sse_string(
                    url,
                    event_index=event_index,
                    event=event,
                    field_path=f"{citation_path}.url",
                    violations=violations,
                )

    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=f"{field_path}.evidence",
        )
    else:
        for evidence_index, item in enumerate(evidence):
            item_path = f"{field_path}.evidence[{evidence_index}]"
            item_payload = _validate_sse_exact_object(
                item,
                (),
                event_index=event_index,
                event=event,
                field_path=item_path,
                violations=violations,
            )
            if item_payload == {}:
                _append_sse_schema_violation(
                    violations,
                    event_index=event_index,
                    event=event,
                    category="invalid_value",
                    field_path=item_path,
                )

    clarification = payload.get("clarification")
    if clarification is not None:
        clarification_path = f"{field_path}.clarification"
        clarification_payload = _validate_sse_exact_object(
            clarification,
            ("prompt", "options", "default_id", "omitted"),
            event_index=event_index,
            event=event,
            field_path=clarification_path,
            violations=violations,
        )
        if clarification_payload is not None:
            for key in ("prompt", "default_id"):
                if key in clarification_payload:
                    _validate_sse_string(
                        clarification_payload[key],
                        event_index=event_index,
                        event=event,
                        field_path=f"{clarification_path}.{key}",
                        violations=violations,
                    )
            options = clarification_payload.get("options")
            if not isinstance(options, list):
                _append_sse_schema_violation(
                    violations,
                    event_index=event_index,
                    event=event,
                    category="invalid_type",
                    field_path=f"{clarification_path}.options",
                )
            else:
                for option_index, option in enumerate(options):
                    option_path = f"{clarification_path}.options[{option_index}]"
                    option_payload = _validate_sse_exact_object(
                        option,
                        ("id", "domain", "label", "hint"),
                        event_index=event_index,
                        event=event,
                        field_path=option_path,
                        violations=violations,
                    )
                    if option_payload is None:
                        continue
                    for key in ("id", "label", "hint"):
                        if key in option_payload:
                            _validate_sse_string(
                                option_payload[key],
                                event_index=event_index,
                                event=event,
                                field_path=f"{option_path}.{key}",
                                violations=violations,
                            )
                    if "domain" in option_payload:
                        _validate_sse_string(
                            option_payload["domain"],
                            event_index=event_index,
                            event=event,
                            field_path=f"{option_path}.domain",
                            violations=violations,
                            allowed=frozenset(
                                {"professor", "paper", "company", "patent"}
                            ),
                        )
            if "omitted" in clarification_payload:
                _validate_sse_integer(
                    clarification_payload["omitted"],
                    event_index=event_index,
                    event=event,
                    field_path=f"{clarification_path}.omitted",
                    violations=violations,
                    nonnegative=True,
                )

    structured_payload = payload.get("structured_payload")
    _validate_sse_exact_object(
        structured_payload,
        (),
        event_index=event_index,
        event=event,
        field_path=f"{field_path}.structured_payload",
        violations=violations,
    )

    if "answer_style" in payload:
        _validate_sse_string(
            payload["answer_style"],
            event_index=event_index,
            event=event,
            field_path=f"{field_path}.answer_style",
            violations=violations,
            allowed=frozenset({"template", "llm_synthesized"}),
        )

    citation_map = payload.get("citation_map")
    if isinstance(citation_map, dict):
        expected_citation_map = {
            str(index): citation_id
            for index, citation_id in enumerate(citation_ids, start=1)
        }
        map_payload = _validate_sse_exact_object(
            citation_map,
            tuple(expected_citation_map),
            event_index=event_index,
            event=event,
            field_path=f"{field_path}.citation_map",
            violations=violations,
        )
        if map_payload is not None:
            for key, expected_id in expected_citation_map.items():
                if key not in map_payload:
                    continue
                value = map_payload[key]
                _validate_sse_string(
                    value,
                    event_index=event_index,
                    event=event,
                    field_path=f"{field_path}.citation_map.{key}",
                    violations=violations,
                )
                if isinstance(value, str) and value != expected_id:
                    _append_sse_schema_violation(
                        violations,
                        event_index=event_index,
                        event=event,
                        category="invalid_value",
                        field_path=f"{field_path}.citation_map.{key}",
                    )
    else:
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="invalid_type",
            field_path=f"{field_path}.citation_map",
        )

    _validate_sse_string_list(
        payload.get("suggested_followups"),
        event_index=event_index,
        event=event,
        field_path=f"{field_path}.suggested_followups",
        violations=violations,
        max_length=5,
    )


def _sse_event_schema_violations(
    *,
    event_index: int,
    event: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    field_path = f"{event}.data"
    if event == "unknown":
        _append_sse_schema_violation(
            violations,
            event_index=event_index,
            event=event,
            category="unknown_event",
            field_path="event.name",
        )
        return violations
    if event == "answer":
        _validate_sse_answer(data, event_index=event_index, violations=violations)
        return violations

    expected_keys = {
        "stage": ("name",),
        "plan_done": ("lanes", "domains", "views"),
        "retrieval_done": ("lanes",),
        "answer_chunk": ("text",),
        "done": (),
        "error": ("detail",),
    }[event]
    payload = _validate_sse_exact_object(
        data,
        expected_keys,
        event_index=event_index,
        event=event,
        field_path=field_path,
        violations=violations,
    )
    if payload is None:
        return violations
    if event == "stage" and "name" in payload:
        _validate_sse_string(
            payload["name"],
            event_index=event_index,
            event=event,
            field_path=f"{field_path}.name",
            violations=violations,
            allowed=frozenset({"planning", "retrieval", "synthesis"}),
        )
    elif event == "plan_done":
        for key in ("lanes", "domains", "views"):
            if key in payload:
                _validate_sse_string_list(
                    payload[key],
                    event_index=event_index,
                    event=event,
                    field_path=f"{field_path}.{key}",
                    violations=violations,
                )
    elif event == "retrieval_done" and "lanes" in payload:
        lanes = payload["lanes"]
        if not isinstance(lanes, list):
            _append_sse_schema_violation(
                violations,
                event_index=event_index,
                event=event,
                category="invalid_type",
                field_path=f"{field_path}.lanes",
            )
        else:
            for lane_index, lane in enumerate(lanes):
                lane_path = f"{field_path}.lanes[{lane_index}]"
                lane_payload = _validate_sse_exact_object(
                    lane,
                    ("lane", "status", "candidates"),
                    event_index=event_index,
                    event=event,
                    field_path=lane_path,
                    violations=violations,
                )
                if lane_payload is None:
                    continue
                for key in ("lane", "status"):
                    if key in lane_payload:
                        _validate_sse_string(
                            lane_payload[key],
                            event_index=event_index,
                            event=event,
                            field_path=f"{lane_path}.{key}",
                            violations=violations,
                        )
                if "candidates" in lane_payload:
                    _validate_sse_integer(
                        lane_payload["candidates"],
                        event_index=event_index,
                        event=event,
                        field_path=f"{lane_path}.candidates",
                        violations=violations,
                        nonnegative=True,
                    )
    elif event == "answer_chunk" and "text" in payload:
        _validate_sse_string(
            payload["text"],
            event_index=event_index,
            event=event,
            field_path=f"{field_path}.text",
            violations=violations,
        )
    elif event == "error" and "detail" in payload:
        _validate_sse_string(
            payload["detail"],
            event_index=event_index,
            event=event,
            field_path=f"{field_path}.detail",
            violations=violations,
        )
    return violations


def _evaluate_sse_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts: dict[str, int] = {}
    event_names: list[str] = []
    answer_chunk_indexes: list[int] = []
    answer_indexes: list[int] = []
    done_indexes: list[int] = []
    error_indexes: list[int] = []
    chunk_texts: list[str] = []
    answer_texts: list[str] = []
    answer_citation_flags: list[bool] = []
    answer_option_flags: list[bool] = []
    valid_event_shapes = True
    known_event_names = True
    synthesis_stage_seen = False
    marker_latches: list[dict[str, Any]] = []
    schema_violations: list[dict[str, Any]] = []
    allowed_wire_marker_kinds = {
        *(marker_kind for marker_kind, _pattern in INTERNAL_MARKER_PATTERNS),
        SSE_WIRE_STRUCTURE_MARKER_KIND,
    }

    for index, event in enumerate(events):
        raw_name = event.get("name")
        data = event.get("data")
        raw_data = event.get("raw_data")
        raw_wire_latches = event.get("wire_latches", [])
        event_shape_valid = bool(
            isinstance(raw_name, str)
            and isinstance(data, dict)
            and isinstance(raw_data, str)
            and isinstance(raw_wire_latches, list)
        )
        if not isinstance(raw_name, str) or not isinstance(data, dict):
            valid_event_shapes = False
            raw_name = ""
            data = {}
        if not isinstance(raw_data, str):
            valid_event_shapes = False
            raw_data = ""
        if not isinstance(raw_wire_latches, list):
            valid_event_shapes = False
            raw_wire_latches = []
        for raw_latch in raw_wire_latches:
            raw_latch = raw_latch if isinstance(raw_latch, dict) else {}
            marker_kind = raw_latch.get("marker_kind")
            sha256 = raw_latch.get("sha256")
            if not (
                marker_kind in allowed_wire_marker_kinds
                and isinstance(sha256, str)
                and re.fullmatch(r"[0-9a-f]{64}", sha256)
            ):
                valid_event_shapes = False
                event_shape_valid = False
                continue
            marker_latches.append(
                {
                    "marker_kind": marker_kind,
                    "event_index": index,
                    "sha256": sha256,
                }
            )

        name = raw_name if raw_name in SAFE_SSE_EVENT_NAMES else "unknown"
        known_event_names = known_event_names and name != "unknown"
        event_names.append(name)
        event_counts[name] = event_counts.get(name, 0) + 1
        event_schema_violations = _sse_event_schema_violations(
            event_index=index,
            event=name,
            data=data,
        )
        schema_violations.extend(event_schema_violations)
        valid_event_shapes = valid_event_shapes and not event_schema_violations
        event_schema_valid = bool(
            event_shape_valid and name != "unknown" and not event_schema_violations
        )
        if event_schema_valid and name == "stage" and data.get("name") == "synthesis":
            synthesis_stage_seen = True

        marker_material = "\n".join([raw_name, raw_data, *_nested_string_values(data)])
        marker_sha256 = hashlib.sha256(marker_material.encode("utf-8")).hexdigest()
        for marker_kind, pattern in INTERNAL_MARKER_PATTERNS:
            if re.search(pattern, marker_material, flags=re.IGNORECASE):
                marker_latches.append(
                    {
                        "marker_kind": marker_kind,
                        "event_index": index,
                        "sha256": marker_sha256,
                    }
                )

        if name == "answer_chunk":
            answer_chunk_indexes.append(index)
            chunk_text = data.get("text")
            if isinstance(chunk_text, str):
                chunk_texts.append(chunk_text)
            else:
                valid_event_shapes = False
        elif name == "answer":
            answer_indexes.append(index)
            answer_text = data.get("answer_text")
            if isinstance(answer_text, str):
                answer_texts.append(answer_text)
            else:
                valid_event_shapes = False
            citations = data.get("citations")
            answer_citation_flags.append(
                bool(event_schema_valid and isinstance(citations, list) and citations)
            )
            clarification = data.get("clarification")
            options = (
                clarification.get("options")
                if isinstance(clarification, dict)
                else None
            )
            answer_option_flags.append(
                bool(event_schema_valid and isinstance(options, list) and options)
            )
        elif name == "done":
            done_indexes.append(index)
        elif name == "error":
            error_indexes.append(index)

    answer_index = answer_indexes[0] if len(answer_indexes) == 1 else None
    done_index = done_indexes[0] if len(done_indexes) == 1 else None
    chunk_text = "".join(chunk_texts)
    answer_text = answer_texts[0] if len(answer_texts) == 1 else ""
    successful_terminal_shape = bool(
        not error_indexes
        and answer_index is not None
        and done_index is not None
        and answer_index == len(events) - 2
        and done_index == len(events) - 1
    )
    terminal_controls = (
        [".process-summary summary"] if successful_terminal_shape else []
    )
    if successful_terminal_shape and answer_citation_flags == [True]:
        terminal_controls.append(".evidence-summary")
    if successful_terminal_shape and answer_option_flags == [True]:
        terminal_controls.append(".option-button")
    control_expectations = {
        "streaming": [".process-stop"] if synthesis_stage_seen else [],
        "terminal": terminal_controls,
    }
    checks = {
        "valid_event_shapes": valid_event_shapes,
        "known_event_names": known_event_names,
        "no_error_events": not error_indexes,
        "unique_answer": len(answer_indexes) == 1,
        "nonempty_answer": len(answer_texts) == 1 and bool(answer_text.strip()),
        "unique_done": len(done_indexes) == 1,
        "chunks_before_answer": answer_index is not None
        and all(index < answer_index for index in answer_chunk_indexes),
        "answer_before_done": answer_index is not None
        and done_index is not None
        and answer_index < done_index,
        "answer_is_penultimate": answer_index is not None
        and answer_index == len(events) - 2,
        "done_is_terminal": done_index is not None and done_index == len(events) - 1,
        "no_events_after_terminal": done_index is not None
        and done_index == len(events) - 1,
        "chunks_reconstruct_answer": len(answer_texts) == 1
        and (
            not answer_chunk_indexes
            or (
                len(chunk_texts) == len(answer_chunk_indexes)
                and chunk_text == answer_text
            )
        ),
        "no_raw_event_markers": not marker_latches,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "event_count": len(events),
        "event_counts": dict(sorted(event_counts.items())),
        "indexes": {
            "answer_chunks": answer_chunk_indexes,
            "answer": answer_index,
            "done": done_index,
            "errors": error_indexes,
        },
        "checks": checks,
        "control_expectations": control_expectations,
        "event_order_sha256": hashlib.sha256(
            "\n".join(event_names).encode("utf-8")
        ).hexdigest(),
        "chunk_text_sha256": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
        "answer_text_sha256": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
        "event_marker_latches": marker_latches,
        "schema_violations": schema_violations,
    }


def _ordered_defects(defects: set[str]) -> list[str]:
    return [code for code in DEFECT_ORDER if code in defects]


def _write_json(path: Path, payload: Any) -> None:
    temporary_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _commit_artifacts(
    run_dir: Path,
    console_events: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    _write_json(run_dir / "console.json", console_events)
    _write_json(run_dir / "summary.json", summary)


def _production_observation_provenance() -> dict[str, bool | str]:
    return {
        "observation_kind": "browser_observation",
        "task9_provenance_certified": False,
        "evidence_eligible_without_task9_receipt": False,
    }


def _create_run_directory(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = output_dir / f"{timestamp}-{secrets.token_hex(4)}"
    run_dir.mkdir(exist_ok=False)
    return run_dir


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run S12G browser acceptance without installing dependencies."
    )
    parser.add_argument("--browser", choices=("chromium",), default="chromium")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--real-sse-query")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.self_test:
        if args.url is not None or args.real_sse_query is not None:
            parser.error(
                "--self-test cannot be combined with --url or --real-sse-query"
            )
    elif not args.url or not args.real_sse_query:
        parser.error("production mode requires both --url and --real-sse-query")
    return args


def _console_event(page_label: str, event_type: str, text: str) -> dict[str, Any]:
    return {
        "page": page_label,
        "type": event_type,
        **_fingerprint(text),
    }


def _attach_sanitized_console(
    page: Any,
    page_label: str,
    console_events: list[dict[str, Any]],
) -> None:
    def record_console(message: Any) -> None:
        try:
            event_type = message.type
            text = message.text
            console_events.append(_console_event(page_label, event_type, text))
        except Exception:
            console_events.append(
                _console_event(page_label, "console_serialization_error", "")
            )

    def record_page_error(error: Any) -> None:
        try:
            text = str(error)
        except Exception:
            text = ""
        console_events.append(_console_event(page_label, "pageerror", text))

    page.on("console", record_console)
    page.on("pageerror", record_page_error)


def _capture_failure(page: Any, path: Path) -> dict[str, Any]:
    if page is None:
        return {"screenshot_saved": False, "reason": "PAGE_CLOSED"}
    try:
        if page.is_closed():
            return {"screenshot_saved": False, "reason": "PAGE_CLOSED"}
    except Exception:
        return {"screenshot_saved": False, "reason": "PAGE_CLOSED"}

    mask_selectors = (
        ".shell[data-presentation-state]",
        "#messages",
        "#chat-input",
        "#demo-grid",
    )
    try:
        masks = [page.locator(selector) for selector in mask_selectors]
        if any(mask.count() != 1 for mask in masks):
            return {
                "screenshot_saved": False,
                "reason": "MASK_ROOTS_UNAVAILABLE",
            }
    except Exception:
        return {"screenshot_saved": False, "reason": "MASK_ROOTS_UNAVAILABLE"}

    try:
        page.screenshot(
            path=str(path),
            full_page=True,
            mask=masks,
            mask_color="#000000",
        )
    except Exception:
        # Artifact capture must not hide or persist the primary acceptance failure.
        return {"screenshot_saved": False, "reason": "CAPTURE_FAILED"}
    return {"screenshot_saved": True, "reason": "MASKED_CHAT_ROOTS"}


def _settle_geometry(page: Any) -> None:
    page.evaluate(
        """() => new Promise((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(resolve));
        })"""
    )


def _core_geometry(page: Any) -> dict[str, Any]:
    return _browser_geometry(page, ())


def _browser_geometry(page: Any, target_selectors: tuple[str, ...]) -> dict[str, Any]:
    return page.evaluate(
        """(selectors) => {
          const root = document.documentElement;
          const body = document.body;
          const visual = window.visualViewport;
          const round = (value) => Math.round(Number(value) * 1000) / 1000;
          const rect = (selector) => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            if (
              style.display === "none" ||
              style.visibility === "hidden" ||
              box.width <= 0 ||
              box.height <= 0
            ) return null;
            return {
              left: round(box.left),
              top: round(box.top),
              right: round(box.right),
              bottom: round(box.bottom),
              width: round(box.width),
              height: round(box.height),
            };
          };
          const cssAppHeight = Number.parseFloat(
            getComputedStyle(root).getPropertyValue("--app-height"),
          );
          const targets = [];
          for (const selector of selectors) {
            document.querySelectorAll(selector).forEach((element, index) => {
              const style = getComputedStyle(element);
              const box = element.getBoundingClientRect();
              if (
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                box.width > 0 &&
                box.height > 0
              ) {
                targets.push({
                  selector,
                  index,
                  width: round(box.width),
                  height: round(box.height),
                });
              }
            });
          }
          return {
            viewport: {
              width: round(window.innerWidth),
              height: round(window.innerHeight),
              visual: {
                offset_left: round(visual ? visual.offsetLeft : 0),
                offset_top: round(visual ? visual.offsetTop : 0),
                width: round(visual ? visual.width : window.innerWidth),
                height: round(visual ? visual.height : window.innerHeight),
              },
              css_app_height: Number.isFinite(cssAppHeight)
                ? round(cssAppHeight)
                : null,
              visual_viewport_short: root.classList.contains(
                "visual-viewport-short",
              ),
            },
            document: {
              client_width: round(root.clientWidth),
              scroll_width: round(
                Math.max(root.scrollWidth, body ? body.scrollWidth : 0),
              ),
              client_height: round(root.clientHeight),
              scroll_height: round(
                Math.max(root.scrollHeight, body ? body.scrollHeight : 0),
              ),
              scroll_x: round(window.scrollX),
              scroll_y: round(window.scrollY),
            },
            presentation_state:
              document.querySelector(".shell")?.dataset.presentationState || null,
            shell: rect(".shell"),
            header: rect(".header"),
            messages: rect("#messages"),
            composer: rect(".composer"),
            targets,
          };
        }""",
        list(target_selectors),
    )


def _evaluate_geometry_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "document_size_fits": False,
        "document_not_scrolled": False,
        "shell_matches_visual_viewport": False,
        "core_within_visual_viewport": False,
        "core_within_shell": False,
        "core_ordered": False,
    }
    try:
        document = snapshot["document"]
        viewport = snapshot["viewport"]
        visual = viewport["visual"]
        shell = snapshot["shell"]
        core = [snapshot["header"], snapshot["messages"], snapshot["composer"]]
        checks["document_size_fits"] = bool(
            document["scroll_width"] <= document["client_width"] + 0.01
            and document["scroll_height"] <= document["client_height"] + 0.01
        )
        checks["document_not_scrolled"] = bool(
            abs(document["scroll_x"]) < 0.01 and abs(document["scroll_y"]) < 0.01
        )
        visual_left = visual["offset_left"]
        visual_top = visual["offset_top"]
        visual_right = visual_left + visual["width"]
        visual_bottom = visual_top + visual["height"]
        app_height = viewport["css_app_height"]
        expected_shell_width = (
            visual["width"]
            if viewport["width"] <= 720
            else min(980, max(0, visual["width"] - 32))
        )
        expected_shell_left = visual_left + (visual["width"] - expected_shell_width) / 2
        checks["shell_matches_visual_viewport"] = bool(
            shell is not None
            and app_height is not None
            and abs(shell["width"] - expected_shell_width) <= GEOMETRY_TOLERANCE_PX
            and abs(shell["left"] - expected_shell_left) <= GEOMETRY_TOLERANCE_PX
            and abs(shell["height"] - visual["height"]) <= GEOMETRY_TOLERANCE_PX
            and abs(app_height - visual["height"]) <= GEOMETRY_TOLERANCE_PX
        )
        all_rects = [shell, *core]
        checks["core_within_visual_viewport"] = bool(
            all(rect is not None for rect in all_rects)
            and all(
                rect["left"] >= visual_left - 0.01
                and rect["top"] >= visual_top - 0.01
                and rect["right"] <= visual_right + 0.01
                and rect["bottom"] <= visual_bottom + 0.01
                for rect in all_rects
            )
        )
        checks["core_within_shell"] = bool(
            shell is not None
            and all(rect is not None for rect in core)
            and all(
                rect["left"] >= shell["left"] - GEOMETRY_TOLERANCE_PX
                and rect["top"] >= shell["top"] - GEOMETRY_TOLERANCE_PX
                and rect["right"] <= shell["right"] + GEOMETRY_TOLERANCE_PX
                and rect["bottom"] <= shell["bottom"] + GEOMETRY_TOLERANCE_PX
                for rect in core
            )
        )
        checks["core_ordered"] = bool(
            all(rect is not None for rect in core)
            and core[0]["bottom"] <= core[1]["top"] + GEOMETRY_TOLERANCE_PX
            and core[1]["bottom"] <= core[2]["top"] + GEOMETRY_TOLERANCE_PX
        )
    except (KeyError, TypeError, ValueError):
        pass

    defects: set[str] = set()
    if not checks["document_size_fits"] or not checks["document_not_scrolled"]:
        defects.add("DOCUMENT_OVERFLOW")
    if not all(
        checks[name]
        for name in (
            "shell_matches_visual_viewport",
            "core_within_visual_viewport",
            "core_within_shell",
            "core_ordered",
        )
    ):
        defects.add("ROTATION_STALE_GEOMETRY")
    return {
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "checks": checks,
    }


def _geometry_is_stale(snapshot: dict[str, Any]) -> bool:
    return (
        "ROTATION_STALE_GEOMETRY"
        in _evaluate_geometry_snapshot(snapshot)["defect_codes"]
    )


def _summarize_target_samples(
    samples: list[dict[str, Any]],
    selectors: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    summary = {
        selector: {
            "seen": False,
            "sample_count": 0,
            "min_width": None,
            "min_height": None,
            "ever_below_44": False,
        }
        for selector in selectors
    }
    for sample in samples:
        selector = sample.get("selector")
        if selector not in summary:
            continue
        record = summary[selector]
        width = sample.get("width")
        height = sample.get("height")
        record["seen"] = True
        record["sample_count"] += 1
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            record["ever_below_44"] = True
            continue
        record["min_width"] = (
            width if record["min_width"] is None else min(record["min_width"], width)
        )
        record["min_height"] = (
            height
            if record["min_height"] is None
            else min(record["min_height"], height)
        )
        if width + 0.01 < 44 or height + 0.01 < 44:
            record["ever_below_44"] = True
    return summary


def _required_actionable_controls(
    state: str,
    *,
    short_layout: bool = False,
) -> tuple[str, ...]:
    if short_layout and state in REQUIRED_ACTIONABLE_CONTROLS:
        return ("#chat-input", "#chat-submit")
    return REQUIRED_ACTIONABLE_CONTROLS.get(state, ())


def _actionable_control_observations(
    page: Any,
    state: str,
    *,
    required_controls: tuple[str, ...] | None = None,
) -> dict[str, dict[str, bool]]:
    required = (
        _required_actionable_controls(state)
        if required_controls is None
        else required_controls
    )
    observations: dict[str, dict[str, bool]] = {}
    for selector in required:
        locator = page.locator(selector)
        count = locator.count()
        visible = count > 0
        actionable = count > 0
        for index in range(count):
            candidate = locator.nth(index)
            if not candidate.is_visible():
                visible = False
                actionable = False
                continue
            try:
                box = candidate.bounding_box()
                width = box.get("width") if isinstance(box, dict) else None
                height = box.get("height") if isinstance(box, dict) else None
                target_size_valid = all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and value + 0.01 >= 44
                    for value in (width, height)
                )
                if not target_size_valid:
                    actionable = False
                candidate.click(trial=True, timeout=1_000)
            except Exception:
                actionable = False
        observations[selector] = {
            "seen": count > 0,
            "visible": visible,
            "actionable": actionable,
        }
    return observations


def _evaluate_actionable_controls(
    state: str,
    observations: dict[str, dict[str, bool]],
    *,
    required_controls: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    required = (
        _required_actionable_controls(state)
        if required_controls is None
        else required_controls
    )
    controls = {
        selector: {
            "seen": bool(observations.get(selector, {}).get("seen")),
            "visible": bool(observations.get(selector, {}).get("visible")),
            "actionable": bool(observations.get(selector, {}).get("actionable")),
        }
        for selector in required
    }
    passed = bool(required) and all(
        item["seen"] and item["visible"] and item["actionable"]
        for item in controls.values()
    )
    defects = set() if passed else {"REQUIRED_CONTROL_NOT_ACTIONABLE"}
    return {
        "status": "passed" if passed else "failed",
        "defect_codes": _ordered_defects(defects),
        "required_controls": list(required),
        "controls": controls,
    }


def _terminal_actionable_controls(
    page: Any,
    *,
    required_dynamic_controls: tuple[str, ...] = (".process-summary summary",),
) -> dict[str, Any]:
    required = (
        *_required_actionable_controls("conversation"),
        *required_dynamic_controls,
    )
    return _evaluate_actionable_controls(
        "conversation",
        _actionable_control_observations(
            page,
            "conversation",
            required_controls=required,
        ),
        required_controls=required,
    )


def _evaluate_detached_samples(
    baseline: dict[str, Any],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    valid_shape = (
        isinstance(baseline, dict) and isinstance(samples, list) and bool(samples)
    )
    baseline_scroll = baseline.get("scroll_top") if isinstance(baseline, dict) else None
    baseline_anchor = baseline.get("anchor_top") if isinstance(baseline, dict) else None
    valid_shape = valid_shape and all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (baseline_scroll, baseline_anchor)
    )

    max_scroll_delta = None
    max_scroll_delta_index = None
    max_anchor_delta = None
    max_anchor_delta_index = None
    terminal_scroll_delta = None
    terminal_anchor_delta = None
    if valid_shape:
        scroll_deltas: list[float] = []
        anchor_deltas: list[float] = []
        for sample in samples:
            scroll_top = sample.get("scroll_top") if isinstance(sample, dict) else None
            anchor_top = sample.get("anchor_top") if isinstance(sample, dict) else None
            if not all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in (scroll_top, anchor_top)
            ):
                valid_shape = False
                break
            scroll_deltas.append(abs(scroll_top - baseline_scroll))
            anchor_deltas.append(abs(anchor_top - baseline_anchor))
        if valid_shape:
            max_scroll_delta = max(scroll_deltas)
            max_scroll_delta_index = scroll_deltas.index(max_scroll_delta)
            max_anchor_delta = max(anchor_deltas)
            max_anchor_delta_index = anchor_deltas.index(max_anchor_delta)
            terminal_scroll_delta = scroll_deltas[-1]
            terminal_anchor_delta = anchor_deltas[-1]

    within_tolerance = bool(
        valid_shape
        and max_scroll_delta is not None
        and max_anchor_delta is not None
        and max_scroll_delta <= GEOMETRY_TOLERANCE_PX
        and max_anchor_delta <= GEOMETRY_TOLERANCE_PX
    )
    defects = set() if within_tolerance else {"DETACHED_SCROLL_DRIFT"}
    return {
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "checks": {
            "valid_sample_shape": valid_shape,
            "all_samples_within_tolerance": within_tolerance,
        },
        "sample_count": len(samples) if isinstance(samples, list) else 0,
        "max_scroll_delta": max_scroll_delta,
        "max_scroll_delta_index": max_scroll_delta_index,
        "max_anchor_delta": max_anchor_delta,
        "max_anchor_delta_index": max_anchor_delta_index,
        "terminal_scroll_delta": terminal_scroll_delta,
        "terminal_anchor_delta": terminal_anchor_delta,
    }


ROTATION_PHASE_VIEWPORTS = (
    (390, 844),
    (390, 500),
    (390, 844),
    (844, 390),
    (390, 844),
)


def _evaluate_rotation_continuity(
    phases: list[dict[str, Any]],
    expected_input_fingerprint: dict[str, Any],
) -> dict[str, Any]:
    expected_source = (
        expected_input_fingerprint
        if isinstance(expected_input_fingerprint, dict)
        else {}
    )
    expected_fingerprint = {
        "length": (
            expected_source.get("length")
            if isinstance(expected_source.get("length"), int)
            and not isinstance(expected_source.get("length"), bool)
            else None
        ),
        "sha256": (
            expected_source.get("sha256")
            if isinstance(expected_source.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_source["sha256"])
            else None
        ),
    }
    sanitized: list[dict[str, Any]] = []
    if isinstance(phases, list):
        for phase in phases:
            phase = phase if isinstance(phase, dict) else {}
            viewport = phase.get("viewport")
            viewport = viewport if isinstance(viewport, dict) else {}
            fingerprint = phase.get("input_value_fingerprint")
            fingerprint = fingerprint if isinstance(fingerprint, dict) else {}
            shell = phase.get("shell")
            shell = shell if isinstance(shell, dict) else {}
            sanitized.append(
                {
                    "phase_index": (
                        phase.get("phase_index")
                        if isinstance(phase.get("phase_index"), int)
                        and not isinstance(phase.get("phase_index"), bool)
                        else None
                    ),
                    "viewport": {
                        "width": viewport.get("width")
                        if isinstance(viewport.get("width"), (int, float))
                        else None,
                        "height": viewport.get("height")
                        if isinstance(viewport.get("height"), (int, float))
                        else None,
                    },
                    "geometry_status": (
                        phase.get("geometry_status")
                        if phase.get("geometry_status") in {"passed", "failed"}
                        else "invalid"
                    ),
                    "presentation_state": (
                        phase.get("presentation_state")
                        if phase.get("presentation_state")
                        in {
                            "landing",
                            "conversation",
                            "demo-expanded",
                        }
                        else "invalid"
                    ),
                    "input_value_fingerprint": {
                        "length": fingerprint.get("length")
                        if isinstance(fingerprint.get("length"), int)
                        and not isinstance(fingerprint.get("length"), bool)
                        else None,
                        "sha256": fingerprint.get("sha256")
                        if isinstance(fingerprint.get("sha256"), str)
                        and re.fullmatch(r"[0-9a-f]{64}", fingerprint["sha256"])
                        else None,
                    },
                    "input_focused": phase.get("input_focused") is True,
                    "scroll_intent": (
                        phase.get("scroll_intent")
                        if phase.get("scroll_intent") in {"following", "detached"}
                        else "invalid"
                    ),
                    "sentinel_present": phase.get("sentinel_present") is True,
                    "shell": {
                        "width": shell.get("width")
                        if isinstance(shell.get("width"), (int, float))
                        else None,
                        "height": shell.get("height")
                        if isinstance(shell.get("height"), (int, float))
                        else None,
                    },
                }
            )

    phase_sequence = len(sanitized) == len(ROTATION_PHASE_VIEWPORTS) and all(
        phase["phase_index"] == index
        and phase["viewport"] == {"width": width, "height": height}
        for index, (phase, (width, height)) in enumerate(
            zip(sanitized, ROTATION_PHASE_VIEWPORTS, strict=True)
        )
    )
    geometry_valid = phase_sequence and all(
        phase["geometry_status"] == "passed"
        and phase["shell"]["width"] is not None
        and phase["shell"]["width"] > 0
        and phase["shell"]["height"] is not None
        and phase["shell"]["height"] > 0
        for phase in sanitized
    )
    fingerprint_valid = bool(
        expected_fingerprint["length"] is not None
        and expected_fingerprint["length"] >= 0
        and expected_fingerprint["sha256"] is not None
    )
    final_shell_restored = bool(
        phase_sequence
        and sanitized[0]["shell"] == sanitized[-1]["shell"]
        and sanitized[-1]["shell"] == {"width": 390, "height": 844}
    )
    checks = {
        "phase_sequence": phase_sequence,
        "geometry_valid": geometry_valid,
        "conversation_state_preserved": phase_sequence
        and all(phase["presentation_state"] == "conversation" for phase in sanitized),
        "input_value_preserved": phase_sequence
        and fingerprint_valid
        and all(
            phase["input_value_fingerprint"] == expected_fingerprint
            for phase in sanitized
        ),
        "input_focus_preserved": phase_sequence
        and all(phase["input_focused"] for phase in sanitized),
        "detached_intent_preserved": phase_sequence
        and all(phase["scroll_intent"] == "detached" for phase in sanitized),
        "sentinel_preserved": phase_sequence
        and all(phase["sentinel_present"] for phase in sanitized),
        "final_shell_restored": final_shell_restored,
    }
    defects = set() if all(checks.values()) else {"ROTATION_STALE_GEOMETRY"}
    return {
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "checks": checks,
        "phases": sanitized,
    }


def _evaluate_dom_marker_latches(latches: list[dict[str, Any]]) -> dict[str, Any]:
    allowed_marker_kinds = {kind for kind, _pattern in INTERNAL_MARKER_PATTERNS}
    valid_shape = isinstance(latches, list)
    sanitized: list[dict[str, Any]] = []
    if isinstance(latches, list):
        for latch in latches:
            latch = latch if isinstance(latch, dict) else {}
            marker_kind = latch.get("marker_kind")
            mutation_index = latch.get("mutation_index")
            sha256 = latch.get("sha256")
            latch_valid = bool(
                marker_kind in allowed_marker_kinds
                and isinstance(mutation_index, int)
                and not isinstance(mutation_index, bool)
                and mutation_index >= 0
                and isinstance(sha256, str)
                and re.fullmatch(r"[0-9a-f]{64}", sha256)
            )
            valid_shape = valid_shape and latch_valid
            sanitized.append(
                {
                    "marker_kind": marker_kind
                    if marker_kind in allowed_marker_kinds
                    else None,
                    "mutation_index": (
                        mutation_index
                        if isinstance(mutation_index, int)
                        and not isinstance(mutation_index, bool)
                        and mutation_index >= 0
                        else None
                    ),
                    "sha256": (
                        sha256
                        if isinstance(sha256, str)
                        and re.fullmatch(r"[0-9a-f]{64}", sha256)
                        else None
                    ),
                }
            )
    checks = {
        "valid_latch_shape": valid_shape,
        "no_dom_mutation_markers": valid_shape and not sanitized,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "latches": sanitized,
    }


def _install_dom_marker_probe(page: Any) -> None:
    patterns = [
        {"kind": marker_kind, "pattern": pattern}
        for marker_kind, pattern in INTERNAL_MARKER_PATTERNS
    ]
    if page.evaluate(DOM_MARKER_PROBE_SCRIPT, patterns) is not True:
        raise AcceptanceRuntimeError(
            "DOM_MARKER_PROBE_INSTALL_FAILED",
            "The DOM mutation marker probe could not be installed.",
        )


def _dom_marker_probe_result(page: Any) -> list[dict[str, Any]] | None:
    return page.evaluate(
        """async () => {
          const state = window.__s12gDomMarkerProbe;
          if (!state) return null;
          state.processRecords(state.observer.takeRecords());
          state.observer.disconnect();
          await Promise.allSettled([...state.pending]);
          return state.latches
            .map((latch) => ({
              marker_kind: latch.marker_kind,
              mutation_index: latch.mutation_index,
              sha256: latch.sha256,
            }))
            .sort((left, right) =>
              left.mutation_index - right.mutation_index ||
              String(left.marker_kind).localeCompare(String(right.marker_kind)),
            );
        }"""
    )


def _collect_oracle(
    page: Any,
    *,
    target_selectors: tuple[str, ...] = (),
    detached_probe: dict[str, Any] | None = None,
    geometry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    geometry = (
        geometry_snapshot
        if geometry_snapshot is not None
        else _browser_geometry(page, target_selectors)
    )
    geometry_report = _evaluate_geometry_snapshot(geometry)
    defects = set(geometry_report["defect_codes"])
    target_summary = _summarize_target_samples(geometry["targets"], target_selectors)
    defects.update(_sampled_target_defects(target_summary))

    detached_observation = None
    if detached_probe is not None:
        detached_observation = _evaluate_detached_samples(
            detached_probe.get("baseline"), detached_probe.get("samples")
        )
        defects.update(detached_observation["defect_codes"])

    return {
        "defect_codes": _ordered_defects(defects),
        "geometry": geometry,
        "geometry_checks": geometry_report["checks"],
        "target_summary": target_summary,
        "detached_scroll": detached_observation,
    }


def _self_test_html(fixture: str) -> str:
    if fixture not in {
        "valid",
        "document-overflow",
        "small-target",
        "detached-scroll-drift",
        "rotation-stale-geometry",
    }:
        raise ValueError(f"unknown self-test fixture: {fixture}")

    rows = "".join(
        f'<div data-row="{index}" style="height:24px">row {index}</div>'
        for index in range(40)
    )
    fixture_style = {
        "valid": "",
        "document-overflow": (
            ".document-overflow-probe { position: absolute; left: 100vw; top: 0; "
            "width: 24px; height: 1px; }"
        ),
        "small-target": ".demo-chip { width: 30px; height: 30px; }",
        "detached-scroll-drift": "",
        "rotation-stale-geometry": "",
    }[fixture]
    resize_script = (
        'document.documentElement.style.setProperty("--app-height", '
        "`${window.innerHeight}px`);"
    )
    resize_listener = (
        f"const updateAppHeight = () => {{ {resize_script} }};"
        "updateAppHeight();"
        'window.addEventListener("resize", updateAppHeight);'
        if fixture != "rotation-stale-geometry"
        else 'document.documentElement.style.setProperty("--app-height", "844px");'
    )
    detached_script = (
        """
        new MutationObserver(() => {
          const preservedScrollTop = messages.scrollTop;
          messages.scrollTop = preservedScrollTop + 24;
          requestAnimationFrame(() => { messages.scrollTop = preservedScrollTop; });
        }).observe(messages, { childList: true });
        """
        if fixture == "detached-scroll-drift"
        else ""
    )
    overflow_probe = (
        '<div class="document-overflow-probe" aria-hidden="true"></div>'
        if fixture == "document-overflow"
        else ""
    )
    return f"""<!doctype html>
<html>
<head>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{ --app-height: 568px; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
    body {{ font-family: sans-serif; }}
    .shell {{
      display: grid;
      grid-template-rows: 56px minmax(0, 1fr) 60px;
      width: 100%;
      height: var(--app-height);
      overflow: hidden;
    }}
    @media (min-width: 721px) {{
      .shell {{
        width: min(980px, calc(100% - 32px));
        margin-inline: auto;
      }}
    }}
    .header {{ display: flex; align-items: center; justify-content: space-between; }}
    #messages {{ min-height: 0; overflow: auto; }}
    .composer {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 44px;
      gap: 8px;
      align-items: center;
      padding: 8px;
    }}
    #chat-input {{ min-width: 0; width: 100%; height: 44px; }}
    #chat-submit, #demo-toggle {{ width: 44px; height: 44px; padding: 0; }}
    .demo-chip {{ width: 72px; height: 44px; padding: 0; }}
    #demo-grid {{ display: grid; width: max-content; }}
    {fixture_style}
  </style>
</head>
<body>
  <main class="shell" data-presentation-state="conversation" data-scroll-intent="detached">
    <header class="header">
      <span>Acceptance fixture</span>
      <button id="demo-toggle" type="button">Demo</button>
    </header>
    <section id="messages">
      {rows}
      <div id="reading-anchor">reading anchor</div>
      <div id="rotation-sentinel">rotation sentinel</div>
      <div id="demo-grid"><button class="demo-chip" type="button">Example</button></div>
    </section>
    <form class="composer" onsubmit="return false">
      <input id="chat-input" value="s12g-rotation" />
      <button id="chat-submit" type="submit">Send</button>
    </form>
  </main>
  {overflow_probe}
  <script>
    (() => {{
      {resize_listener}
      const messages = document.getElementById("messages");
      messages.scrollTop = 240;
      {detached_script}
    }})();
  </script>
</body>
</html>"""


def _load_self_test_fixture(page: Any, fixture: str) -> None:
    self_test_url = f"https://s12g-self-test.invalid/{fixture}"
    fixture_html = _self_test_html(fixture)

    def fulfill_fixture(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="text/html; charset=utf-8",
            body=fixture_html,
        )

    page.route(self_test_url, fulfill_fixture)
    try:
        page.goto(self_test_url, wait_until="load")
    finally:
        page.unroute(self_test_url, fulfill_fixture)

    if (
        page.evaluate(
            '() => isSecureContext && typeof crypto.subtle.digest === "function"'
        )
        is not True
    ):
        raise AcceptanceRuntimeError(
            "SELF_TEST_WEB_CRYPTO_UNAVAILABLE",
            "The self-test fixture does not have browser SHA-256 support.",
        )


def _detached_fixture_probe(page: Any) -> dict[str, Any]:
    probe = page.evaluate(
        """() => new Promise((resolve) => {
          const messages = document.getElementById("messages");
          const anchor = document.getElementById("reading-anchor");
          const sample = () => ({
            scroll_top: messages.scrollTop,
            anchor_top: anchor.getBoundingClientRect().top,
          });
          const baseline = sample();
          const samples = [];
          const observer = new MutationObserver(() => {
            samples.push(sample());
            requestAnimationFrame(() => {
              samples.push(sample());
              requestAnimationFrame(() => samples.push(sample()));
            });
          });
          observer.observe(messages, { childList: true, subtree: true });
          const row = document.createElement("div");
          row.style.height = "24px";
          row.textContent = "new row";
          messages.append(row);
          requestAnimationFrame(() => requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              samples.push(sample());
              observer.disconnect();
              resolve({ baseline, samples });
            });
          }));
        })"""
    )
    probe["evaluation"] = _evaluate_detached_samples(
        probe["baseline"], probe["samples"]
    )
    return probe


def _rotation_phase_record(
    page: Any,
    phase_index: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    page.set_viewport_size({"width": width, "height": height})
    _settle_geometry(page)
    snapshot = _core_geometry(page)
    input_value = page.locator("#chat-input").input_value()
    state = page.evaluate(
        """() => ({
          input_focused: document.activeElement?.id === "chat-input",
          scroll_intent:
            document.getElementById("messages")?.dataset.scrollIntent ||
            document.querySelector(".shell")?.dataset.scrollIntent ||
            null,
          sentinel_present: Boolean(document.getElementById("rotation-sentinel")),
        })"""
    )
    geometry = _evaluate_geometry_snapshot(snapshot)
    return {
        "phase_index": phase_index,
        "viewport": {"width": width, "height": height},
        "geometry_status": geometry["status"],
        "presentation_state": snapshot["presentation_state"],
        "input_value_fingerprint": _fingerprint(input_value),
        "input_focused": state["input_focused"],
        "scroll_intent": state["scroll_intent"],
        "sentinel_present": state["sentinel_present"],
        "shell": {
            "width": snapshot["shell"]["width"] if snapshot["shell"] else None,
            "height": snapshot["shell"]["height"] if snapshot["shell"] else None,
        },
    }


def _run_self_test(
    browser: Any,
    run_dir: Path,
    console_events: list[dict[str, Any]],
) -> dict[str, Any]:
    fixtures = (
        ("valid", set()),
        ("document-overflow", {"DOCUMENT_OVERFLOW"}),
        ("small-target", {"TARGET_LT_44"}),
        ("detached-scroll-drift", {"DETACHED_SCROLL_DRIFT"}),
        ("rotation-stale-geometry", {"ROTATION_STALE_GEOMETRY"}),
    )
    context = browser.new_context(viewport={"width": 320, "height": 568})
    page = context.new_page()
    _attach_sanitized_console(page, "self-test", console_events)
    records: list[dict[str, Any]] = []
    try:
        for fixture, expected in fixtures:
            initial_viewport = (
                {"width": 390, "height": 844}
                if fixture in {"valid", "rotation-stale-geometry"}
                else {"width": 320, "height": 568}
            )
            page.set_viewport_size(initial_viewport)
            _load_self_test_fixture(page, fixture)

            dom_marker_probe = None
            if fixture == "valid":
                initial_marker = "PROF-" + "A" * 12
                removed_marker = "COMP-" + "b" * 12
                page.evaluate(
                    """(marker) => {
                      const messages = document.getElementById("messages");
                      const initial = document.createElement("span");
                      initial.dataset.acceptanceOnly = "true";
                      initial.textContent = marker;
                      messages.append(initial);
                      const removable = document.createElement("span");
                      removable.id = "removed-marker-fixture";
                      removable.dataset.acceptanceOnly = "true";
                      removable.textContent = "safe-before-probe";
                      messages.append(removable);
                    }""",
                    initial_marker,
                )
                _install_dom_marker_probe(page)
                page.evaluate(
                    """(marker) => {
                      const state = window.__s12gDomMarkerProbe;
                      const messages = document.getElementById("messages");
                      const removable = document.getElementById(
                        "removed-marker-fixture",
                      );
                      state.observer.disconnect();
                      removable.textContent = marker;
                      state.observer.observe(messages, state.observeOptions);
                      removable.remove();
                    }""",
                    removed_marker,
                )
                _settle_geometry(page)
                marker_report = _evaluate_dom_marker_latches(
                    _dom_marker_probe_result(page)
                )
                page.evaluate(
                    """() => document
                      .querySelectorAll('[data-acceptance-only="true"]')
                      .forEach((element) => element.remove())"""
                )
                marker_serialized = json.dumps(marker_report, ensure_ascii=False)
                initial_marker_detected = bool(
                    marker_report["checks"]["valid_latch_shape"]
                    and any(
                        latch["marker_kind"] == "professor_internal_id"
                        for latch in marker_report["latches"]
                    )
                )
                removed_marker_detected = bool(
                    marker_report["checks"]["valid_latch_shape"]
                    and any(
                        latch["marker_kind"] == "company_internal_id"
                        for latch in marker_report["latches"]
                    )
                )
                raw_markers_absent = all(
                    marker not in marker_serialized
                    for marker in (initial_marker, removed_marker)
                )
                checks: dict[str, bool] = {}
                checks["initial_marker_detected"] = initial_marker_detected
                checks["removed_marker_detected"] = removed_marker_detected
                checks["raw_markers_absent_from_report"] = raw_markers_absent
                dom_marker_probe = {
                    "status": "passed" if all(checks.values()) else "failed",
                    "checks": checks,
                    "latch_report": marker_report,
                }

            detached_probe = (
                _detached_fixture_probe(page)
                if fixture in {"valid", "detached-scroll-drift"}
                else None
            )
            rotation = None
            if fixture in {"valid", "rotation-stale-geometry"}:
                page.locator("#chat-input").focus()
                phases = [
                    _rotation_phase_record(page, index, width, height)
                    for index, (width, height) in enumerate(ROTATION_PHASE_VIEWPORTS)
                ]
                rotation = _evaluate_rotation_continuity(
                    phases,
                    _fingerprint("s12g-rotation"),
                )

            observation = _collect_oracle(
                page,
                target_selectors=VISIBLE_TARGET_SELECTORS,
                detached_probe=detached_probe,
            )
            actionability = _evaluate_actionable_controls(
                "conversation",
                _actionable_control_observations(page, "conversation"),
            )
            observed = set(observation["defect_codes"])
            observed.update(actionability["defect_codes"])
            if rotation is not None:
                observed.update(rotation["defect_codes"])
            marker_probe_passed = bool(
                dom_marker_probe is None or dom_marker_probe["status"] == "passed"
            )
            matches = observed == expected and marker_probe_passed
            records.append(
                {
                    "fixture": fixture,
                    "status": "passed" if matches else "failed",
                    "expected_defect_codes": _ordered_defects(expected),
                    "observed_defect_codes": _ordered_defects(observed),
                    "geometry": observation["geometry"],
                    "target_summary": observation["target_summary"],
                    "actionable_controls": actionability,
                    "detached_scroll": observation["detached_scroll"],
                    "rotation_continuity": rotation,
                    "dom_marker_probe": dom_marker_probe,
                }
            )
        passed = all(record["status"] == "passed" for record in records)
        defects: set[str] = set()
        if not passed:
            for record in records:
                if record["status"] == "passed":
                    continue
                expected_codes = set(record["expected_defect_codes"])
                observed_codes = set(record["observed_defect_codes"])
                defects.update(expected_codes.symmetric_difference(observed_codes))
                marker_probe = record.get("dom_marker_probe")
                if marker_probe is not None and marker_probe["status"] == "failed":
                    defects.add("VIEWPORT_RUNTIME_FAILURE")
            if not defects:
                defects.add("VIEWPORT_RUNTIME_FAILURE")
            _capture_failure(page, run_dir / "self-test-failure.png")
        return {
            "status": "passed" if passed else "failed",
            "defect_codes": _ordered_defects(defects),
            "fixtures": records,
        }
    except Exception:
        _capture_failure(page, run_dir / "self-test-failure.png")
        raise
    finally:
        context.close()


def _short_layout_from_snapshot(snapshot: dict[str, Any]) -> bool:
    viewport = snapshot.get("viewport", {})
    visual = viewport.get("visual", {}) if isinstance(viewport, dict) else {}
    visual_height = visual.get("height") if isinstance(visual, dict) else None
    return bool(
        isinstance(viewport, dict)
        and viewport.get("visual_viewport_short") is True
        or isinstance(visual_height, (int, float))
        and not isinstance(visual_height, bool)
        and visual_height <= 500
    )


def _page_state_record(page: Any, expected_state: str) -> dict[str, Any]:
    _settle_geometry(page)
    snapshot = _browser_geometry(page, VISIBLE_TARGET_SELECTORS)
    short_layout = _short_layout_from_snapshot(snapshot)
    required_controls = _required_actionable_controls(
        expected_state,
        short_layout=short_layout,
    )
    oracle = _collect_oracle(
        page,
        target_selectors=VISIBLE_TARGET_SELECTORS,
        geometry_snapshot=snapshot,
    )
    actionability = _evaluate_actionable_controls(
        expected_state,
        _actionable_control_observations(
            page,
            expected_state,
            required_controls=required_controls,
        ),
        required_controls=required_controls,
    )
    state_matches = snapshot["presentation_state"] == expected_state
    defects = set(oracle["defect_codes"])
    defects.update(actionability["defect_codes"])
    if not state_matches:
        defects.add("ROTATION_STALE_GEOMETRY")
    return {
        "state": expected_state,
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "short_layout": short_layout,
        "core_geometry": snapshot,
        "oracle_geometry": oracle["geometry"],
        "actionable_controls": actionability,
    }


def _exercise_presentation_states(page: Any) -> dict[str, Any]:
    records = [_page_state_record(page, "landing")]

    changed = page.evaluate("() => setPresentationState('conversation')")
    if changed is not True:
        raise AcceptanceRuntimeError(
            "PRESENTATION_STATE_FAILURE",
            "The page rejected the conversation presentation state.",
        )
    page.wait_for_function(
        "() => document.querySelector('.shell')?.dataset.presentationState === 'conversation'"
    )
    records.append(_page_state_record(page, "conversation"))

    short_layout = records[0]["short_layout"]
    layout_consistent = all(
        record["short_layout"] is short_layout for record in records
    )
    toggle = page.locator("#demo-toggle")
    toggle_was_visible = toggle.is_visible()
    short_layout_controls = None
    if short_layout:
        short_layout_controls = {
            "demo_strip_hidden": not page.locator("#demo-strip").is_visible(),
            "demo_toggle_hidden": not toggle_was_visible,
        }
    else:
        toggle.click()
        page.wait_for_function(
            "() => document.querySelector('.shell')?.dataset.presentationState === 'demo-expanded'"
        )
        records.append(_page_state_record(page, "demo-expanded"))
        toggle.click()
        page.wait_for_function(
            "() => document.querySelector('.shell')?.dataset.presentationState === 'conversation'"
        )
        _settle_geometry(page)

    defects = {code for record in records for code in record["defect_codes"]}
    if not layout_consistent or (
        short_layout and not all(short_layout_controls.values())
    ):
        defects.add("ROTATION_STALE_GEOMETRY")
    return {
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "short_layout": short_layout,
        "short_layout_controls": short_layout_controls,
        "toggle_was_visible": toggle_was_visible,
        "states": records,
    }


def _inject_and_probe_long_content(page: Any) -> dict[str, Any]:
    page.evaluate(
        """() => {
          document.getElementById("s12g-long-content")?.remove();
          document.getElementById("welcome")?.remove();
          const row = document.createElement("article");
          row.id = "s12g-long-content";
          row.dataset.acceptanceOnly = "true";
          row.className = "message assistant";
          const avatar = document.createElement("div");
          avatar.className = "avatar";
          const bubble = document.createElement("div");
          bubble.className = "bubble";
          const answer = document.createElement("div");
          answer.className = "answer";
          const longToken = "abcdefghijklmnopqrstuvwxyz0123456789".repeat(18);
          answer.innerHTML = `
            <p><a href="#">https://example.invalid/${longToken}</a></p>
            <p><code>${longToken}</code></p>
            <pre><code>${longToken}</code></pre>
            <table><tbody><tr><td style="white-space:nowrap">${longToken}</td></tr></tbody></table>
            <img alt="acceptance fixture" width="1200" height="20"
              src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='20'%3E%3Crect width='1200' height='20' fill='%23168b82'/%3E%3C/svg%3E">
          `;
          bubble.append(answer);
          row.append(avatar, bubble);
          document.getElementById("messages").append(row);
          notifyContentUpdate();
        }"""
    )
    _settle_geometry(page)
    probe = page.evaluate(
        """() => {
          const answer = document.querySelector("#s12g-long-content .answer");
          const answerRect = answer.getBoundingClientRect();
          const tolerance = 1.5;
          const bounded = (selector) => {
            const element = answer.querySelector(selector);
            const rect = element.getBoundingClientRect();
            return {
              selector,
              left: rect.left,
              right: rect.right,
              width: rect.width,
              within_answer:
                rect.left >= answerRect.left - tolerance &&
                rect.right <= answerRect.right + tolerance &&
                rect.width <= answerRect.width + tolerance,
            };
          };
          const pre = answer.querySelector("pre");
          const table = answer.querySelector("table");
          return {
            answer_width: answerRect.width,
            bounded: [bounded("a"), bounded("code"), bounded("img")],
            pre: {
              client_width: pre.clientWidth,
              scroll_width: pre.scrollWidth,
              local_horizontal_scroll: pre.scrollWidth > pre.clientWidth,
            },
            table: {
              client_width: table.clientWidth,
              scroll_width: table.scrollWidth,
              local_horizontal_scroll: table.scrollWidth > table.clientWidth,
            },
          };
        }"""
    )
    oracle = _collect_oracle(
        page,
        target_selectors=VISIBLE_TARGET_SELECTORS,
    )
    defects = set(oracle["defect_codes"])
    containment_ok = all(item["within_answer"] for item in probe["bounded"])
    local_scroll_ok = (
        probe["pre"]["local_horizontal_scroll"]
        and probe["table"]["local_horizontal_scroll"]
    )
    if not containment_ok or not local_scroll_ok:
        defects.add("DOCUMENT_OVERFLOW")
    page.evaluate("() => document.getElementById('s12g-long-content')?.remove()")
    return {
        "status": "passed" if not defects else "failed",
        "defect_codes": _ordered_defects(defects),
        "content_geometry": probe,
        "oracle_geometry": oracle["geometry"],
    }


def _exercise_keyboard_and_rotation(page: Any) -> dict[str, Any]:
    input_locator = page.locator("#chat-input")
    acceptance_draft = "s12g-rotation-continuity"
    try:
        if page.evaluate("() => setPresentationState('conversation')") is not True:
            raise AcceptanceRuntimeError(
                "PRESENTATION_STATE_FAILURE",
                "The page rejected the conversation presentation state.",
            )
        input_locator.fill(acceptance_draft)
        input_locator.focus()
        prepared = page.evaluate(
            """() => {
              document.getElementById("rotation-sentinel")?.remove();
              const sentinel = document.createElement("div");
              sentinel.id = "rotation-sentinel";
              sentinel.dataset.acceptanceOnly = "true";
              sentinel.hidden = true;
              document.getElementById("messages").append(sentinel);
              return (
                setScrollIntent("detached") === true &&
                document.getElementById("messages").dataset.scrollIntent === "detached"
              );
            }"""
        )
        if prepared is not True:
            raise AcceptanceRuntimeError(
                "ROTATION_SETUP_FAILED",
                "The rotation continuity state could not be prepared.",
            )
        phases = [
            _rotation_phase_record(page, index, width, height)
            for index, (width, height) in enumerate(ROTATION_PHASE_VIEWPORTS)
        ]
        report = _evaluate_rotation_continuity(
            phases,
            _fingerprint(acceptance_draft),
        )
        report["simulation_scope"] = "viewport_resize_not_real_ime_or_device_keyboard"
        return report
    finally:
        page.evaluate(
            """() => {
              document.getElementById("rotation-sentinel")?.remove();
              const input = document.getElementById("chat-input");
              if (input) {
                input.value = "";
                input.dispatchEvent(new Event("input", { bubbles: true }));
              }
              setScrollIntent("following");
            }"""
        )


def _inject_stream_history_and_probe(page: Any, answer_index: int) -> None:
    _install_dom_marker_probe(page)
    page.evaluate(
        r"""({answer_index: answerIndex, target_selectors: targetSelectors}) => {
          window.__s12gStreamProbe?.observer?.disconnect();
          document.getElementById("welcome")?.remove();
          document.querySelectorAll('[data-s12g-history="true"]').forEach(
            (element) => element.remove(),
          );
          const messages = document.getElementById("messages");
          for (let index = 0; index < 48; index += 1) {
            const row = document.createElement("article");
            row.className = "message assistant";
            row.dataset.s12gHistory = "true";
            const avatar = document.createElement("div");
            avatar.className = "avatar";
            const bubble = document.createElement("div");
            bubble.className = "bubble";
            bubble.textContent = `acceptance history line ${index}`;
            row.append(avatar, bubble);
            messages.append(row);
          }
          messages.scrollTop = messages.scrollHeight;
          messages.dispatchEvent(new Event("scroll"));

          const state = {
            answerLengthChanges: [],
            answerFingerprints: [],
            lastAnswerLength: null,
            lastAnswerText: null,
            detachmentEnabled: false,
            detached: false,
            detachedAtLength: null,
            detachedBaseline: null,
            detachedSamples: [],
            targetSamples: [],
            anchor: null,
            sampleIndex: 0,
            pending: [],
          };
          const normalizeText = (value) => String(value)
            .replace(/\*\*(.+?)\*\*/g, "$1")
            .replace(/__(.+?)__/g, "$1")
            .replace(/`([^`]*)`/g, "$1")
            .replace(/\s+/g, " ")
            .trim();
          const currentAnswerText = () => {
            const answers = document.querySelectorAll(".answer");
            const answer = answers[answerIndex] || null;
            if (!answer) return "";
            const blockSelector = "h1,h2,h3,h4,h5,h6,p,li,pre,blockquote";
            const blocks = [...answer.querySelectorAll(blockSelector)].filter(
              (element) => !element.parentElement?.closest(blockSelector),
            );
            const value = blocks.length
              ? blocks.map((element) => element.textContent || "").join(" ")
              : answer.textContent || "";
            return normalizeText(value);
          };
          const sampleTargets = (sampleIndex) => {
            for (const selector of targetSelectors) {
              document.querySelectorAll(selector).forEach((element, elementIndex) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                if (
                  style.display !== "none" &&
                  style.visibility !== "hidden" &&
                  rect.width > 0 &&
                  rect.height > 0
                ) {
                  state.targetSamples.push({
                    sample_index: sampleIndex,
                    selector,
                    element_index: elementIndex,
                    width: rect.width,
                    height: rect.height,
                  });
                }
              });
            }
          };
          const detach = (length) => {
            const distance = Math.max(96, Math.round(messages.clientHeight * 0.4));
            messages.scrollTop = Math.max(0, messages.scrollTop - distance);
            messages.dispatchEvent(new Event("scroll"));
            const messagesRect = messages.getBoundingClientRect();
            const candidates = [
              ...messages.querySelectorAll('[data-s12g-history="true"]'),
            ];
            state.anchor = candidates.find((candidate) => {
              const rect = candidate.getBoundingClientRect();
              return (
                rect.bottom >= messagesRect.top + 4 &&
                rect.top <= messagesRect.bottom - 4
              );
            }) || candidates[0] || null;
            state.detached = messages.dataset.scrollIntent === "detached";
            state.detachedAtLength = length;
            state.detachedBaseline = {
              scroll_top: messages.scrollTop,
              anchor_top: state.anchor
                ? state.anchor.getBoundingClientRect().top
                : 0,
            };
          };
          const sample = (trigger) => {
            const sampleIndex = state.sampleIndex;
            state.sampleIndex += 1;
            const answerText = currentAnswerText();
            const answerLength = answerText.length;
            if (answerText !== state.lastAnswerText) {
              state.lastAnswerText = answerText;
              state.lastAnswerLength = answerLength;
              state.answerLengthChanges.push(answerLength);
              if (answerText) {
                const pending = crypto.subtle.digest(
                  "SHA-256",
                  new TextEncoder().encode(answerText),
                ).then(
                  (buffer) => {
                    state.answerFingerprints.push({
                      sample_index: sampleIndex,
                      length: answerLength,
                      sha256: [...new Uint8Array(buffer)]
                        .map((byte) => byte.toString(16).padStart(2, "0"))
                        .join(""),
                    });
                  },
                  () => {
                    state.answerFingerprints.push({
                      sample_index: sampleIndex,
                      length: answerLength,
                      sha256: null,
                    });
                  },
                );
                state.pending.push(pending);
              }
            }
            if (
              state.detachmentEnabled &&
              !state.detached &&
              answerLength > 0
            ) {
              detach(answerLength);
            }
            const record = {
              sample_index: sampleIndex,
              trigger,
              answer_length: answerLength,
              scroll_top: messages.scrollTop,
              anchor_top: state.anchor
                ? state.anchor.getBoundingClientRect().top
                : 0,
            };
            if (state.detached) state.detachedSamples.push(record);
            sampleTargets(sampleIndex);
            return record;
          };
          const handleMutations = (records) => {
            if (!records.length) return;
            sample("mutation_immediate");
            const pending = new Promise((resolve) => {
              requestAnimationFrame(() => {
                sample("mutation_first_frame");
                requestAnimationFrame(() => {
                  sample("mutation_second_frame");
                  resolve();
                });
              });
            });
            state.pending.push(pending);
          };
          const observer = new MutationObserver(handleMutations);
          observer.observe(messages, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
          });
          state.observer = observer;
          state.handleMutations = handleMutations;
          state.sample = sample;
          window.__s12gStreamProbe = state;
          sample("initial");
        }""",
        {
            "answer_index": answer_index,
            "target_selectors": list(VISIBLE_TARGET_SELECTORS),
        },
    )


def _enable_stream_detachment(page: Any) -> None:
    enabled = page.evaluate(
        """() => {
          const state = window.__s12gStreamProbe;
          if (!state) return false;
          state.detachmentEnabled = true;
          state.sample("detachment_enabled");
          return true;
        }"""
    )
    if enabled is not True:
        raise AcceptanceRuntimeError(
            "SSE_DETACHMENT_PROBE_ENABLE_FAILED",
            "The stream detachment probe could not be enabled.",
        )


def _stream_probe_result(page: Any) -> dict[str, Any] | None:
    return page.evaluate(
        """async () => {
          const state = window.__s12gStreamProbe;
          if (!state) return null;
          const settle = () => new Promise((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(resolve));
          });
          const drainPending = async () => {
            let awaited = 0;
            while (awaited < state.pending.length) {
              const batch = state.pending.slice(awaited);
              awaited = state.pending.length;
              await Promise.allSettled(batch);
            }
          };

          state.handleMutations(state.observer.takeRecords());
          await drainPending();
          const terminalPreDisconnect = state.sample("terminal_pre_disconnect");
          state.observer.disconnect();
          await settle();
          const terminalPostDisconnect = state.sample("terminal_post_disconnect");
          await drainPending();

          const sanitizeSample = (sample) => ({
            sample_index: sample.sample_index,
            trigger: sample.trigger,
            answer_length: sample.answer_length,
            scroll_top: sample.scroll_top,
            anchor_top: sample.anchor_top,
          });
          return {
            answer_length_changes: [...state.answerLengthChanges],
            answer_fingerprints: [...state.answerFingerprints]
              .sort((left, right) => left.sample_index - right.sample_index)
              .map((fingerprint) => ({
                sample_index: fingerprint.sample_index,
                length: fingerprint.length,
                sha256: fingerprint.sha256,
              })),
            detached: state.detached,
            detached_at_length: state.detachedAtLength,
            detached_baseline: state.detachedBaseline ? {
              scroll_top: state.detachedBaseline.scroll_top,
              anchor_top: state.detachedBaseline.anchor_top,
            } : null,
            detached_samples: state.detachedSamples.map(sanitizeSample),
            target_samples: state.targetSamples.map((sample) => ({
              sample_index: sample.sample_index,
              selector: sample.selector,
              element_index: sample.element_index,
              width: sample.width,
              height: sample.height,
            })),
            terminal_pre_disconnect: sanitizeSample(terminalPreDisconnect),
            terminal_post_disconnect: sanitizeSample(terminalPostDisconnect),
            pending_sample_count: state.pending.length,
          };
        }"""
    )


def _cleanup_stream_history(page: Any) -> None:
    page.evaluate(
        """() => {
          document.querySelectorAll('[data-s12g-history="true"]').forEach(
            (element) => element.remove(),
          );
          delete window.__s12gStreamProbe;
        }"""
    )


def _sampled_target_defects(
    target_summary: dict[str, Any],
    *,
    required_selectors: tuple[str, ...] = (),
) -> set[str]:
    required_missing = any(
        not isinstance(target_summary.get(selector), dict)
        or target_summary[selector].get("seen") is not True
        for selector in required_selectors
    )
    if required_missing or any(
        not isinstance(sample, dict) or sample.get("ever_below_44", True)
        for sample in target_summary.values()
    ):
        return {"TARGET_LT_44"}
    return set()


def _scan_visible_internal_markers(page: Any) -> list[str]:
    visible_text = page.evaluate("() => document.body.innerText")
    return [
        name
        for name, pattern in INTERNAL_MARKER_PATTERNS
        if re.search(pattern, visible_text, flags=re.IGNORECASE)
    ]


def _request_targets_stream_endpoint(
    request: Any,
    expected_endpoint: str,
) -> bool:
    try:
        request_url = urlparse(request.url)
        expected_url = urlparse(expected_endpoint)
        return bool(
            request.method == "POST"
            and request_url.scheme.lower() == expected_url.scheme.lower()
            and request_url.hostname == expected_url.hostname
            and request_url.port == expected_url.port
            and request_url.path == expected_url.path
            and not request_url.params
            and not request_url.query
            and not request_url.fragment
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _request_payload_matches_query(request: Any, query: str) -> bool:
    try:
        if not isinstance(request.post_data, str):
            return False
        payload = json.loads(request.post_data)
        return isinstance(payload, dict) and payload.get("query") == query
    except (AttributeError, TypeError, ValueError):
        return False


def _is_event_stream_content_type(content_type: Any) -> bool:
    return bool(
        isinstance(content_type, str)
        and content_type.split(";", 1)[0].strip().lower() == "text/event-stream"
    )


def _read_stream_response(response: Any) -> tuple[dict[str, Any], bytes | None]:
    report: dict[str, Any] = {
        "status": None,
        "content_type_is_event_stream": False,
        "finished": True,
        "body_read": False,
        "body_fingerprint": None,
        "failures": [],
    }
    raw_body: bytes | None = None
    try:
        report["status"] = response.status
        content_type = response.headers.get("content-type", "")
        report["content_type_is_event_stream"] = _is_event_stream_content_type(
            content_type
        )
    except Exception as error:
        report["failures"].append(
            {
                "code": "SSE_RESPONSE_METADATA_UNAVAILABLE",
                "exception_type": type(error).__name__,
            }
        )
    try:
        candidate_body = response.body()
        if not isinstance(candidate_body, bytes):
            raise TypeError("response body is not bytes")
        raw_body = candidate_body
        report["body_read"] = True
        report["body_fingerprint"] = {
            "length": len(raw_body),
            "sha256": hashlib.sha256(raw_body).hexdigest(),
        }
    except Exception as error:
        report["failures"].append(
            {
                "code": "SSE_RESPONSE_BODY_UNAVAILABLE",
                "exception_type": type(error).__name__,
            }
        )
    return report, raw_body


def _evaluate_answer_creation(before_count: int, after_count: int) -> dict[str, Any]:
    valid_counts = bool(
        isinstance(before_count, int)
        and not isinstance(before_count, bool)
        and before_count >= 0
        and isinstance(after_count, int)
        and not isinstance(after_count, bool)
        and after_count >= 0
    )
    created_count = after_count - before_count if valid_counts else None
    single_answer_created = valid_counts and created_count == 1
    return {
        "status": "passed" if single_answer_created else "failed",
        "answer_index": before_count if single_answer_created else None,
        "before_count": before_count,
        "after_count": after_count,
        "created_count": created_count,
        "checks": {"single_answer_created_for_request": single_answer_created},
    }


def _compare_rendered_markdown(
    page: Any,
    answer_text: str,
    answer_index: int | None,
) -> dict[str, Any]:
    expected_fingerprint = _fingerprint(_normalize_markdown_visible_text(answer_text))
    return page.evaluate(
        r"""async ({expected_fingerprint: expectedFingerprint, answer_index: answerIndex}) => {
          const normalizeText = (value) => String(value)
            .replace(/\*\*(.+?)\*\*/g, "$1")
            .replace(/__(.+?)__/g, "$1")
            .replace(/`([^`]*)`/g, "$1")
            .replace(/\s+/g, " ")
            .trim();
          const visibleText = (root) => {
            if (!root) return "";
            const parts = [];
            const visit = (node) => {
              if (node.nodeType === Node.TEXT_NODE) {
                if ((node.nodeValue || "").trim()) parts.push(node.nodeValue || "");
                return;
              }
              if (node.nodeType !== Node.ELEMENT_NODE) return;
              if (node.matches("h1,h2,h3,h4,h5,h6,p,li,pre,blockquote")) {
                parts.push(node.textContent || "");
                return;
              }
              node.childNodes.forEach(visit);
            };
            root.childNodes.forEach(visit);
            return normalizeText(parts.join(" "));
          };
          const digest = async (value) => {
            try {
              const buffer = await crypto.subtle.digest(
                "SHA-256",
                new TextEncoder().encode(value),
              );
              return [...new Uint8Array(buffer)]
                .map((byte) => byte.toString(16).padStart(2, "0"))
                .join("");
            } catch {
              return null;
            }
          };
          const canary = document.createElement("div");
          try {
            const canarySource = [
              "## 中文验收",
              "",
              "1. 有序一",
              "2. 有序二",
              "",
              "- 无序一",
              "- 无序二",
              "",
              "```text",
              "closed-fence",
              "```",
              "",
              "```",
              "unclosed-fence",
            ].join(String.fromCharCode(10));
            renderMarkdown(canary, canarySource);
            const ordered = [...canary.querySelectorAll("ol > li")].map(
              (element) => normalizeText(element.textContent || ""),
            );
            const unordered = [...canary.querySelectorAll("ul > li")].map(
              (element) => normalizeText(element.textContent || ""),
            );
            const code = [...canary.querySelectorAll("pre > code")].map(
              (element) => element.textContent || "",
            );
            const canaryChecks = {
              ordered_list_items:
                JSON.stringify(ordered) === JSON.stringify(["有序一", "有序二"]),
              unordered_list_items:
                JSON.stringify(unordered) === JSON.stringify(["无序一", "无序二"]),
              closed_fence: code[0] === "closed-fence",
              unclosed_fence: code[1] === "unclosed-fence",
              chinese_text: (canary.textContent || "").includes("中文验收"),
            };
            const answers = document.querySelectorAll(".answer");
            const rendered = Number.isInteger(answerIndex)
              ? answers[answerIndex] ?? null
              : null;
            const actualText = visibleText(rendered);
            const actualHash = await digest(actualText);
            const hashesComputed =
              Number.isInteger(expectedFingerprint?.length) &&
              /^[0-9a-f]{64}$/.test(expectedFingerprint?.sha256 || "") &&
              /^[0-9a-f]{64}$/.test(actualHash || "");
            const checks = {
              answer_present: Boolean(rendered),
              normalized_text_matches:
                hashesComputed &&
                actualText.length === expectedFingerprint.length &&
                actualHash === expectedFingerprint.sha256,
              hashes_computed: hashesComputed,
              markdown_canary: Object.values(canaryChecks).every(Boolean),
            };
            return {
              status: Object.values(checks).every(Boolean) ? "passed" : "failed",
              checks,
              canary: {
                status: Object.values(canaryChecks).every(Boolean)
                  ? "passed"
                  : "failed",
                checks: canaryChecks,
              },
              normalized_text: {
                expected: expectedFingerprint,
                actual: { length: actualText.length, sha256: actualHash },
              },
            };
          } finally {
            canary.remove();
          }
        }""",
        {
            "expected_fingerprint": expected_fingerprint,
            "answer_index": answer_index,
        },
    )


def _exercise_option_followup(
    page: Any,
    *,
    expected_endpoint: str,
    original_query: str,
    option_id: str | None,
    option_expected: bool,
    controls_ready: bool,
    initial_answer_count: int,
) -> dict[str, Any]:
    option_count = page.locator(".option-button").count()
    if not option_expected:
        return {
            "status": "not_applicable",
            "option_count": option_count,
            "request_count": 0,
            "checks": {},
        }
    if not controls_ready:
        return {
            "status": "blocked",
            "option_count": option_count,
            "request_count": 0,
            "checks": {},
        }

    checks = {
        "option_rendered": option_count > 0,
        "followup_observed": False,
        "original_query_reused": False,
        "entity_id_hint_matches": False,
        "duplicate_suppressed": False,
        "ordinary_request_observed": False,
        "ordinary_hint_absent": False,
    }
    if not isinstance(option_id, str) or not option_id.strip():
        return {
            "status": "failed",
            "option_count": option_count,
            "request_count": 0,
            "checks": checks,
            "failure": {"code": "OPTION_PUBLIC_ID_UNAVAILABLE"},
        }

    observed_payloads: list[dict[str, Any] | None] = []

    def observe_request(request: Any) -> None:
        try:
            if request.url != expected_endpoint or request.method.upper() != "POST":
                return
            payload = json.loads(request.post_data or "")
            observed_payloads.append(payload if isinstance(payload, dict) else None)
        except Exception:
            observed_payloads.append(None)

    page.on("request", observe_request)
    try:
        option_locator = page.locator(".option-button").first
        option_handle = option_locator.element_handle()
        if option_handle is None:
            return {
                "status": "failed",
                "option_count": option_count,
                "request_count": 0,
                "checks": checks,
                "failure": {"code": "OPTION_CONTROL_UNAVAILABLE"},
            }

        option_locator.click()
        page.wait_for_function(
            """(answerTarget) => {
              const submit = document.getElementById("chat-submit");
              return (
                !submit.disabled &&
                submit.textContent.trim() === "发送" &&
                document.querySelectorAll(".answer").length >= answerTarget
              );
            }""",
            arg=initial_answer_count + 1,
            timeout=SSE_TIMEOUT_MS,
        )
        followup_request_count = len(observed_payloads)
        option_handle.evaluate("(button) => button.click()")
        page.wait_for_timeout(300)
        duplicate_suppressed = (
            followup_request_count == 1 and len(observed_payloads) == 1
        )

        ordinary_query = "ordinary request without option"
        page.locator("#chat-input").fill(ordinary_query)
        page.locator("#chat-submit").click()
        page.wait_for_function(
            """(answerTarget) => {
              const submit = document.getElementById("chat-submit");
              return (
                !submit.disabled &&
                submit.textContent.trim() === "发送" &&
                document.querySelectorAll(".answer").length >= answerTarget
              );
            }""",
            arg=initial_answer_count + 2,
            timeout=SSE_TIMEOUT_MS,
        )

        followup_payload = observed_payloads[0] if observed_payloads else None
        ordinary_payload = observed_payloads[1] if len(observed_payloads) >= 2 else None
        checks.update(
            {
                "followup_observed": followup_request_count == 1,
                "original_query_reused": bool(
                    isinstance(followup_payload, dict)
                    and followup_payload.get("query") == original_query
                ),
                "entity_id_hint_matches": bool(
                    isinstance(followup_payload, dict)
                    and followup_payload.get("entity_id_hint") == option_id
                ),
                "duplicate_suppressed": duplicate_suppressed,
                "ordinary_request_observed": bool(
                    len(observed_payloads) == 2
                    and isinstance(ordinary_payload, dict)
                    and ordinary_payload.get("query") == ordinary_query
                ),
                "ordinary_hint_absent": bool(
                    isinstance(ordinary_payload, dict)
                    and "entity_id_hint" not in ordinary_payload
                ),
            }
        )
        report = {
            "status": "passed" if all(checks.values()) else "failed",
            "option_count": option_count,
            "request_count": len(observed_payloads),
            "checks": checks,
        }
        if report["status"] == "failed":
            report["failure"] = {"code": "OPTION_FOLLOWUP_CHECK_FAILED"}
        return report
    except Exception as error:
        return {
            "status": "failed",
            "option_count": option_count,
            "request_count": len(observed_payloads),
            "checks": checks,
            "failure": {
                "code": "OPTION_FOLLOWUP_EXECUTION_FAILED",
                "exception_type": type(error).__name__,
            },
        }
    finally:
        page.remove_listener("request", observe_request)


def _run_real_sse(page: Any, query: str) -> dict[str, Any]:
    attached_listeners: list[tuple[str, Any]] = []
    try:
        return _run_real_sse_round(page, query, attached_listeners)
    finally:
        for event_name, listener in reversed(attached_listeners):
            try:
                page.remove_listener(event_name, listener)
            except Exception:
                pass


def _run_real_sse_round(
    page: Any,
    query: str,
    attached_listeners: list[tuple[str, Any]],
) -> dict[str, Any]:
    deadline = time.monotonic() + (SSE_TIMEOUT_MS / 1_000)
    target_requests: list[Any] = []
    primary_request: Any | None = None
    primary_responses: list[Any] = []
    request_finished = False
    request_failed = False
    request_failure: dict[str, str] | None = None
    page_location = urlparse(page.url)
    if page_location.scheme not in {"http", "https"} or not page_location.netloc:
        raise AcceptanceRuntimeError(
            "SSE_PAGE_ORIGIN_INVALID",
            "The chat page does not have a valid HTTP origin.",
        )
    expected_endpoint = (
        f"{page_location.scheme}://{page_location.netloc}/api/chat/stream"
    )

    def observe_request(request: Any) -> None:
        nonlocal primary_request
        if not _request_targets_stream_endpoint(request, expected_endpoint):
            return
        target_requests.append(request)
        if primary_request is None:
            primary_request = request

    def observe_response(response: Any) -> None:
        try:
            if response.request is primary_request:
                primary_responses.append(response)
        except Exception:
            return

    def observe_request_finished(request: Any) -> None:
        nonlocal request_finished
        if request is primary_request:
            request_finished = True

    def observe_request_failed(request: Any) -> None:
        nonlocal request_failed, request_failure
        if request is not primary_request:
            return
        request_failed = True
        try:
            failure = request.failure
            exception_type = (
                type(failure).__name__
                if failure is not None
                else "UnknownRequestFailure"
            )
        except Exception as error:
            exception_type = type(error).__name__
        request_failure = {
            "code": "SSE_REQUEST_FAILED",
            "exception_type": exception_type,
        }

    listeners = (
        ("request", observe_request),
        ("response", observe_response),
        ("requestfinished", observe_request_finished),
        ("requestfailed", observe_request_failed),
    )
    for event_name, listener in listeners:
        page.on(event_name, listener)
        attached_listeners.append((event_name, listener))

    answer_count_before = 0
    answer_count_after = 0
    pending_seen = False
    streaming_frame_observed = False
    streaming_control_observations: list[dict[str, Any]] = []

    def round_state() -> dict[str, Any]:
        state = page.evaluate(
            """(answerCountBefore) => {
              const submit = document.getElementById("chat-submit");
              const answers = [...document.querySelectorAll(".answer")]
                .slice(answerCountBefore);
              const visibleAnswer = answers.some((answer) => {
                const style = getComputedStyle(answer);
                const rect = answer.getBoundingClientRect();
                return (
                  (answer.textContent || "").trim().length > 0 &&
                  style.display !== "none" &&
                  style.visibility !== "hidden" &&
                  rect.width > 0 &&
                  rect.height > 0
                );
              });
              const pending = Boolean(
                submit?.disabled && submit.textContent.trim() === "检索中"
              );
              return {
                pending_seen:
                  window.__s12gSubmitPendingProbe?.seen === true,
                pending,
                restored: Boolean(
                  submit &&
                  !submit.disabled &&
                  submit.textContent.trim() === "发送"
                ),
                streaming_frame: pending && visibleAnswer,
              };
            }""",
            answer_count_before,
        )
        return state if isinstance(state, dict) else {}

    try:
        page.evaluate("() => setPresentationState('conversation')")
        answer_count_before = page.locator(".answer").count()
        _inject_stream_history_and_probe(page, answer_count_before)
        pending_probe_installed = page.evaluate(
            """() => {
              window.__s12gSubmitPendingProbe?.observer?.disconnect();
              const submit = document.getElementById("chat-submit");
              if (!submit) return false;
              const state = { seen: false, observer: null };
              const sample = () => {
                if (submit.disabled && submit.textContent.trim() === "检索中") {
                  state.seen = true;
                }
              };
              const observer = new MutationObserver(sample);
              observer.observe(submit, {
                attributes: true,
                childList: true,
                subtree: true,
                characterData: true,
              });
              state.observer = observer;
              window.__s12gSubmitPendingProbe = state;
              sample();
              return true;
            }"""
        )
        if pending_probe_installed is not True:
            raise AcceptanceRuntimeError(
                "SSE_PENDING_PROBE_INSTALL_FAILED",
                "The stream pending-state probe could not be installed.",
            )
        page.locator("#chat-input").fill(query)
        page.locator("#chat-submit").click()

        while True:
            state = round_state()
            pending_seen = state.get("pending_seen") is True
            if pending_seen or request_failed:
                break
            page.wait_for_timeout(min(25, _remaining_timeout_ms(deadline)))

        while True:
            state = round_state()
            if state.get("streaming_frame") is True:
                streaming_frame_observed = True
                break
            if state.get("restored") is True or request_failed:
                break
            page.wait_for_timeout(min(25, _remaining_timeout_ms(deadline)))

        if streaming_frame_observed:
            streaming_control_observations = _actionable_control_observations(
                page,
                "conversation",
                required_controls=(".process-stop",),
            )
            _enable_stream_detachment(page)
            while True:
                state = round_state()
                if state.get("restored") is True or request_failed:
                    break
                page.wait_for_timeout(min(25, _remaining_timeout_ms(deadline)))

        while not request_finished and not request_failed:
            page.wait_for_timeout(min(25, _remaining_timeout_ms(deadline)))

        _settle_geometry(page)
        page.wait_for_timeout(min(500, _remaining_timeout_ms(deadline)))
        answer_count_after = page.locator(".answer").count()
    finally:
        try:
            page.evaluate(
                """() => {
                  window.__s12gSubmitPendingProbe?.observer?.disconnect();
                  delete window.__s12gSubmitPendingProbe;
                }"""
            )
        except Exception:
            pass

    answer_creation = _evaluate_answer_creation(
        answer_count_before,
        answer_count_after,
    )
    answer_index = answer_creation["answer_index"]
    response_failures: list[dict[str, str]] = []
    response_report: dict[str, Any] = {
        "primary_request_observed": primary_request is not None,
        "primary_response_count": len(primary_responses),
        "request_finished": request_finished,
        "request_failed": request_failed,
        "request_failure": request_failure,
        "status": None,
        "content_type_is_event_stream": False,
        "finished": False,
        "body_read": False,
        "body_fingerprint": None,
        "failures": response_failures,
    }
    raw_body: bytes | None = None
    if len(primary_responses) == 1 and request_finished:
        observed_response, raw_body = _read_stream_response(primary_responses[0])
        observed_failures = observed_response.pop("failures", [])
        response_report.update(observed_response)
        if isinstance(observed_failures, list):
            response_failures.extend(observed_failures)
        response_report["failures"] = response_failures

    events: list[dict[str, Any]] = []
    raw_answer = ""
    expected_prefixes: list[dict[str, Any]] = []
    control_expectations = {"streaming": [], "terminal": []}
    sse_report: dict[str, Any] = {
        "status": "failed",
        "failure": {"code": "SSE_RESPONSE_BODY_UNAVAILABLE"},
        "control_expectations": control_expectations,
    }

    def append_expected_prefix(value: str) -> None:
        visible_text = _normalize_markdown_visible_text(value)
        if not visible_text:
            return
        fingerprint = _fingerprint(visible_text)
        if not expected_prefixes or expected_prefixes[-1] != fingerprint:
            expected_prefixes.append(fingerprint)

    if raw_body is not None:
        try:
            events = _parse_sse_body(raw_body)
            sse_report = _evaluate_sse_events(events)
            derived_controls = sse_report["control_expectations"]
            control_expectations = {
                "streaming": list(derived_controls["streaming"]),
                "terminal": list(derived_controls["terminal"]),
            }

            chunk_prefix = ""
            for event in events:
                if event.get("name") != "answer_chunk":
                    continue
                data = event.get("data")
                chunk_text = data.get("text") if isinstance(data, dict) else None
                if not isinstance(chunk_text, str):
                    continue
                previous_length = len(chunk_prefix)
                chunk_prefix += chunk_text
                for boundary in re.finditer(r"\r\n|\r|\n", chunk_prefix):
                    if boundary.end() > previous_length:
                        append_expected_prefix(chunk_prefix[: boundary.end()])
                append_expected_prefix(chunk_prefix)

            answer_payloads = [
                event["data"]
                for event in events
                if event.get("name") == "answer" and isinstance(event.get("data"), dict)
            ]
            if len(answer_payloads) == 1:
                answer_value = answer_payloads[0].get("answer_text")
                if isinstance(answer_value, str):
                    raw_answer = answer_value
                    append_expected_prefix(raw_answer)
        except AcceptanceRuntimeError as error:
            sse_report = {
                "status": "failed",
                "failure": {
                    "code": error.code,
                    "exception_type": type(error).__name__,
                },
                "control_expectations": control_expectations,
            }
        except Exception as error:
            sse_report = {
                "status": "failed",
                "failure": {
                    "code": "SSE_EVALUATION_FAILED",
                    "exception_type": type(error).__name__,
                },
                "control_expectations": control_expectations,
            }

    progressive_answer_chunk_observed = any(
        event.get("name") == "answer_chunk" for event in events
    )
    streaming_required_controls = tuple(control_expectations["streaming"])
    if streaming_frame_observed and streaming_required_controls:
        streaming_actionability = _evaluate_actionable_controls(
            "conversation",
            streaming_control_observations,
            required_controls=streaming_required_controls,
        )
    else:
        streaming_actionability = {
            "status": "passed",
            "defect_codes": [],
            "required_controls": [],
            "controls": {},
        }
    terminal_dynamic_controls = tuple(control_expectations["terminal"])
    sampled_required_controls = (
        *(streaming_required_controls if streaming_frame_observed else ()),
        *terminal_dynamic_controls,
    )

    markdown_report = _compare_rendered_markdown(page, raw_answer, answer_index)
    stream_probe = _stream_probe_result(page)
    observed_prefixes = (
        stream_probe.get("answer_fingerprints", [])
        if isinstance(stream_probe, dict)
        else []
    )
    incremental_report = _evaluate_incremental_prefixes(
        expected_prefixes,
        observed_prefixes if isinstance(observed_prefixes, list) else [],
    )
    detached_baseline = (
        stream_probe.get("detached_baseline")
        if isinstance(stream_probe, dict)
        else None
    )
    detached_samples = (
        stream_probe.get("detached_samples", [])
        if isinstance(stream_probe, dict)
        else []
    )
    if streaming_frame_observed:
        detached_report = _evaluate_detached_samples(
            detached_baseline if isinstance(detached_baseline, dict) else {},
            detached_samples if isinstance(detached_samples, list) else [],
        )
    else:
        detached_report = {
            "status": "passed",
            "defect_codes": [],
            "checks": {
                "applicable": False,
                "valid_sample_shape": True,
                "all_samples_within_tolerance": True,
            },
            "sample_count": 0,
            "max_scroll_delta": None,
            "max_scroll_delta_index": None,
            "max_anchor_delta": None,
            "max_anchor_delta_index": None,
            "terminal_scroll_delta": None,
            "terminal_anchor_delta": None,
        }
    target_samples = (
        stream_probe.get("target_samples", []) if isinstance(stream_probe, dict) else []
    )
    target_summary = _summarize_target_samples(
        target_samples if isinstance(target_samples, list) else [],
        VISIBLE_TARGET_SELECTORS,
    )

    answer = ""
    if isinstance(answer_index, int):
        answer_locator = page.locator(".answer").nth(answer_index)
        if answer_locator.count() == 1:
            answer = answer_locator.text_content() or ""
    before_return = page.evaluate(
        """() => {
          const messages = document.getElementById("messages");
          const button = document.getElementById("back-to-latest");
          const style = getComputedStyle(button);
          return {
            scroll_intent: messages.dataset.scrollIntent,
            button_visible:
              !button.hidden &&
              style.display !== "none" &&
              style.visibility !== "hidden",
            distance_to_bottom:
              messages.scrollHeight - messages.clientHeight - messages.scrollTop,
          };
        }"""
    )
    before_return = before_return if isinstance(before_return, dict) else {}
    answer_lengths = (
        stream_probe.get("answer_length_changes", [])
        if isinstance(stream_probe, dict)
        else []
    )
    detached_at_length = (
        stream_probe.get("detached_at_length")
        if isinstance(stream_probe, dict)
        else None
    )
    if streaming_frame_observed:
        progressive_growth = bool(
            isinstance(answer_lengths, list)
            and len(answer_lengths) >= 2
            and any(
                current > previous
                for previous, current in zip(answer_lengths, answer_lengths[1:])
            )
        )
        grew_after_detach = bool(
            isinstance(detached_at_length, (int, float))
            and not isinstance(detached_at_length, bool)
            and any(
                isinstance(sample, dict)
                and isinstance(sample.get("answer_length"), (int, float))
                and sample["answer_length"] > detached_at_length
                for sample in detached_samples
            )
        )
        back_button_ready = bool(
            before_return.get("scroll_intent") == "detached"
            and before_return.get("button_visible") is True
        )
    else:
        progressive_growth = False
        grew_after_detach = False
        back_button_ready = False
    detached_stable = bool(
        streaming_frame_observed and detached_report["status"] == "passed"
    )

    if streaming_frame_observed and back_button_ready:
        page.locator("#back-to-latest").click()
        page.wait_for_function(
            """() => {
              const messages = document.getElementById("messages");
              const button = document.getElementById("back-to-latest");
              return (
                messages.dataset.scrollIntent === "following" &&
                button.hidden &&
                messages.scrollHeight - messages.clientHeight -
                  messages.scrollTop <= 2
              );
            }""",
            timeout=_remaining_timeout_ms(deadline),
        )
    after_return = page.evaluate(
        """() => {
          const messages = document.getElementById("messages");
          const button = document.getElementById("back-to-latest");
          return {
            scroll_intent: messages.dataset.scrollIntent,
            button_hidden: button.hidden,
            distance_to_bottom:
              messages.scrollHeight - messages.clientHeight - messages.scrollTop,
          };
        }"""
    )
    after_return = after_return if isinstance(after_return, dict) else {}
    return_restored = bool(
        streaming_frame_observed
        and after_return.get("scroll_intent") == "following"
        and after_return.get("button_hidden") is True
        and isinstance(after_return.get("distance_to_bottom"), (int, float))
        and after_return["distance_to_bottom"] <= 2
    )
    dom_marker_report = _evaluate_dom_marker_latches(_dom_marker_probe_result(page))
    _cleanup_stream_history(page)
    _settle_geometry(page)
    oracle = _collect_oracle(
        page,
        target_selectors=VISIBLE_TARGET_SELECTORS,
    )
    internal_markers = _scan_visible_internal_markers(page)
    actionability = _terminal_actionable_controls(
        page,
        required_dynamic_controls=terminal_dynamic_controls,
    )
    sampled_target_defects = _sampled_target_defects(
        target_summary,
        required_selectors=sampled_required_controls,
    )
    terminal_summary = page.locator(".process-summary summary")
    terminal_summary_text = ""
    if terminal_summary.count() > 0:
        terminal_summary_text = terminal_summary.last.text_content() or ""
    submit_restored = page.locator("#chat-submit").is_enabled()

    request_count = len(target_requests)
    request_count_is_one = request_count == 1
    unique_request_payload_matches_query = bool(
        request_count_is_one
        and _request_payload_matches_query(target_requests[0], query)
    )
    network_failures: list[dict[str, str]] = []
    if not request_count_is_one:
        network_failures.append({"code": "SSE_REQUEST_MATCH_COUNT"})
    elif not unique_request_payload_matches_query:
        network_failures.append({"code": "SSE_REQUEST_PAYLOAD_INVALID"})
    if len(primary_responses) != 1:
        network_failures.append({"code": "SSE_RESPONSE_MATCH_COUNT"})
    if request_failed:
        network_failures.append(
            request_failure
            or {
                "code": "SSE_REQUEST_FAILED",
                "exception_type": "UnknownRequestFailure",
            }
        )
    response_failures[:0] = network_failures
    response_report.update(
        {
            "target_request_count": request_count,
            "duplicate_target_request_count": max(0, request_count - 1),
            "request_count_is_one": request_count_is_one,
            "unique_request_payload_matches_query": (
                unique_request_payload_matches_query
            ),
            "matched_request_count": request_count,
            "duplicate_request_count": max(0, request_count - 1),
            "primary_request_observed": primary_request is not None,
            "primary_response_count": len(primary_responses),
            "request_finished": request_finished,
            "request_failed": request_failed,
            "request_failure": request_failure,
            "failures": response_failures,
        }
    )

    defects = set(oracle["defect_codes"])
    defects.update(detached_report["defect_codes"])
    defects.update(sampled_target_defects)
    defects.update(streaming_actionability["defect_codes"])
    defects.update(actionability["defect_codes"])
    response_unique = bool(
        request_count_is_one
        and unique_request_payload_matches_query
        and len(primary_responses) == 1
        and not request_failed
    )
    response_ok = bool(
        response_unique
        and request_finished
        and response_report["status"] == 200
        and response_report["content_type_is_event_stream"]
        and response_report["finished"]
        and response_report["body_read"]
        and not response_report["failures"]
    )
    checks = {
        "unique_matching_stream_response": response_unique,
        "real_sse_response": response_ok,
        "raw_sse_contract_and_order": sse_report["status"] == "passed",
        "raw_answer_available": bool(raw_answer),
        "single_answer_created_for_request": answer_creation["status"] == "passed",
        "rendered_markdown_matches_raw_answer": markdown_report["status"] == "passed",
        "incremental_answer_prefixes": incremental_report["status"] == "passed",
        "no_dom_mutation_markers": dom_marker_report["status"] == "passed",
        "progressive_answer_chunk_observed": progressive_answer_chunk_observed,
        "streaming_frame_observed": streaming_frame_observed,
        "progressive_answer_growth": progressive_growth,
        "grew_after_detach": grew_after_detach,
        "detached_scroll_and_anchor_stable": detached_stable,
        "stream_targets_never_below_44": not sampled_target_defects,
        "back_to_latest_visible_while_detached": back_button_ready,
        "back_to_latest_restored_following": return_restored,
        "submit_restored": submit_restored,
        "terminal_process_summary": terminal_summary_text.strip() == "查看检索过程",
        "answer_nonempty": bool(answer.strip()),
        "no_visible_internal_markers": not internal_markers,
        "streaming_controls_actionable": (
            streaming_actionability["status"] == "passed"
        ),
        "terminal_controls_actionable": actionability["status"] == "passed",
    }
    passed = all(checks.values()) and not defects
    if not passed and not defects:
        defects.add("VIEWPORT_RUNTIME_FAILURE")
    return {
        "status": "passed" if passed else "failed",
        "defect_codes": _ordered_defects(defects),
        "query": _fingerprint(query),
        "answer": _fingerprint(answer),
        "response": response_report,
        "sse_contract": sse_report,
        "control_expectations": control_expectations,
        "answer_creation": answer_creation,
        "markdown_consistency": markdown_report,
        "incremental_prefixes": incremental_report,
        "dom_marker_latches": dom_marker_report,
        "streaming_actionable_controls": streaming_actionability,
        "actionable_controls": actionability,
        "checks": checks,
        "stream_probe": stream_probe,
        "target_summary": target_summary,
        "detached_oracle": detached_report,
        "terminal_oracle": oracle,
        "before_return": before_return,
        "after_return": after_return,
        "visible_internal_marker_kinds": internal_markers,
    }


def _run_production(
    browser: Any,
    url: str,
    query: str,
    run_dir: Path,
    console_events: list[dict[str, Any]],
) -> dict[str, Any]:
    viewport_records: list[dict[str, Any]] = []
    real_sse: dict[str, Any] | None = None
    all_defects: set[str] = set()
    all_passed = True

    for width, height in VIEWPORT_MATRIX:
        label = f"viewport-{width}x{height}"
        context = None
        page = None
        record: dict[str, Any] = {
            "viewport": {"width": width, "height": height},
        }
        defects: set[str] = set()
        record_passed = True
        shared_bootstrap_started = False
        shared_bootstrap_complete = False
        abort_after_record = False
        try:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            _attach_sanitized_console(page, label, console_events)
            shared_bootstrap_started = True
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            page.wait_for_selector(".shell[data-presentation-state]")
            page.wait_for_function(
                "() => document.getElementById('demo-grid')?.getAttribute('aria-busy') === 'false'",
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            shared_bootstrap_complete = True
            presentation = _exercise_presentation_states(page)
            record["presentation"] = presentation
            presentation_defects = set(presentation["defect_codes"])
            defects.update(presentation_defects)
            presentation_passed = presentation["status"] == "passed"
            if not presentation_passed and not presentation_defects:
                defects.add("VIEWPORT_RUNTIME_FAILURE")
            record_passed = record_passed and presentation_passed

            if (width, height) in LONG_CONTENT_VIEWPORTS:
                long_content = _inject_and_probe_long_content(page)
                record["long_content"] = long_content
                long_content_defects = set(long_content["defect_codes"])
                defects.update(long_content_defects)
                long_content_passed = long_content["status"] == "passed"
                if not long_content_passed and not long_content_defects:
                    defects.add("VIEWPORT_RUNTIME_FAILURE")
                record_passed = record_passed and long_content_passed

            if (width, height) == SSE_VIEWPORT:
                geometry_simulations = _exercise_keyboard_and_rotation(page)
                record["geometry_simulations"] = geometry_simulations
                geometry_defects = set(geometry_simulations["defect_codes"])
                defects.update(geometry_defects)
                geometry_passed = geometry_simulations["status"] == "passed"
                if not geometry_passed and not geometry_defects:
                    defects.add("VIEWPORT_RUNTIME_FAILURE")
                record_passed = record_passed and geometry_passed

                real_sse = _run_real_sse(page, query)
                sse_defects = set(real_sse["defect_codes"])
                defects.update(sse_defects)
                sse_passed = real_sse["status"] == "passed"
                if not sse_passed and not sse_defects:
                    defects.add("VIEWPORT_RUNTIME_FAILURE")
                record_passed = record_passed and sse_passed

            if not record_passed or defects:
                record["screenshot"] = _capture_failure(
                    page,
                    run_dir / f"{label}-failure.png",
                )
        except Exception as error:
            if (
                not viewport_records
                and shared_bootstrap_started
                and not shared_bootstrap_complete
            ):
                abort_after_record = True
            record_passed = False
            defects.add("VIEWPORT_RUNTIME_FAILURE")
            record["failure"] = {
                "code": "VIEWPORT_RUNTIME_FAILURE",
                "exception_type": type(error).__name__,
            }
            record["screenshot"] = _capture_failure(
                page,
                run_dir / f"{label}-failure.png",
            )
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception as error:
                    record_passed = False
                    defects.add("VIEWPORT_RUNTIME_FAILURE")
                    record["cleanup_failure"] = {
                        "code": "VIEWPORT_CLEANUP_FAILURE",
                        "exception_type": type(error).__name__,
                    }
                    if "screenshot" not in record:
                        record["screenshot"] = _capture_failure(
                            page,
                            run_dir / f"{label}-failure.png",
                        )

        record["defect_codes"] = _ordered_defects(defects)
        record["status"] = "passed" if record_passed and not defects else "failed"
        if record["status"] == "failed":
            all_passed = False
        all_defects.update(defects)
        viewport_records.append(record)
        if abort_after_record:
            break

    if real_sse is None:
        all_passed = False
        all_defects.add("VIEWPORT_RUNTIME_FAILURE")
    elif real_sse["status"] != "passed":
        all_passed = False
        if not real_sse["defect_codes"]:
            all_defects.add("VIEWPORT_RUNTIME_FAILURE")
    return {
        **_production_observation_provenance(),
        "status": "passed" if all_passed else "failed",
        "defect_codes": _ordered_defects(all_defects),
        "viewports": viewport_records,
        "real_sse": real_sse,
    }


def _looks_like_missing_browser(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "executable doesn't exist" in message
        or "browser was not found" in message
        or "failed to launch" in message
        and "executable" in message
    )


def _execute_browser(
    args: argparse.Namespace,
    run_dir: Path,
    console_events: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except (ImportError, ModuleNotFoundError) as error:
        raise AcceptanceRuntimeError(
            "PLAYWRIGHT_PACKAGE_UNAVAILABLE",
            "Playwright is unavailable; no package installation was attempted.",
        ) from error

    try:
        with sync_playwright() as playwright:
            browser = None
            try:
                browser_type = getattr(playwright, args.browser)
                browser = browser_type.launch(headless=True)
                if args.self_test:
                    return _run_self_test(browser, run_dir, console_events)
                return _run_production(
                    browser,
                    args.url,
                    args.real_sse_query,
                    run_dir,
                    console_events,
                )
            finally:
                if browser is not None:
                    browser.close()
    except AcceptanceRuntimeError:
        raise
    except Exception as error:
        if _looks_like_missing_browser(error):
            raise AcceptanceRuntimeError(
                "BROWSER_EXECUTABLE_UNAVAILABLE",
                "Chromium is unavailable; no browser installation was attempted.",
            ) from error
        raise


def main(argv: list[str] | None = None) -> int:
    """Run self-test or production acceptance and persist sanitized evidence."""
    args = _parse_args(argv)
    run_dir = _create_run_directory(args.output_dir)
    started_at = datetime.now(UTC)
    console_events: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "schema_version": 1,
        "mode": "self-test" if args.self_test else "production",
        "browser": args.browser,
        "status": "running",
        "started_at": started_at.isoformat(),
        "query": None if args.self_test else _fingerprint(args.real_sse_query),
        "defect_codes": [],
    }
    if not args.self_test:
        summary.update(_production_observation_provenance())
    exit_code = 1
    try:
        result = _execute_browser(args, run_dir, console_events)
        summary["result"] = result
        summary["defect_codes"] = result["defect_codes"]
        summary["status"] = result["status"]
        exit_code = 0 if result["status"] == "passed" else 1
    except AcceptanceRuntimeError as error:
        summary["status"] = "failed"
        summary["failure"] = {"type": error.code}
        print(
            f"S12G browser acceptance failed: {error.public_message}", file=sys.stderr
        )
    except Exception as error:
        summary["status"] = "failed"
        summary["failure"] = {"type": type(error).__name__}
        print(
            "S12G browser acceptance failed with an unexpected runtime error; "
            "raw error text was not persisted.",
            file=sys.stderr,
        )
    finally:
        summary["finished_at"] = datetime.now(UTC).isoformat()
        try:
            _commit_artifacts(run_dir, console_events, summary)
        except Exception:
            exit_code = 1
            print(
                "S12G browser acceptance could not commit sanitized artifacts; "
                "summary.json was not published as a commit marker.",
                file=sys.stderr,
            )
        print(f"S12G browser acceptance artifacts: {run_dir}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
