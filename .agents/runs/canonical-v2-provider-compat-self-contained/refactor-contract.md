# Refactor Contract: canonical-v2-provider-compat-self-contained

## Status

Accepted as of `2026-07-21T03:57:07Z` (UTC).

The external/root targeted final review reported `C0/I0` (`C=0`, `I=0`) and explicitly authorized
acceptance. The runtime-gate reconciliation, required checks, fresh-wheel proof, and final
unrelated-byte receipt comparison have evidence. Under the non-recursive sequence, these Accepted
documents are frozen before the write-once acceptance receipt is created.

Implementation began at `2026-07-21T03:27:37Z` (UTC) after the required dirty-worktree receipt was
captured. The focused subprocess RED was observed before any production edit.

Pre-Ready re-review completed at `2026-07-21T03:19:48Z` (UTC) with result `C0/I0` and
`Ready=yes`. Reviewed pre-Ready artifact hashes:

- `refactor-contract.md`:
  `bc3288c01b9cbf2f3d55b11dd272ed47157b05d70c7d3666afae1655b799829d`
- `verification.md`:
  `a412b3622e95055420cbaa48e97ee4c5058407a2dc169e57118c7a4670692160`

## Goal

Behavior-preserving repair so tracked data-agent providers resolve OpenAI compatibility exclusively
from tracked package-local code, never an ignored root helper, host working directory, or host
`PYTHONPATH`.

## Diagnosis and invariant

- `qwen.py` and `mirothinker.py` import top-level `openai_client_compat`, then dynamically load
  `<repo>/openai_client_compat.py` with `importlib` on failure.
- `.gitignore:252` ignores `/openai_client_compat.py`; it is absent from the current intentionally
  dirty worktree and is not a valid tracked runtime dependency.
- A clean import from an empty temporary cwd with `PYTHONPATH` removed exits nonzero with
  `FileNotFoundError` for `<worktree>/openai_client_compat.py`.
- Hatch packages `src`, so the compatibility helper belongs beside the providers.

Invariant: provider import and client construction use only tracked, packaged dependencies.

## Allowed future implementation scope

- Create `apps/miroflow-agent/src/data_agents/providers/openai_client_compat.py`.
- Modify `apps/miroflow-agent/src/data_agents/providers/qwen.py` only to relative-import that helper
  and delete the dynamic root loader and its unused imports.
- Modify `apps/miroflow-agent/src/data_agents/providers/mirothinker.py` only for the same change.
- Create
  `apps/miroflow-agent/tests/data_agents/providers/test_openai_client_compat.py`.
- After final `C0/I0` authorization only, create the finalization artifact
  `.agents/runs/canonical-v2-provider-compat-self-contained/acceptance-receipt.json` according to the
  acceptance sequence below. It is not an implementation input and must not be created at Candidate.

No other production, test, packaging, S11B, OpenSpec, or run artifact is in scope.

## Dirty-worktree receipt and scope guard

Use the existing worktree; do not create, switch to, or populate another worktree. Existing unrelated
dirty bytes are user-owned and must remain byte-for-byte unchanged.

Immediately before implementation, capture the complete raw output of
`git status --porcelain=v1 -z --untracked-files=all` to a temporary receipt, record its SHA-256 and a
lossless escaped/base64 rendering in `verification.md`, and record existence plus SHA-256 (or an
explicit `MISSING` marker) for all six allowed paths:

1. `apps/miroflow-agent/src/data_agents/providers/openai_client_compat.py`
2. `apps/miroflow-agent/src/data_agents/providers/qwen.py`
3. `apps/miroflow-agent/src/data_agents/providers/mirothinker.py`
4. `apps/miroflow-agent/tests/data_agents/providers/test_openai_client_compat.py`
5. `.agents/runs/canonical-v2-provider-compat-self-contained/refactor-contract.md`
6. `.agents/runs/canonical-v2-provider-compat-self-contained/verification.md`

