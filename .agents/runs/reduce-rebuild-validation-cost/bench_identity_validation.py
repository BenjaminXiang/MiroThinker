"""Time-based before/after benchmark for the identity-result revalidation.

Builds a person-method identity batch (half the sources carry an evidence-bound
ORCID, half do not, exactly like the internal-reference recall path) and times
`validate_identity_resolution_result`, which is what the run15 py-spy stack
showed consuming the identity phase.

Usage (no database needed):
    uv run python bench_identity_validation.py <label> [counts...]
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "apps" / "miroflow-agent"
TEST_MODULE = (
    APP_ROOT / "tests" / "canonical_v2" / "test_canonical_identity_resolution_contract.py"
)

spec = importlib.util.spec_from_file_location("identity_contract_helpers", TEST_MODULE)
helpers = importlib.util.module_from_spec(spec)
sys.modules["identity_contract_helpers"] = helpers
spec.loader.exec_module(helpers)

LABEL = sys.argv[1]
COUNTS = [int(value) for value in sys.argv[2:]] or [500, 2000]
REPEATS = 3


def build(module, count: int):
    sources = []
    assertions = []
    for index in range(count):
        bound = index % 2 == 0
        keys = {"name_key": f"bench person {index:05d}"}
        if bound:
            keys["orcid"] = f"0000-0001-2345-{index:04d}"
        source = helpers._source_identity(
            module,
            f"bench-person-{index:05d}",
            source_system="singleton-fixture",
            source_key=f"singleton:person:{index:05d}",
            entity_type="person",
            normalized_keys=keys,
        )
        sources.append(source)
        assertions.append(
            helpers._identity_assertion(
                module,
                f"assertion-bench-person-{index:05d}",
                source,
                field_path="identity.orcid" if bound else "identity.name",
                value=(
                    f"https://orcid.org/0000-0001-2345-{index:04d}"
                    if bound
                    else keys["name_key"]
                ),
            )
        )
    request = helpers._request(
        module,
        source_identities=tuple(sources),
        identity_assertions=tuple(assertions),
        identity_method_version="canonical-identity-resolution-person-v1",
    )
    return request


module = helpers._module()
for count in COUNTS:
    request = build(module, count)
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    durations = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        module.validate_identity_resolution_result(request, result)
        durations.append(time.perf_counter() - started)
    best = min(durations)
    print(
        f"{LABEL}: sources={count} assertions={count} "
        f"validate_best={best:.4f}s validate_all={[round(d, 4) for d in durations]}"
    )
