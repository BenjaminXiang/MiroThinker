"""Generate the content-addressed s12e serving bundle from the accepted r8 bundle.

Only the release-bound identities change (bundle id, release id, database,
index target/root, envelope path); every runtime policy field stays byte
identical to the accepted r8 bundle.  The self-hash is recomputed through
``RecordedServingBundle.model_validate`` exactly like the earlier web-results
bump, and the readback is validated in external content-addressed mode.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
AGENT_APP = ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    RecordedServingBundle,
)


GATE = ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
SOURCE = GATE / "s12c/serving-bundle-r8.json"
OUTPUT = Path(__file__).with_name("serving-bundle-s12e.json")
RELEASE_ID = "candidate-s12e-20260801-v1"


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing bundle: {OUTPUT}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload.pop("content_sha256", None)
    payload.update(
        {
            "bundle_id": f"serving-bundle:{RELEASE_ID}",
            "release_id": RELEASE_ID,
            "database_name": "miroflow_candidate_s12e_20260801_v1",
            "index_target_id": f"index:{RELEASE_ID}",
            "index_root": "/var/tmp/mirothinker-canonical-v2-s12e/index",
            # The complete candidate runner pins the envelope path by release
            # prefix; candidate-s12e-* falls to the fixed s12a evidence path.
            "envelope_path": str(
                GATE / "s12a/complete-candidate-build-envelope.json"
            ),
        }
    )
    bundle = RecordedServingBundle.model_validate(payload)
    rendered = json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        indent=1,
        sort_keys=False,
        allow_nan=False,
    ) + "\n"
    OUTPUT.write_text(rendered, encoding="utf-8")
    readback = RecordedServingBundle.model_validate_json(
        OUTPUT.read_bytes(),
        context={"external_content_addressed": True},
    )
    if readback != bundle:
        raise RuntimeError("s12e serving bundle readback differs")
    print(f"{OUTPUT} {bundle.content_sha256}")


if __name__ == "__main__":
    main()
