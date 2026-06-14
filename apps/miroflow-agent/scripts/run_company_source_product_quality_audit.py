#!/usr/bin/env python3
"""Audit batch-scoped source-backed company products for quality risks."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.enrichment_batch import review_enrichment_item  # noqa: E402
from src.data_agents.company.news_connectors import (  # noqa: E402
    NewsRecord,
    YiouSearchContext,
)
from src.data_agents.company.news_connectors.iyiou import (  # noqa: E402
    _build_yiou_match_terms,
    _record_mentions_company,
)
from src.data_agents.company.official_product_capture import (  # noqa: E402
    _is_noise_product_name,
    _looks_like_noise_product_context,
)
from src.data_agents.company.source_product_extractor import (  # noqa: E402
    _clean_name,
    _valid_product_name,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit source-backed company products for a company enrichment batch.",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-rejected", action="store_true")
    parser.add_argument(
        "--apply-rejections",
        action="store_true",
        help="Mark clear audit failures as rejected and write review audit actions.",
    )
    parser.add_argument(
        "--promote-ready",
        action="store_true",
        help="Promote ready candidates to ready. Defaults to report-only for ready rows.",
    )
    parser.add_argument("--actor", default="source-product-quality-audit")
    parser.add_argument(
        "--llm-verify",
        action="store_true",
        help="Use the configured LLM to verify company identity and product ownership.",
    )
    parser.add_argument("--llm-profile", default=None)
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_llm_client(profile: str | None = None):
    from openai import OpenAI

    settings = resolve_professor_llm_settings(profile, include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=90.0, trust_env=False),
        timeout=90.0,
    )
    extra_body = build_non_thinking_extra_body(settings["local_llm_model"])
    return client, settings["local_llm_model"], extra_body


def _build_source_product_select_sql(
    *,
    batch_id: str,
    limit: int | None,
    include_rejected: bool,
) -> tuple[str, dict[str, Any]]:
    conditions = [
        "st.batch_id = %(batch_id)s",
        "p.created_at >= b.started_at",
        "("
        "starts_with(coalesce(p.official_product_url, ''), 'https://pitchhub.36kr.com/') "
        "OR starts_with(coalesce(p.official_product_url, ''), 'https://data.iyiou.com/')"
        ")",
    ]
    if not include_rejected:
        conditions.append("p.quality_status != 'rejected'")
    sql = f"""
        SELECT
            p.product_id,
            p.company_id,
            c.canonical_name AS company_name,
            c.registered_name,
            c.aliases AS company_aliases,
            s.project_name,
            s.description,
            s.team_raw,
            p.canonical_name AS product_name,
            p.short_description,
            p.official_product_url AS source_url,
            p.quality_status,
            pe.evidence_span,
            n.news_id::text AS news_id,
            n.source_adapter,
            n.title,
            n.summary_clean AS source_body
          FROM company_product p
          JOIN company_enrichment_company_state st
            ON st.company_id = p.company_id
          JOIN company_enrichment_batch b
            ON b.batch_id = st.batch_id
          JOIN company c
            ON c.company_id = p.company_id
          LEFT JOIN LATERAL (
              SELECT project_name, description, team_raw
                FROM company_snapshot s
               WHERE s.company_id = p.company_id
               ORDER BY s.snapshot_created_at DESC NULLS LAST
               LIMIT 1
          ) s ON TRUE
          LEFT JOIN LATERAL (
              SELECT evidence_span
                FROM company_product_evidence pe
               WHERE pe.product_id = p.product_id
                 AND pe.source_url = p.official_product_url
               ORDER BY pe.created_at DESC
               LIMIT 1
          ) pe ON TRUE
          LEFT JOIN LATERAL (
              SELECT news_id, source_adapter, title, summary_clean
                FROM company_news_item n
               WHERE n.company_id = p.company_id
                 AND n.source_url = p.official_product_url
               ORDER BY n.fetched_at DESC NULLS LAST
               LIMIT 1
          ) n ON TRUE
         WHERE {" AND ".join(conditions)}
         ORDER BY p.company_id, p.canonical_name, p.product_id
    """
    params: dict[str, Any] = {"batch_id": batch_id}
    if limit is not None:
        sql += " LIMIT %(limit)s"
        params["limit"] = int(limit)
    return sql, params


def _audit_product_row(row: dict[str, Any]) -> dict[str, Any]:
    product_name = _clean_name(str(row.get("product_name") or ""))
    company_name = str(row.get("company_name") or "")
    source_url = str(row.get("source_url") or "")
    source_body = str(row.get("source_body") or "")
    title = str(row.get("title") or "")
    evidence_span = str(row.get("evidence_span") or "")
    short_description = str(row.get("short_description") or "")
    reasons: list[str] = []
    warnings: list[str] = []

    identity_terms = _build_identity_terms(row)
    source_record = NewsRecord(
        company_id=str(row.get("company_id") or ""),
        source_url=source_url,
        title=title,
        summary=source_body,
        raw_text=source_body,
        published_at=None,
        source_adapter=str(row.get("source_adapter") or ""),
    )
    company_identity_confirmed = bool(
        row.get("news_id") and _record_mentions_company(source_record, identity_terms)
    )
    if not row.get("news_id"):
        warnings.append("source_news_missing")
    elif not company_identity_confirmed:
        reasons.append("company_identity_failed")

    product_name_valid = _valid_product_name(
        product_name,
        company_name=company_name,
        allow_company_alias=True,
    )
    if (
        not product_name_valid
        or _is_noise_product_name(product_name)
        or _looks_like_noise_product_context(
            product_name,
            " ".join(value for value in (product_name, short_description) if value),
        )
    ):
        reasons.append("invalid_product_name")

    source_text = " ".join(
        value for value in (title, source_body, evidence_span, short_description) if value
    )
    product_grounded = _contains_text(source_text, product_name)
    if not product_grounded:
        reasons.append("product_not_grounded_in_source")

    evidence_text = " ".join(value for value in (evidence_span, short_description) if value)
    evidence_quality_ok = len(_compact(evidence_text)) >= 12 and _contains_text(
        evidence_text,
        product_name,
    )
    if not evidence_quality_ok:
        warnings.append("weak_evidence_span")

    if reasons:
        decision = "reject"
        recommended_status = "rejected"
        risk_level = "high"
    elif warnings:
        decision = "needs_review"
        recommended_status = "needs_review"
        risk_level = "medium"
    else:
        decision = "ready_candidate"
        recommended_status = "needs_review"
        risk_level = "low"

    return {
        "product_id": str(row.get("product_id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "company_name": company_name,
        "product_name": product_name,
        "source_url": source_url,
        "source_adapter": row.get("source_adapter"),
        "quality_status": row.get("quality_status"),
        "decision": decision,
        "recommended_status": recommended_status,
        "risk_level": risk_level,
        "reasons": _dedupe(reasons),
        "warnings": _dedupe(warnings),
        "company_identity_confirmed": company_identity_confirmed,
        "identity_terms": identity_terms,
        "product_name_valid": product_name_valid,
        "product_grounded": product_grounded,
        "evidence_quality_ok": evidence_quality_ok,
        "news_id": row.get("news_id"),
    }


def _build_llm_verifier_payload(
    row: dict[str, Any],
    rule_result: dict[str, Any],
) -> dict[str, Any]:
    source_body = str(row.get("source_body") or "")
    return {
        "trusted_xlsx_baseline": {
            "company_id": str(row.get("company_id") or ""),
            "company_name": str(row.get("company_name") or ""),
            "registered_name": str(row.get("registered_name") or ""),
            "company_aliases": _coerce_aliases(row.get("company_aliases")),
            "project_name": str(row.get("project_name") or ""),
            "description": str(row.get("description") or ""),
            "team_raw": str(row.get("team_raw") or ""),
        },
        "candidate_product": {
            "product_id": str(row.get("product_id") or ""),
            "product_name": _clean_name(str(row.get("product_name") or "")),
            "short_description": str(row.get("short_description") or ""),
            "source_url": str(row.get("source_url") or ""),
            "evidence_span": str(row.get("evidence_span") or ""),
            "quality_status": row.get("quality_status"),
        },
        "external_source": {
            "news_id": row.get("news_id"),
            "source_adapter": row.get("source_adapter"),
            "source_url": str(row.get("source_url") or ""),
            "title": str(row.get("title") or ""),
            "source_body": source_body[:5000],
        },
        "rule_precheck": {
            "decision": rule_result.get("decision"),
            "reasons": list(rule_result.get("reasons") or []),
            "warnings": list(rule_result.get("warnings") or []),
            "company_identity_confirmed": bool(
                rule_result.get("company_identity_confirmed")
            ),
            "identity_terms": list(rule_result.get("identity_terms") or []),
            "product_name_valid": bool(rule_result.get("product_name_valid")),
            "product_grounded": bool(rule_result.get("product_grounded")),
            "evidence_quality_ok": bool(rule_result.get("evidence_quality_ok")),
        },
    }


def _audit_product_with_llm(
    row: dict[str, Any],
    rule_result: dict[str, Any],
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _build_llm_verifier_payload(row, rule_result)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "XLSX baseline is trusted for company identity and existing "
                        "company facts. External Yiou/PitchHub/source text is untrusted "
                        "candidate evidence. Verify whether the source is about the same "
                        "company and whether the candidate is a real product or service "
                        "provided by that company. Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_llm_verifier_prompt(payload),
                },
            ],
            temperature=0.0,
            max_tokens=900,
            extra_body=extra_body or {},
        )
        raw_text = (response.choices[0].message.content or "").strip()
        verdict = _extract_json_object(raw_text)
        if not isinstance(verdict, dict):
            return _llm_failure_result(
                rule_result,
                error="invalid_json_response",
                raw_text=raw_text[:500],
            )
        return _merge_llm_verdict(rule_result, verdict, llm_model=llm_model)
    except Exception as exc:
        return _llm_failure_result(rule_result, error=str(exc), raw_text=None)


def _build_llm_verifier_prompt(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Judge this external company-product candidate.",
            "Use the trusted XLSX baseline as the company identity baseline.",
            "Do not treat recall terms, product terms, industry words, founders, or unverified aliases as proof of identity.",
            "Reject if the source section is about another company, a related article, a similar project, an investor, a platform recommendation, or an industry example.",
            "Reject or mark needs_review if the candidate name is a sentence fragment, slogan, generic section title, or not an actual product/service.",
            "If the evidence is ambiguous, choose needs_review.",
            "Return strict JSON with keys: company_identity_match, matched_company_name_or_alias, source_section_type, fact_belongs_to_company, is_actual_product_or_service, evidence_quote, decision, confidence, reason.",
            "confidence should be a numeric value between 0 and 1. If you cannot provide a numeric value, use high/medium/low.",
            "Allowed values: yes/no/uncertain for the three boolean judgments; decision is ready_candidate/needs_review/reject.",
            "",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def _merge_llm_verdict(
    rule_result: dict[str, Any],
    verdict: dict[str, Any],
    *,
    llm_model: str,
) -> dict[str, Any]:
    confidence = _coerce_float(verdict.get("confidence"))
    identity = _normalize_verdict_value(verdict.get("company_identity_match"))
    belongs = _normalize_verdict_value(verdict.get("fact_belongs_to_company"))
    actual = _normalize_verdict_value(verdict.get("is_actual_product_or_service"))
    requested_decision = str(verdict.get("decision") or "").strip()
    evidence_quote = str(verdict.get("evidence_quote") or "").strip()
    reasons: list[str] = []
    warnings: list[str] = []

    if confidence < 0.75:
        warnings.append("llm_low_confidence")
    if not evidence_quote:
        warnings.append("llm_missing_evidence_quote")
    if "no" in {identity, belongs, actual}:
        if identity == "no":
            reasons.append("llm_company_identity_no")
        if belongs == "no":
            reasons.append("llm_fact_belongs_no")
        if actual == "no":
            reasons.append("llm_not_actual_product")
    if "uncertain" in {identity, belongs, actual}:
        warnings.append("llm_uncertain")

    if reasons and confidence >= 0.75:
        decision = "reject"
        recommended_status = "rejected"
        risk_level = "high"
    elif (
        identity == "yes"
        and belongs == "yes"
        and actual == "yes"
        and confidence >= 0.75
        and evidence_quote
        and requested_decision != "reject"
    ):
        decision = "ready_candidate"
        recommended_status = "ready"
        risk_level = "low"
    else:
        decision = "needs_review"
        recommended_status = "needs_review"
        risk_level = "medium"

    result = dict(rule_result)
    result.update(
        {
            "decision": decision,
            "recommended_status": recommended_status,
            "risk_level": risk_level,
            "reasons": _dedupe(reasons),
            "warnings": _dedupe(warnings),
            "llm_verifier": {
                "status": "verified",
                "model": llm_model,
                "company_identity_match": identity,
                "matched_company_name_or_alias": str(
                    verdict.get("matched_company_name_or_alias") or ""
                ),
                "source_section_type": str(verdict.get("source_section_type") or ""),
                "fact_belongs_to_company": belongs,
                "is_actual_product_or_service": actual,
                "evidence_quote": evidence_quote,
                "confidence": confidence,
                "reason": str(verdict.get("reason") or ""),
                "raw_decision": requested_decision,
            },
        }
    )
    return result


def _llm_failure_result(
    rule_result: dict[str, Any],
    *,
    error: str,
    raw_text: str | None,
) -> dict[str, Any]:
    hard_reasons = [
        reason
        for reason in (rule_result.get("reasons") or [])
        if reason in {"invalid_product_name", "product_not_grounded_in_source"}
    ]
    result = dict(rule_result)
    if hard_reasons:
        decision = "reject"
        recommended_status = "rejected"
        risk_level = "high"
        reasons = hard_reasons
    else:
        decision = "needs_review"
        recommended_status = "needs_review"
        risk_level = "medium"
        reasons = []
    result.update(
        {
            "decision": decision,
            "recommended_status": recommended_status,
            "risk_level": risk_level,
            "reasons": _dedupe(reasons),
            "warnings": _dedupe(list(result.get("warnings") or []) + ["llm_verification_failed"]),
            "llm_verifier": {
                "status": "failed",
                "error": error,
                "raw_text": raw_text,
            },
        }
    )
    return result


def _extract_json_object(raw_text: str) -> Any:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _normalize_verdict_value(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text in {"yes", "true", "是", "匹配", "same"}:
        return "yes"
    if text in {"no", "false", "否", "不匹配", "different"}:
        return "no"
    return "uncertain"


def _coerce_float(value: Any) -> float:
    if isinstance(value, str):
        text = value.strip().casefold()
        text = text.removesuffix("%")
        labels = {
            "very high": 0.95,
            "high": 0.85,
            "medium": 0.65,
            "moderate": 0.65,
            "low": 0.35,
            "very low": 0.2,
            "高": 0.85,
            "中": 0.65,
            "低": 0.35,
        }
        if text in labels:
            return labels[text]
        try:
            parsed = float(text)
        except ValueError:
            return 0.0
        if "%" in str(value):
            return parsed / 100.0
        return parsed
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_identity_terms(row: dict[str, Any]) -> list[str]:
    aliases = _coerce_aliases(row.get("company_aliases"))
    context = YiouSearchContext(
        company_name=str(row.get("company_name") or ""),
        normalized_name=str(row.get("registered_name") or ""),
        description=str(row.get("description") or ""),
        team_raw=str(row.get("team_raw") or ""),
        project_name=str(row.get("project_name") or ""),
        aliases=tuple(aliases),
    )
    return _build_yiou_match_terms(context, [])


def _coerce_aliases(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item or "").strip()]
        return [value] if value.strip() else []
    return []


def _contains_text(haystack: str, needle: str) -> bool:
    compact_needle = _compact(needle)
    if len(compact_needle) < 2:
        return False
    return compact_needle in _compact(haystack)


def _compact(value: str | None) -> str:
    text = (value or "").replace("™", "").replace("®", "")
    return re.sub(r"[\s\u3000，,。.;；:：\"'“”‘’（）()\[\]【】_\-]+", "", text).casefold()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _apply_audit_actions(
    conn: Any,
    audit_items: list[dict[str, Any]],
    *,
    actor: str,
    apply_rejections: bool,
    promote_ready: bool,
) -> dict[str, int]:
    updated = {"rejected": 0, "ready": 0}
    for item in audit_items:
        if apply_rejections and item["recommended_status"] == "rejected":
            review_enrichment_item(
                conn,
                target_type="product",
                target_id=item["product_id"],
                action="reject",
                actor=actor,
                note=f"source_product_quality_audit: {', '.join(item['reasons'])}",
            )
            updated["rejected"] += 1
        elif promote_ready and item["decision"] == "ready_candidate":
            review_enrichment_item(
                conn,
                target_type="product",
                target_id=item["product_id"],
                action="accept",
                actor=actor,
                note="source_product_quality_audit: ready_candidate",
            )
            updated["ready"] += 1
    return updated


def _build_report(
    *,
    batch_id: str,
    dry_run: bool,
    apply_rejections: bool,
    promote_ready: bool,
    llm_verify: bool,
    audit_items: list[dict[str, Any]],
    updated_counts: dict[str, int],
) -> dict[str, Any]:
    decision_counts = Counter(item["decision"] for item in audit_items)
    risk_counts = Counter(item["risk_level"] for item in audit_items)
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    for item in audit_items:
        reason_counts.update(item["reasons"])
        warning_counts.update(item["warnings"])
    llm_status_counts = Counter(
        item.get("llm_verifier", {}).get("status", "not_requested")
        for item in audit_items
    )
    return {
        "batch_id": batch_id,
        "dry_run": dry_run,
        "apply_rejections": apply_rejections,
        "promote_ready": promote_ready,
        "llm_verify": llm_verify,
        "totals": {
            "audited": len(audit_items),
            "llm_verified": llm_status_counts.get("verified", 0),
            "llm_failed": llm_status_counts.get("failed", 0),
        },
        "decision_counts": dict(decision_counts),
        "risk_counts": dict(risk_counts),
        "reason_counts": dict(reason_counts),
        "warning_counts": dict(warning_counts),
        "llm_status_counts": dict(llm_status_counts),
        "updated_counts": updated_counts,
        "items": audit_items,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    conn = _open_database_connection(dsn)
    sql, params = _build_source_product_select_sql(
        batch_id=args.batch_id,
        limit=args.limit,
        include_rejected=args.include_rejected,
    )
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    llm_client: Any | None = None
    llm_model: str | None = None
    llm_extra_body: dict[str, Any] | None = None
    if args.llm_verify:
        llm_client, llm_model, llm_extra_body = _open_llm_client(args.llm_profile)

    audit_items: list[dict[str, Any]] = []
    for row in rows:
        rule_result = _audit_product_row(row)
        if args.llm_verify and llm_client is not None and llm_model is not None:
            audit_items.append(
                _audit_product_with_llm(
                    row,
                    rule_result,
                    llm_client=llm_client,
                    llm_model=llm_model,
                    extra_body=llm_extra_body,
                )
            )
        else:
            audit_items.append(rule_result)
    updated_counts = {"rejected": 0, "ready": 0}
    if not args.dry_run and (args.apply_rejections or args.promote_ready):
        updated_counts = _apply_audit_actions(
            conn,
            audit_items,
            actor=args.actor,
            apply_rejections=args.apply_rejections,
            promote_ready=args.promote_ready,
        )
        conn.commit()
    report = _build_report(
        batch_id=args.batch_id,
        dry_run=args.dry_run,
        apply_rejections=args.apply_rejections,
        promote_ready=args.promote_ready,
        llm_verify=args.llm_verify,
        audit_items=audit_items,
        updated_counts=updated_counts,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
