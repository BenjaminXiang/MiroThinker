#!/usr/bin/env python3
"""Record the D1-a controlled-vocabulary LLM decisions into a decision bundle.

Two phases, both batched (never one call per tag value):

  * ``induct`` - one call over a deterministic stratified sample of every distinct
    value; the model proposes the controlled concept vocabulary.
  * ``map``    - ``ceil(values / batch)`` calls per field; the model maps each raw
    value into concepts of that frozen list, or into ``[]`` (undecidable).

The script only *records* provider bytes.  All parsing/replay lives in
``data_agents.canonical_v2.tech_vocabulary`` so the build replays exactly the code
path that recorded the bundle.  Completed calls are cached per call id, so a
re-run resumes and never re-asks a recorded call.

Secrets: the key is read through the repository chain
(``providers/local_api_key.py`` -> ``.deepseek_api_key``); it is never printed,
hashed or written into an artifact.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = REPO_ROOT / "apps" / "miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

from src.data_agents.canonical_v2.tech_vocabulary import (  # noqa: E402
    BUNDLE_SCHEMA_VERSION,
    MAPPING_BATCH_SIZE,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_VERSION,
    VocabularyIntegrityError,
    assert_mapping_arity,
    induction_batches,
    mapping_batches,
    merge_induced_concepts,
    parse_concept_drafts,
    parse_mapping_lines,
    render_concept_catalogue,
    render_induction_prompt,
    render_mapping_prompt,
    vocabulary_content_sha256,
)
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

DEFAULT_INPUTS = (
    REPO_ROOT / ".agents/runs/d1a-tech-vocabulary/out/vocabulary-inputs.json"
)
DEFAULT_OUT = REPO_ROOT / ".agents/runs/d1a-tech-vocabulary/out"
PROVIDER_NAME = "deepseek"
MAX_CONCEPTS = 100
MAX_ATTEMPTS = 3
MAX_OUTPUT_TOKENS = 64000


class InductionError(RuntimeError):
    """The recording run could not produce a schema-valid provider transcript."""


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_inputs(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    tech = {item["value"]: item["companies"] for item in document["tech_tag_values"]}
    industry = {
        item["value"]: item["companies"] for item in document["industry_values"]
    }
    return tech, industry


class Provider:
    """One recorded provider endpoint, resolved through the repo credential chain."""

    def __init__(
        self, *, model: str, base_url: str, api_key: str, timeout: float
    ) -> None:
        self.model = model
        self.base_url = base_url
        self._api_key = api_key
        self.timeout = timeout
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def complete(self, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=self.base_url, api_key=self._api_key, timeout=self.timeout
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.0,
            extra_body=build_non_thinking_extra_body(self.model),
        )
        self.calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise InductionError("provider returned an empty transcript")
        return content


def call_id_for(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _validate_mapping(
    raw_output: str,
    values: Sequence[str],
    field: str,
    concept_ids: frozenset[str],
) -> None:
    parsed = parse_mapping_lines(
        raw_output, expected_values=values, concept_ids=concept_ids
    )
    assert_mapping_arity(field, parsed)


def _write_telemetry(
    *, out: Path, calls: Sequence[Mapping[str, Any]], provider: Provider, model: str
) -> None:
    """Honest call accounting: recorded calls vs actual provider attempts."""
    payload = {
        "model": model,
        "recorded_calls": len(calls),
        "provider_attempts_total": sum(
            int(call.get("provider_attempts", 1)) for call in calls
        ),
        "provider_attempts_this_process": provider.calls,
        "retried_calls": sum(
            1 for call in calls if int(call.get("provider_attempts", 1)) > 1
        ),
        "prompt_tokens": provider.prompt_tokens,
        "completion_tokens": provider.completion_tokens,
        "notes": (
            "provider_attempts_this_process counts every HTTP call made by this "
            "process, including attempts whose transcript failed validation and "
            "were re-asked; only the accepted transcript of each call id is "
            "recorded in the bundle and replayed by the build."
        ),
    }
    (out / "induction-telemetry.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def record_call(
    *,
    provider: Provider,
    cache_dir: Path,
    call_id: str,
    kind: str,
    prompt: str,
    input_value_ids: Sequence[str],
    validate: Any,
) -> dict[str, Any]:
    """Run one provider call until its transcript satisfies the shared parser."""
    cache_path = cache_dir / f"{call_id.replace(':', '__')}.json"
    if cache_path.is_file():
        recorded = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"[cached ] {call_id}  values={len(input_value_ids)}", flush=True)
        return recorded
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        try:
            raw_output = provider.complete(prompt)
            validate(raw_output)
        except (InductionError, VocabularyIntegrityError) as exc:
            last_error = exc
            print(f"[retry  ] {call_id} attempt={attempt}: {exc}", flush=True)
            time.sleep(2.0 * attempt)
            continue
        except Exception as exc:  # provider/transport failure
            last_error = exc
            print(
                f"[retry  ] {call_id} attempt={attempt}: {type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(3.0 * attempt)
            continue
        recorded = {
            "call_id": call_id,
            "kind": kind,
            "input_value_ids": list(input_value_ids),
            "input_sha256": canonical_sha256(list(input_value_ids)),
            "raw_output": raw_output,
            "output_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
            "provider_attempts": attempts,
        }
        cache_path.write_text(
            json.dumps(recorded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[recorded] {call_id}  values={len(input_value_ids)}", flush=True)
        return recorded
    raise InductionError(
        f"{call_id} failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--phase", choices=("all", "induct", "map"), default="all")
    args = parser.parse_args()

    tech_values, industry_values = load_inputs(args.inputs)
    all_values = {"tech_tags": tech_values, "industry": industry_values}
    cache_dir = args.out / "bundle-calls"
    cache_dir.mkdir(parents=True, exist_ok=True)

    settings = resolve_professor_llm_settings(args.profile)
    api_key = settings.get("local_llm_api_key") or load_local_api_key(REPO_ROOT)
    model = settings.get("local_llm_model") or ""
    base_url = settings.get("local_llm_base_url") or ""
    if not api_key:
        raise SystemExit("no provider credential resolved from the repository chain")
    provider = Provider(
        model=model, base_url=base_url, api_key=api_key, timeout=args.timeout
    )
    print(f"provider={PROVIDER_NAME} model={model} base_url={base_url}", flush=True)

    chunks = induction_batches(sorted(tech_values))
    calls: list[dict[str, Any]] = []

    if args.phase in ("all", "induct"):
        induction_jobs = [(f"{index:04d}", chunk) for index, chunk in enumerate(chunks)]

        def run_induction(job: tuple[str, Sequence[str]]) -> dict[str, Any]:
            index, chunk = job
            return record_call(
                provider=provider,
                cache_dir=cache_dir,
                call_id=call_id_for("induct", index),
                kind="induct",
                prompt=render_induction_prompt(chunk, max_concepts=MAX_CONCEPTS),
                input_value_ids=chunk,
                validate=parse_concept_drafts,
            )

        with ThreadPoolExecutor(
            max_workers=max(1, min(args.workers, len(chunks)))
        ) as executor:
            calls.extend(executor.map(run_induction, induction_jobs))
        induced = [
            concept
            for call in sorted(calls, key=lambda item: item["call_id"])
            for concept in parse_concept_drafts(call["raw_output"])
        ]
        concepts, merged_duplicates, id_collisions = merge_induced_concepts(induced)
    elif args.phase == "map":
        cached: list[dict[str, Any]] = []
        for index, _chunk in enumerate(chunks):
            path = cache_dir / (
                call_id_for("induct", f"{index:04d}").replace(":", "__") + ".json"
            )
            cached.append(json.loads(path.read_text(encoding="utf-8")))
        calls.extend(cached)
        induced = [
            concept
            for call in sorted(cached, key=lambda item: item["call_id"])
            for concept in parse_concept_drafts(call["raw_output"])
        ]
        concepts, merged_duplicates, id_collisions = merge_induced_concepts(induced)
    else:  # pragma: no cover - argparse restricts the value
        raise SystemExit("unreachable phase")

    catalogue = render_concept_catalogue(concepts)
    concept_ids = frozenset(concept.concept_id for concept in concepts)
    print(
        f"concepts={len(concept_ids)} merged_duplicates={merged_duplicates} "
        f"id_collisions={id_collisions}",
        flush=True,
    )

    if args.phase in ("all", "map"):
        jobs: list[tuple[str, str, Sequence[str]]] = []
        for batch_index, batch in enumerate(mapping_batches(sorted(tech_values))):
            jobs.append(("tech_tags", f"{batch_index:04d}", batch))
        for batch_index, batch in enumerate(mapping_batches(sorted(industry_values))):
            jobs.append(("industry", f"{batch_index:04d}", batch))

        def run_job(job: tuple[str, str, Sequence[str]]) -> dict[str, Any]:
            field, index, batch = job
            prompt = render_mapping_prompt(
                field, batch, catalogue=catalogue, concept_ids=sorted(concept_ids)
            )
            return record_call(
                provider=provider,
                cache_dir=cache_dir,
                call_id=call_id_for("map", f"{field}:{index}"),
                kind="value_mapping",
                prompt=prompt,
                input_value_ids=batch,
                validate=lambda raw, batch=batch, field=field: _validate_mapping(
                    raw, batch, field, concept_ids
                ),
            )

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            calls.extend(executor.map(run_job, jobs))

    bundle = assemble_bundle(
        calls=calls,
        concepts=concepts,
        all_values=all_values,
        provider=provider,
        model=model,
        base_url=base_url,
    )
    _write_telemetry(out=args.out, calls=calls, provider=provider, model=model)
    bundle_path = args.out / "recorded-vocabulary-decision-bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "bundle": str(bundle_path),
                "llm_calls_recorded": len(calls),
                "provider_calls_this_run": provider.calls,
                "prompt_tokens": provider.prompt_tokens,
                "completion_tokens": provider.completion_tokens,
                "concepts": len(concepts),
                "content_sha256": bundle["content_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def assemble_bundle(
    *,
    calls: Sequence[Mapping[str, Any]],
    concepts: Sequence[Any],
    all_values: Mapping[str, Mapping[str, int]],
    provider: Provider,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    chunks = induction_batches(sorted(all_values["tech_tags"]))
    prompts = {
        "induct": render_induction_prompt(("<sample>",), max_concepts=MAX_CONCEPTS),
        "map": render_mapping_prompt(
            "tech_tags",
            ["<sample>"],
            catalogue=render_concept_catalogue(concepts),
            concept_ids=sorted(concept.concept_id for concept in concepts),
        ),
    }
    payload: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "provider": PROVIDER_NAME,
        "model": model,
        "endpoint": base_url,
        "prompt_version": PROMPT_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "temperature": 0.0,
        "pythonhashseed_invariant": True,
        "prompts": {
            kind: {
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text": text,
            }
            for kind, text in prompts.items()
        },
        "source_value_counts": {
            field: len(values) for field, values in sorted(all_values.items())
        },
        "induction_chunks": [list(chunk) for chunk in chunks],
        "induction_max_concepts": MAX_CONCEPTS,
        "mapping_batch_size": MAPPING_BATCH_SIZE,
        "calls": [
            {
                "call_id": call["call_id"],
                "kind": call["kind"],
                "input_value_ids": list(call["input_value_ids"]),
                "input_sha256": call["input_sha256"],
                "raw_output": call["raw_output"],
                "output_sha256": call["output_sha256"],
            }
            for call in sorted(calls, key=lambda item: str(item["call_id"]))
        ],
        "call_count": len(calls),
        "usage": {
            "prompt_tokens": provider.prompt_tokens,
            "completion_tokens": provider.completion_tokens,
        },
    }
    payload["content_sha256"] = vocabulary_content_sha256(payload)
    return payload


if __name__ == "__main__":
    main()
