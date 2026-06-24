#!/usr/bin/env python
"""Model-assisted professor publishability gate.

Default mode is a bounded dry-run. Use --write to update quality_status for
deterministic-ready candidates that pass the model gate. The script supports
worker sharding and JSONL checkpoint/resume so the 3387-row professor set does
not require one fragile process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from uuid import UUID

import httpx
import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.professor.model_quality_gate import (  # noqa: E402
    MODEL_QUALITY_GATE_ACTOR,
    MODEL_QUALITY_GATE_REPORTED_BY,
    MODEL_QUALITY_GATE_STAGE,
    ModelQualityGateResult,
    evaluate_model_quality_gate,
)
from src.data_agents.professor.quality_gate import (  # noqa: E402
    evaluate_professor_quality,
    load_professor_canonical_state,
    persist_professor_quality_evaluation,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_RUN_KIND = "backfill_real"
_DEFAULT_LLM_PROFILE = "deepseek-v4-pro"
_CHECKPOINT_DIR = (
    _APP_ROOT.parent.parent / ".agents" / "runs" / "professor-model-quality-gate"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run model-assisted publishability gate for professor records."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--write", action="store_true", help="Persist DB changes.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--worker-count", type=int, default=1)
    parser.add_argument("--worker-index", type=int, default=0)
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--llm-profile", default=_DEFAULT_LLM_PROFILE)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--confidence-threshold", type=float, default=0.75)
    parser.add_argument(
        "--base-only",
        action="store_true",
        help=(
            "Only persist deterministic non-ready statuses. Base-ready candidates "
            "remain needs_review until the model gate passes."
        ),
    )
    parser.add_argument(
        "--include-ready",
        action="store_true",
        help="Also inspect rows already marked ready. Default scans needs_review only.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.worker_count < 1:
        raise ValueError("--worker-count must be >= 1")
    if args.worker_index < 0 or args.worker_index >= args.worker_count:
        raise ValueError("--worker-index must be in [0, worker_count)")
    if "deepseek" in str(args.llm_profile).lower():
        load_dotenv(override=False)

    dsn = resolve_dsn(
        args.database_url
        or os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_URL_TEST")
    )
    settings: dict[str, str]
    client: Any | None = None
    extra_body: dict[str, Any] = {}
    if args.base_only:
        settings = {"llm_profile": "base-only"}
        model = "base-only"
    else:
        settings = resolve_professor_llm_settings(
            args.llm_profile,
            strict=True,
            include_profile=True,
            apply_endpoint_env_overrides=False,
        )
        model = args.model or settings["local_llm_model"]
        client = _open_llm_client(
            settings, timeout=args.timeout, max_retries=args.max_retries
        )
        extra_body = build_non_thinking_extra_body(model)

    conn = psycopg.connect(dsn, row_factory=dict_row)
    run_id: UUID | str | None = None
    checkpoint_path: Path | None = None
    try:
        if args.write:
            run_id = open_pipeline_run(
                conn,
                run_kind=_RUN_KIND,
                run_scope={
                    "task": "professor_model_quality_gate",
                    "llm_profile": settings["llm_profile"],
                    "model": model,
                    "limit": args.limit,
                    "offset": args.offset,
                    "worker_count": args.worker_count,
                    "worker_index": args.worker_index,
                    "include_ready": bool(args.include_ready),
                    "confidence_threshold": args.confidence_threshold,
                    "base_only": bool(args.base_only),
                },
                triggered_by=MODEL_QUALITY_GATE_REPORTED_BY,
            )
            run_id = require_real_run_id(run_id, writer_name=__file__)
            conn.commit()

        checkpoint_path = _resolve_checkpoint_path(args, run_id)
        completed = _load_completed_ids(args.resume)
        professor_ids = _select_professor_ids(
            conn,
            include_ready=bool(args.include_ready),
            worker_count=args.worker_count,
            worker_index=args.worker_index,
            offset=args.offset,
            limit=args.limit,
            completed=completed,
        )
        summary = _empty_summary(
            args=args,
            model=model,
            llm_profile=settings["llm_profile"],
            checkpoint_path=checkpoint_path,
            run_id=run_id,
            selected=len(professor_ids),
        )
        for professor_id in professor_ids:
            row = _process_professor(
                conn,
                professor_id=professor_id,
                client=client,
                model=model,
                extra_body=extra_body,
                confidence_threshold=args.confidence_threshold,
                base_only=bool(args.base_only),
                write=bool(args.write),
                run_id=run_id,
            )
            _accumulate(summary, row)
            _append_checkpoint(checkpoint_path, row)
            if _is_provider_billing_error(row.get("error")):
                summary["stopped_early"] = True
                summary["provider_billing_error"] = str(row.get("error") or "")
                break
            if args.sleep:
                time.sleep(args.sleep)

        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if summary["failed"] else "succeeded",
                items_processed=summary["processed"],
                items_failed=summary["failed"],
                error_summary={
                    "ready": summary["ready"],
                    "needs_review": summary["needs_review"],
                    "skipped_base": summary["skipped_base"],
                    "ready_candidate": summary["ready_candidate"],
                    "stopped_early": summary["stopped_early"],
                    "provider_billing_error": summary["provider_billing_error"],
                },
            )
            conn.commit()
        return summary
    except Exception as exc:
        conn.rollback()
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            conn.commit()
        raise
    finally:
        conn.close()


def _open_llm_client(
    settings: dict[str, str],
    *,
    timeout: float,
    max_retries: int,
) -> OpenAI:
    return OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=timeout, trust_env=False),
        timeout=timeout,
        max_retries=max_retries,
    )


def _select_professor_ids(
    conn: Any,
    *,
    include_ready: bool,
    worker_count: int,
    worker_index: int,
    offset: int,
    limit: int | None,
    completed: set[str],
) -> list[str]:
    statuses = ("needs_review", "ready") if include_ready else ("needs_review",)
    rows = conn.execute(
        """
        SELECT professor_id
          FROM professor
         WHERE quality_status = ANY(%s)
           AND COALESCE(lifecycle_state, 'active') != 'merged_to_other_school'
         ORDER BY professor_id
        """,
        (list(statuses),),
    ).fetchall()
    sharded = []
    for row in rows:
        professor_id = str(row["professor_id"])
        if professor_id in completed:
            continue
        if _worker_slot(professor_id, worker_count) != worker_index:
            continue
        sharded.append(professor_id)
    if offset:
        sharded = sharded[int(offset) :]
    if limit is not None:
        sharded = sharded[: int(limit)]
    return sharded


def _worker_slot(professor_id: str, worker_count: int) -> int:
    digest = hashlib.sha256(professor_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % worker_count


def _process_professor(
    conn: Any,
    *,
    professor_id: str,
    client: Any | None,
    model: str,
    extra_body: dict[str, Any],
    confidence_threshold: float,
    base_only: bool,
    write: bool,
    run_id: UUID | str | None,
) -> dict[str, Any]:
    try:
        state = load_professor_canonical_state(conn, professor_id)
        if base_only:
            base_evaluation = evaluate_professor_quality(state)
            result = _base_only_result(professor_id, base_evaluation.quality_status)
            wrote = False
            if write and base_evaluation.quality_status != "ready":
                if run_id is None:
                    raise ValueError("write mode requires run_id")
                _persist_base_quality_result(
                    conn,
                    professor_id=professor_id,
                    evaluation=base_evaluation,
                    run_id=run_id,
                )
                conn.commit()
                wrote = True
            return _result_row(result, wrote=wrote)

        if client is None:
            raise ValueError("LLM client is required unless --base-only is set")
        result = evaluate_model_quality_gate(
            state,
            llm_client=client,
            llm_model=model,
            extra_body=extra_body,
            confidence_threshold=confidence_threshold,
        )
        wrote = False
        if write:
            if run_id is None:
                raise ValueError("write mode requires run_id")
            if result.model_called:
                _persist_model_quality_result(
                    conn, state=state, result=result, run_id=run_id
                )
                wrote = True
            elif result.base_quality_status != "ready":
                _persist_base_quality_result(
                    conn,
                    professor_id=professor_id,
                    evaluation=evaluate_professor_quality(state),
                    run_id=run_id,
                )
                wrote = True
            if wrote:
                conn.commit()
        return _result_row(result, wrote=wrote)
    except Exception as exc:  # noqa: BLE001 - per-row resilience
        conn.rollback()
        return {
            "professor_id": professor_id,
            "status": "failed",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _base_only_result(
    professor_id: str,
    base_quality_status: str,
) -> ModelQualityGateResult:
    if base_quality_status == "ready":
        return ModelQualityGateResult(
            professor_id=professor_id,
            base_quality_status=base_quality_status,
            final_quality_status="needs_review",
            model_called=False,
            skip_reason="base_ready_requires_model",
        )
    return ModelQualityGateResult(
        professor_id=professor_id,
        base_quality_status=base_quality_status,
        final_quality_status=base_quality_status,  # type: ignore[arg-type]
        model_called=False,
        skip_reason=f"base_gate_{base_quality_status}",
    )


def _persist_base_quality_result(
    conn: Any,
    *,
    professor_id: str,
    evaluation: Any,
    run_id: UUID | str,
) -> None:
    run_id = require_real_run_id(run_id, writer_name="_persist_base_quality_result")
    persist_professor_quality_evaluation(conn, evaluation)
    conn.execute(
        "UPDATE professor SET run_id = %s, updated_at = now() WHERE professor_id = %s",
        (run_id, professor_id),
    )


def _persist_model_quality_result(
    conn: Any,
    *,
    state: Any,
    result: ModelQualityGateResult,
    run_id: UUID | str,
) -> None:
    run_id = require_real_run_id(run_id, writer_name="_persist_model_quality_result")
    if result.final_quality_status == "ready":
        evaluation = evaluate_professor_quality(state)
        persist_professor_quality_evaluation(conn, evaluation)
        conn.execute(
            "UPDATE professor SET run_id = %s, updated_at = now() WHERE professor_id = %s",
            (run_id, result.professor_id),
        )
        _insert_model_ready_action(conn, result=result, run_id=run_id)
        return

    conn.execute(
        """
        UPDATE professor
           SET quality_status = 'needs_review',
               run_id = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (run_id, result.professor_id),
    )
    _insert_model_review_issue(conn, result=result, run_id=run_id)