The same receipt must identify every pre-existing dirty path outside those six; retain byte hashes for
those paths, including untracked files, so unchanged status alone cannot mask changed content. At
Candidate scope review, capture the same full status receipt and targeted hashes again. After excluding
the six allowed paths, pre/post status entries and pre-existing dirty-path hashes must match exactly,
and no unrelated path may appear, disappear, or change bytes. Only the four implementation paths and
these two documents may differ before acceptance authorization. The acceptance receipt may appear as
a seventh, finalization-only path only through the ordered acceptance sequence below.

## Behavior-preservation contract

- Preserve `QwenProvider` and `MiroThinkerProvider` public names, constructor signatures/defaults,
  injectable `client_factory`, `create_client()` arguments, and all request payloads/defaults.
- Preserve module-level `build_openai_client`, including its use by `dashscope.py` through `qwen.py`.
- Preserve the explicit keyword-only helper signature:
  `def build_openai_client(*, base_url: str, api_key: str, timeout: float) -> openai.Client`.
- Preserve primary construction with `openai.Client(base_url=..., api_key=..., timeout=...)`.
- Preserve both compatibility fallbacks: only `ImportError` containing `socksio` and `TypeError`
  containing `proxies` retry with the same arguments plus
  `openai.DefaultHttpxClient(timeout=timeout, trust_env=False)`; non-matching exceptions propagate.
- Tests must use fakes only and make no live provider/network call.

## RED contract

Add the focused test before implementation. It must use a fresh empty `tmp_path` as subprocess cwd,
remove `PYTHONPATH` from a copied environment, run `sys.executable -I`, and explicitly add only the
tracked `apps/miroflow-agent` package root. Separate cases must cover both provider modules and assert
that each module's `build_openai_client` and default provider factory are the exact object from
`src.data_agents.providers.openai_client_compat`, whose `__module__` and source path are package-local.

Use `subprocess.run(..., check=False, capture_output=True, text=True)` and then
`assert result.returncode == 0, result.stderr`. Before GREEN, focused pytest must collect normally and
fail at this assertion, not during collection. Record that RED transcript.

The focused file must also compactly cover primary construction, exact `socksio` and `proxies`
fallback calls, and propagation of non-matching errors.

## Implementation sequence

1. Add/run RED and record assertion failures for both providers.
2. Move the ignored helper behavior into the new package-local module.
3. Replace both loaders with `from .openai_client_compat import build_openai_client`; do not alter
   provider classes.
4. Run all checks and fresh-wheel proof; review only to `Candidate` with evidence.

## Required checks

```bash
cd apps/miroflow-agent
uv run pytest -n0 -W error tests/data_agents/providers/test_openai_client_compat.py
uv run pytest -n0 \
  tests/data_agents/test_runtime.py::test_provider_adapters_are_thin_and_configurable \
  tests/data_agents/test_runtime.py::test_mirothinker_provider_uses_compat_client_helper
# Visible diagnostic; acceptance rule below permits only the two recorded baseline failures.
uv run pytest -n0 tests/data_agents/test_runtime.py
uv run pytest -n0 tests/data_agents/providers/test_dashscope.py
uv run ruff format --check src/data_agents/providers/openai_client_compat.py src/data_agents/providers/qwen.py src/data_agents/providers/mirothinker.py tests/data_agents/providers/test_openai_client_compat.py
uv run ruff check src/data_agents/providers/openai_client_compat.py src/data_agents/providers/qwen.py src/data_agents/providers/mirothinker.py tests/data_agents/providers/test_openai_client_compat.py
uv run python -m py_compile src/data_agents/providers/openai_client_compat.py src/data_agents/providers/qwen.py src/data_agents/providers/mirothinker.py tests/data_agents/providers/test_openai_client_compat.py
uv run pyright src/data_agents/providers/openai_client_compat.py src/data_agents/providers/qwen.py src/data_agents/providers/mirothinker.py tests/data_agents/providers/test_openai_client_compat.py
```

The two exact `test_runtime.py` provider nodeids above are the mandatory pass gate and both must pass.
The full-file command remains a required visible diagnostic, but its nonzero result is allowed only
when it is unchanged from the recorded pre-existing baseline: exactly `13 passed, 2 failed`, with
both failures limited to these nodeids and signatures:

