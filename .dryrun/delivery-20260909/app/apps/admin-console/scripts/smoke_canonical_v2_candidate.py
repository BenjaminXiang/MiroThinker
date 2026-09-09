"""Black-box transport smoke for one explicit Canonical V2 candidate URL."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from http.cookiejar import CookieJar
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    ProxyHandler,
    Request,
    build_opener,
)


_MAX_QUERIES = 10
_MAX_QUERY_CHARS = 500
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_TRACE_ITEMS = 100


class SmokeContractError(RuntimeError):
    """The candidate transport or bounded V2 trace violated the smoke contract."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
    except ValueError as exc:
        raise SmokeContractError("base URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SmokeContractError("base URL must be one explicit HTTP origin")
    return urlunsplit((parsed.scheme, parsed.netloc, "/api/chat", "", ""))


def _non_empty_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SmokeContractError(f"{label} must be non-empty text")
    return value


def _bounded_list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_TRACE_ITEMS:
        raise SmokeContractError(f"{label} must contain 1..{_MAX_TRACE_ITEMS} items")
    return value


def _validate_trace(
    payload: object,
    *,
    expected_release_id: str,
    expected_query: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SmokeContractError("chat response must be a JSON object")
    if payload.get("query") != expected_query:
        raise SmokeContractError("chat response did not echo the issued query")
    query_type = _non_empty_text(payload.get("query_type"), label="query_type")
    if not query_type.startswith("canonical_v2:"):
        raise SmokeContractError("query_type is not Canonical V2")
    structured = payload.get("structured_payload")
    if not isinstance(structured, dict):
        raise SmokeContractError("chat response lacks structured payload")
    trace = structured.get("canonical_v2")
    if not isinstance(trace, dict):
        raise SmokeContractError("chat response lacks a Canonical V2 trace")
    if trace.get("release_id") != expected_release_id:
        raise SmokeContractError("chat response crossed the expected release")
    plan_id = _non_empty_text(trace.get("plan_id"), label="plan_id")
    _non_empty_text(trace.get("plan_version"), label="plan_version")
    lanes = _bounded_list(trace.get("lanes"), label="lanes")
    retrieval_traces = _bounded_list(
        trace.get("retrieval_traces"), label="retrieval_traces"
    )
    evidence_ids = _bounded_list(trace.get("evidence_ids"), label="evidence_ids")
    claims = _bounded_list(trace.get("claims"), label="claims")
    mappings = _bounded_list(
        trace.get("claim_evidence_mappings"), label="claim_evidence_mappings"
    )
    evidence = _bounded_list(payload.get("evidence"), label="evidence")
    if not all(isinstance(lane, str) and lane for lane in lanes):
        raise SmokeContractError("lanes contain an invalid value")
    if not all(isinstance(item, str) and item for item in evidence_ids):
        raise SmokeContractError("evidence_ids contain an invalid value")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise SmokeContractError("evidence_ids must be unique")
    if not all(isinstance(item, dict) for item in retrieval_traces):
        raise SmokeContractError("retrieval_traces contain an invalid value")
    if not all(isinstance(item, dict) for item in (*claims, *mappings, *evidence)):
        raise SmokeContractError("evidence or claim trace contains an invalid value")
    evidence_set = set(evidence_ids)
    response_evidence_ids = {
        item.get("evidence_id") for item in evidence if isinstance(item, dict)
    }
    if response_evidence_ids != evidence_set:
        raise SmokeContractError("response evidence and trace evidence drifted")
    for item in (*claims, *mappings):
        references = item.get("evidence_ids")
        if not isinstance(references, list) or not set(references) <= evidence_set:
            raise SmokeContractError("claim evidence closure drifted")
    return {
        "release_id": expected_release_id,
        "plan_id": plan_id,
        "lane_count": len(lanes),
        "evidence_count": len(evidence_ids),
        "claim_count": len(claims),
    }


def run_smoke(
    *,
    base_url: str,
    expected_release_id: str,
    queries: Sequence[str],
) -> tuple[dict[str, Any], ...]:
    """Run bounded queries through one cookie session and validate V2 trace identity."""

    endpoint = _endpoint(base_url)
    _non_empty_text(expected_release_id, label="expected_release_id")
    if not 1 <= len(queries) <= _MAX_QUERIES:
        raise SmokeContractError(f"queries must contain 1..{_MAX_QUERIES} items")
    normalized: list[str] = []
    for query in queries:
        if (
            not isinstance(query, str)
            or not 1 <= len(query.strip()) <= _MAX_QUERY_CHARS
        ):
            raise SmokeContractError(
                f"each query must contain 1..{_MAX_QUERY_CHARS} characters"
            )
        normalized.append(query.strip())

    opener = build_opener(
        ProxyHandler({}),
        _NoRedirect(),
        HTTPCookieProcessor(CookieJar()),
    )
    results: list[dict[str, Any]] = []
    for query in normalized:
        request = Request(
            endpoint,
            data=json.dumps(
                {"query": query, "entity_id_hint": None},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=10) as response:
                if response.status != 200:
                    raise SmokeContractError("candidate chat did not return HTTP 200")
                if response.geturl() != endpoint:
                    raise SmokeContractError("candidate chat left the explicit origin")
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except SmokeContractError:
            raise
        except (HTTPError, URLError, OSError) as exc:
            raise SmokeContractError("candidate chat request failed") from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise SmokeContractError("candidate chat response exceeded the size bound")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeContractError(
                "candidate chat response was not valid JSON"
            ) from exc
        results.append(
            _validate_trace(
                payload,
                expected_release_id=expected_release_id,
                expected_query=query,
            )
        )
    return tuple(results)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke one explicit Canonical V2 candidate release."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-release-id", required=True)
    parser.add_argument("--query", action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        results = run_smoke(
            base_url=args.base_url,
            expected_release_id=args.expected_release_id,
            queries=tuple(args.query),
        )
    except SmokeContractError:
        raise SystemExit("Canonical V2 candidate smoke rejected") from None
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