def _insert_model_ready_action(
    conn: Any,
    *,
    result: ModelQualityGateResult,
    run_id: UUID | str,
) -> None:
    decision = result.decision
    note = {
        "run_id": str(run_id),
        "model_quality_gate": "passed",
        "confidence": decision.confidence if decision else None,
        "reason_codes": list(decision.reason_codes) if decision else [],
        "rationale": decision.rationale if decision else "",
    }
    conn.execute(
        """
        INSERT INTO professor_admin_action (
            professor_id, action, actor, note, observed_data_updated_at
        )
        VALUES (%s, 'confirm_ready', %s, %s, now())
        """,
        (result.professor_id, MODEL_QUALITY_GATE_ACTOR, json.dumps(note, ensure_ascii=False)),
    )


def _insert_model_review_issue(
    conn: Any,
    *,
    result: ModelQualityGateResult,
    run_id: UUID | str,
) -> None:
    decision = result.decision
    reason_codes = list(decision.reason_codes) if decision else ["model_quality_gate_failed"]
    description = "model quality gate blocked publishability: " + ",".join(reason_codes)
    evidence = {
        "run_id": str(run_id),
        "quality_status": "needs_review",
        "confidence": decision.confidence if decision else None,
        "reason_codes": reason_codes,
        "rationale": decision.rationale if decision else "",
        "prompt_hash": decision.prompt_hash if decision else None,
        "raw_response_hash": decision.raw_response_hash if decision else None,
        "usage": decision.usage if decision else {},
    }
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity, description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'high', %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            result.professor_id,
            MODEL_QUALITY_GATE_STAGE,
            description,
            Jsonb(evidence),
            MODEL_QUALITY_GATE_REPORTED_BY,
        ),
    )