- `test_recommended_templates_delegate_to_shared_provider_entrypoints[recommended_client_template_mirothinker17_fp8.py-MiroThinkerProvider]` fails with `FileNotFoundError` for the ignored/missing root
  `recommended_client_template_mirothinker17_fp8.py`.
- `test_recommended_templates_delegate_to_shared_provider_entrypoints[recommended_client_template_35b_a3b.py-QwenProvider]` fails with `FileNotFoundError` for the ignored/missing root
  `recommended_client_template_35b_a3b.py`.

Both failures occur while loading the root template, before provider import, and derive from the
pre-existing `.gitignore:253` rule `/recommended_client_template_*.py`. Any additional failure,
different exception/path, changed count, or provider-node failure blocks acceptance. Do not create or
edit the ignored templates to make the diagnostic green.

Build a fresh wheel into a temporary directory and inspect it with isolated Python/`zipfile`. This is
only a narrow packaging proof from a dirty worktree, not a clean-build or release artifact. Assert
that `src/data_agents/providers/openai_client_compat.py` is included and no root-level helper is
included. From an empty cwd with `PYTHONPATH` removed, prepend only the fresh wheel to isolated
Python's import path—never the repository or app source tree—and import the helper, `qwen`, and
`mirothinker`. Assert all three `__spec__.origin` values are inside that wheel and both providers share
the packaged helper object. Then run `git diff --check` and the receipt-based final scope review.

## Forbidden actions and stop conditions

- No DB/index/application-or-provider network call, migration, benchmark, commit, push, PR, staging,
  or cutover.
- Do not edit or rely on the ignored root helper.
- Stop if behavior preservation requires an API, request/default, S11B, broader runtime change, or a
  packaging-configuration/dependency change beyond automatic inclusion of the package-local helper.

## Done means

Candidate requires the pre/post dirty-worktree receipts and hashes, recorded RED, all current check
evidence, narrow fresh-wheel isolated import proof, and a diff limited to the four allowed
implementation paths plus these two documents. It does not imply a clean/release artifact.

## Non-recursive acceptance sequence

Candidate evidence and Candidate snapshot hashes are review inputs, not final hash authority.
Acceptance must occur in this order:

1. An external/root reviewer performs the targeted final review and explicitly authorizes
   `C0/I0` (`C=0`, `I=0`). Without that authorization, stop at Candidate.
2. Mechanically update only `refactor-contract.md` and `verification.md` to status `Accepted`, adding
   the authorization result and UTC timestamp. Make no substantive implementation or evidence
   change in this step.
3. Freeze all six already-allowed files. Compute their final SHA-256 values only after both status
   updates are complete.
4. Atomically create the write-once
   `.agents/runs/canonical-v2-provider-compat-self-contained/acceptance-receipt.json` from a temporary
   sibling file. The receipt must contain:
   - schema name `canonical-v2-provider-compat-acceptance-receipt` and integer version `1`;
   - acceptance UTC timestamp and the authorized `C0/I0` result;
   - path-keyed final SHA-256 values for the four implementation files and two Accepted run docs;
   - the outcome of every required check, including the signature-locked full-runtime diagnostic;
   - wheel SHA-256 `86c2a78a764c5828186c648c00d5d1a5b38c67de5e3553d879c1e9b57c2345eb`;
   - unchanged unrelated-manifest path count `240` and digest
     `7c4beba1878e6a60eba60e249f8cad1da590034387e6dee88caa57eaef41883b`.
5. The receipt must not contain its own path hash or its own SHA-256. After receipt creation, do not
   edit any of the six referenced files; the receipt is also immutable. Any correction invalidates
   the sequence and requires a new targeted review before recreating the receipt.
6. External/root verification recomputes the receipt SHA-256, every referenced six-file SHA-256, the
   wheel hash, required-check outcomes, and the unchanged 240-path manifest digest. The externally
   reported receipt SHA-256 is the terminal authority; it is never embedded back into the receipt or
   either run document.

This ordering eliminates self-hash recursion: the two docs are finalized first, the receipt hashes
them second, and the receipt's own hash is computed and reported externally last.

## Rollback

Revert the helper/test additions and both relative-import changes atomically; no data rollback exists.
