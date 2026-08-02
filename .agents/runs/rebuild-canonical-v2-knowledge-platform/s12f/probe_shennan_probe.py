"""Run the exact 深南 theme-probe query and trace the hit decision."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402

RUN_ROOT = AGENT_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
RELEASE_ID = "candidate-s12f-20260801-v1"
QUERY = "深南电路 PCB打板"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    inputs = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12f/serving-bundle-s12f.json",
        expected_content_sha256="93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12f_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    probe = inputs.web_search._merged_results
    results = probe(QUERY)
    print(f"probe results: {len(results)}")
    for index, result in enumerate(results[:8]):
        text = f"{result.title} {result.snippet}"
        company_hit = any(
            serving._web_identity_text_matches(form, serving._normalized_web_identity(text))
            for form in serving._web_identity_forms("深南电路股份有限公司")
        )
        covers = serving._theme_evidence_covers("PCB打板", text)
        print(f"  [{index}] company={company_hit} covers={covers} | {result.title[:40]} | {result.url[:50]}")
        print(f"        {result.snippet[:90]}")


if __name__ == "__main__":
    raise SystemExit(main())