def _result_row(result: ModelQualityGateResult, *, wrote: bool) -> dict[str, Any]:
    decision = result.decision
    return {
        "professor_id": result.professor_id,
        "status": "processed",
        "base_quality_status": result.base_quality_status,
        "final_quality_status": result.final_quality_status,
        "model_called": result.model_called,
        "skip_reason": result.skip_reason,
        "wrote": wrote,
        "confidence": decision.confidence if decision else None,
        "reason_codes": list(decision.reason_codes) if decision else [],
        "rationale": decision.rationale if decision else None,
        "usage": decision.usage if decision else {},
    }


def _empty_summary(
    *,
    args: argparse.Namespace,
    model: str,
    llm_profile: str,
    checkpoint_path: Path,
    run_id: UUID | str | None,
    selected: int,
) -> dict[str, Any]:
    return {
        "dry_run": not bool(args.write),
        "write": bool(args.write),
        "run_id": str(run_id) if run_id else None,
        "llm_profile": llm_profile,
        "model": model,
        "selected": selected,
        "processed": 0,
        "model_called": 0,
        "ready": 0,
        "needs_review": 0,
        "needs_enrichment": 0,
        "low_confidence": 0,
        "skipped_base": 0,
        "ready_candidate": 0,
        "failed": 0,
        "written": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "stopped_early": False,
        "provider_billing_error": None,
        "checkpoint_path": str(checkpoint_path),
        "worker_count": args.worker_count,
        "worker_index": args.worker_index,
        "limit": args.limit,
        "include_ready": bool(args.include_ready),
        "base_only": bool(args.base_only),
    }


def _accumulate(summary: dict[str, Any], row: dict[str, Any]) -> None:
    if row.get("status") == "failed":
        summary["failed"] += 1
        return
    summary["processed"] += 1
    if row.get("model_called"):
        summary["model_called"] += 1
    else:
        summary["skipped_base"] += 1
    if row.get("skip_reason") == "base_ready_requires_model":
        summary["ready_candidate"] += 1
    if row.get("wrote"):
        summary["written"] += 1
    final_status = str(row.get("final_quality_status") or "")
    if final_status in {"ready", "needs_review", "needs_enrichment", "low_confidence"}:
        summary[final_status] += 1
    usage = row.get("usage") or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        summary["usage"][key] += int(usage.get(key) or 0)


def _is_provider_billing_error(error: Any) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    billing_markers = (
        "insufficient balance",
        "insufficient_balance",
        "insufficient quota",
        "insufficient_quota",
        "payment required",
        "billing",
    )
    return ("402" in text or "payment required" in text) and any(
        marker in text for marker in billing_markers
    )


def _resolve_checkpoint_path(args: argparse.Namespace, run_id: UUID | str | None) -> Path:
    if args.checkpoint:
        return args.checkpoint
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    name = str(run_id) if run_id else f"dry-run-{int(time.time())}"
    return _CHECKPOINT_DIR / f"{name}-worker{args.worker_index}.jsonl"


def _load_completed_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    completed: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            professor_id = str(row.get("professor_id") or "").strip()
            if professor_id and row.get("status") == "processed":
                completed.add(professor_id)
    return completed


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
