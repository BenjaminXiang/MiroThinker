# Verification contract: switch-embedding-model-to-qwen37-flash

Per `openspec/config.yaml` / AGENTS §4: written before production-code edits of
the change. This change is unusual in that the code it needs was already frozen by
two inert slices (`v2/embedding-model-switch`); what remains is a data/identity
switch, so the contract names which layer verifies which claim.

## 1. Layer map

| Claim | RED/GREEN artifact (this change) | Fixture source |
|---|---|---|
| The candidate identity is frozen and inert on the pre-switch path | `apps/miroflow-agent/tests/canonical_v2/test_embedding_model_switch_v2.py` (31 tests) — already GREEN on the lane, re-run in the merged switch line | local `ThreadingHTTPServer` stand-in; the real pack/index fixture in `test_serving_pack_no_milvus.py` |
| F1 still holds after the merge: gateway/native transport failures reach the lane's fail-open hook as builtin `TimeoutError`/`ConnectionError` | `apps/miroflow-agent/tests/canonical_v2/test_embedding_lane_fail_open.py`, `test_embedding_transport_classification.py` extended with a case per new adapter (T2.4) | constructed scenario (stub/real loopback), as in the F1 contract |
| F2 still holds after the merge: `resolve_embedding_base_url` + `base_url`-only exclusion cover both new authorities; `api_key_source` stays frozen | `apps/miroflow-agent/tests/canonical_v2/test_embedding_endpoint_resolution.py` extended (T2.5) | bundle-document fixture (the frozen candidate document, mutated one field at a time) |
| The new release's index was built by the candidate model | T5.4 matrix read-back (`dimension=1024`, `point_count=51026`, `embedding_model_id=qwen3.7-text-embedding-flash`) + T6.1 manifest `embedding_model_id` | the real rebuilt index |
| **Recall did not regress** | **scenario eval**: `apps/admin-console/scripts/eval_recall_canonical_v2.py` run twice against a scratch boot of the new pack, judged by `--diff` against the frozen `baseline.json` and `control.json` (exit 0 PASS / 1 FAIL / 2 REVIEW) | the frozen pre-switch captures (37 turns each, sha256 in `acceptance.md`) |
| Cutover is reversible | T8.3 rollback drill on the switched service, both directions, with the receipt/health identities compared | the live service (operator window) |

## 2. Why the recall gate is the blocking artifact and not a unit test

A vector-lane regression keeps the answer shape and only loses entities
(`protocol.md` §2), so no unit test and no behavioural replay assertion can see
it. The gate is also the only artifact whose oracle is *calibrated*: the same
configuration run twice moves the vector metric on 0/34 cases (so a > 30 % median
drop is a real signal) while the 关键点 strings flip on 6/11 (so they are
review-level). Anything that weakens those rules — dropping the run-twice
protocol, judging the cold pass, or scoring concept strings in the candidate
layer — invalidates this contract.

## 3. What is NOT claimed

* Rank movement inside the vector top-k, answer precision, multi-turn referent
  resolution (`protocol.md` §6/§9).
* That the gateway will behave the same at 1,595 calls as at one request; the
  rebuild's own failure mode (no in-pass checkpoint) is documented in the runbook
  rather than tested.
* That the two routes are interchangeable (they are measurably not).
