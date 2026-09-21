# Spec delta: canonical-v2-serving-runtime

Capability `canonical-v2-serving-runtime` (declared by
`serving-index-process-scope`; not yet migrated into `openspec/specs/`). All
requirements below are **ADDED** by this change except where marked MODIFIED.

## ADDED — Requirement: embedding lane transport failures degrade, never fail the turn

The serving read path MUST distinguish *transport* failures of the embedding
provider from *integrity* failures of the embedding result.

- Transport failures are the builtin exceptions `TimeoutError` (provider did not
  answer within the request timeout) and `ConnectionError` (the address is
  unreachable, refused, black-holed, or answers with a non-2xx status).
- The OpenAI-compatible embedding HTTP client MUST translate
  `httpx.TimeoutException` to builtin `TimeoutError` and
  `httpx.TransportError` / `OSError` / `httpx.HTTPStatusError` to builtin
  `ConnectionError`, preserving the original exception as `__cause__`.
- The release-bound validating adapter MUST re-raise builtin `TimeoutError` /
  `ConnectionError` unchanged and MUST keep wrapping every other delegate failure
  as `IsolatedKnowledgeReadIntegrityError`.
- When the vector lane fails on transport, the turn MUST complete with evidence
  from the other lanes and the vector lane's `RetrievalTrace` MUST carry
  `status="unavailable"`, `failure_kind` in `{"timeout","connection_failure"}`
  and `candidate_count=0`.
- The user-facing stream MUST NOT emit an error event for this case, and the
  access log MUST keep its normal (non-error) status.

### Scenario: black-holed embedding endpoint

- GIVEN a serving process whose effective embedding base URL is unreachable
- WHEN an ordinary question is asked
- THEN the stream ends with a normal answer, no `event: error` frame
- AND the retrieval trace shows the `vector` lane `unavailable` with a transport
  `failure_kind`
- AND no `IsolatedKnowledgeReadIntegrityError` is raised.

### Scenario: genuine integrity failure still fails closed

- GIVEN an embedding delegate that returns a wrong-dimension / non-finite /
  wrong-model-id / non-deterministic vector
- WHEN the vector lane runs
- THEN `IsolatedKnowledgeReadIntegrityError` propagates (the turn fails closed).

## ADDED — Requirement: bounded vector-lane wait

`KnowledgeRead.execute` MUST apply an outer wall-clock wait to the `vector` lane
future, mirroring the existing web-lane outer-wait pattern.

- Default: 8 seconds; configurable through the environment variable
  `CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS` (managed-config naming convention;
  a non-positive or unparsable value falls back to the default).
- On expiry the lane is recorded `status="unavailable"`, `failure_kind="timeout"`
  and the turn continues.

### Scenario: hung adapter

- GIVEN a vector lane whose delegate blocks forever
- WHEN the plan executes
- THEN the lane returns within the configured cap (≤ cap + one poll interval)
- AND the turn completes with the other lanes' evidence.

## ADDED — Requirement: consecutive-failure breaker for the vector lane

- After 2 consecutive vector-lane transport failures the lane MUST be skipped
  without a provider call for a 300-second window.
- A skipped attempt MUST be reported as `status="unavailable"` with a transport
  `failure_kind`, and MUST NOT be reported as a success.
- A successful attempt resets the consecutive-failure count; a successful
  attempt after the window closes resets the lane to healthy.
- The provider keep-warm path MUST consult the same breaker state before calling
  the embedding provider (a skipped warm call is not a failure).

### Scenario: permanently down endpoint

- GIVEN 2 consecutive vector-lane transport failures
- WHEN further turns are served inside the window
- THEN no embedding provider call is issued for the vector lane
- AND each such lane row is `unavailable` with a transport `failure_kind`
- AND after the window a probe attempt is allowed again.

## ADDED — Requirement: effective embedding endpoint resolution

The effective embedding base URL MUST be resolved at one point, with this
precedence:

1. the process environment variable `CANONICAL_V2_EMBEDDING_BASE_URL` (populated
   at startup from the managed setting `extraction_endpoints.embedding_base_url`
   by the managed-runtime projection, or set directly by the service unit);
2. otherwise the address recorded in the embedding bundle document.

The resolved value MUST be a non-empty `http` or `https` URL; any other value
MUST be rejected as a configuration error rather than silently used.

### Scenario: operator points the endpoint at a customer address

- GIVEN the managed setting is set to an operator-chosen `http(s)` address
- WHEN the serving process boots
- THEN the embedding adapter uses that address
- AND the bundle on disk is neither edited nor resealed.

### Scenario: unset

- GIVEN `CANONICAL_V2_EMBEDDING_BASE_URL` is unset or empty
- WHEN the serving process boots
- THEN the embedding adapter uses the address recorded in the bundle.

## MODIFIED — Requirement: frozen embedding *identity* (was: frozen document equality)

`load_content_addressed_embedding_adapter` MUST keep proving the embedding
identity and MUST NOT require the address to equal a frozen literal.

- MUST still require `schema_version`, `provider`, `model_id`
  (`Qwen/Qwen3-Embedding-8B`), `dimension` (4096), `api_key_source`,
  `batch_size`, `max_workers`, `timeout_seconds`, and
  `content_sha256 == _QWEN_EMBEDDING_BUNDLE_SHA256`.
- MUST accept a `base_url` that is a non-empty `http(s)` URL, whether it equals
  the recorded address or the operator-configured one.
- MUST reject a `base_url` that is empty, non-string, or not `http(s)`.

### Scenario: identity fields still gate the load

- GIVEN a bundle differing in `model_id`, `dimension` or `content_sha256`
- WHEN the adapter is loaded
- THEN loading fails with a configuration error.

### Scenario: a changed address no longer gates the load

- GIVEN the operator-configured address differs from the bundle's recorded one
- WHEN the adapter is loaded
- THEN loading succeeds and the adapter embeds against the operator address.

## MODIFIED — Requirement: admin reports the runtime-effective embedding connection

`resolve_embedding` MUST resolve the effective base URL with the same precedence
as the serving process and MUST report it as the connection's `base_url` with an
`endpoint_origin` that names the winning source (environment/managed file vs
bundle default). A non-empty effective address is what the admin connection test
probes.

The managed field `extraction_endpoints.embedding_base_url` MUST be editable on
the admin config page (it now has a runtime reader) and its copy MUST NOT claim
the endpoint is frozen. `extraction_endpoints.embedding_model` remains read-only
with copy stating the model identity is frozen, because changing it would
invalidate the whole vector index.

### Scenario: page copy matches runtime

- GIVEN the config page payload
- WHEN the embedding row is rendered
- THEN the address row is editable, the model row is not, and neither claims the
  address is frozen.

## ADDED (round 2) — Requirement: the vector lane's wait is operator-visible configuration

`serving.vector_lane_timeout_seconds` (managed settings, projected to
`CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`) MUST be the operator-facing form of
the vector lane's outer wait.

- Default 8 s; values MUST be `> 0` and `<= 120`; an out-of-bounds save MUST be
  refused with the field path named in the message.
- The serving path MUST resolve the wait in exactly one place, with the
  environment value winning over the default, and an unparsable or non-positive
  environment value falling back to the default (never to "no cap").
- A managed value equal to the default MUST NOT be projected into the
  environment.

### Scenario: an operator tightens the wait

- GIVEN the operator saves 12.5 s on the page
- WHEN the service restarts
- THEN the environment carries `12.5` and the vector lane waits at most 12.5 s
- AND the page shows the row as editable with its bounds.

### Scenario: an absurd value

- GIVEN a save of 0, a negative number, or 121 s
- WHEN the page submits it
- THEN the write is refused and the message names
  `serving.vector_lane_timeout_seconds`.

## ADDED (round 2) — Requirement: the embedding connection test verifies endpoint identity

Because the embedding address is operator-configurable, the admin connection
test for the embedding connection MUST be able to answer "is this endpoint in
the same embedding space as the index?" — a wrong space fails every transport
check while silently corrupting every ranking.

- The check MUST run on request (`identity_check`), and MUST NOT add calls to the
  default single-call connection test.
- **Reference arm**: the same fixed probe string embedded at the recorded
  (bundle) address and at the configured address; cosine ≥ 0.999 ⇒ same space.
- **Index arm** (fallback when the reference is unavailable, or when the
  configured address *is* the recorded one): one deterministic document's
  verbatim `embedded_content` from the mounted serving pack, embedded with the
  configured endpoint, compared against the vector the index already stored for
  that document; cosine ≥ 0.99 plus "the document is its own nearest neighbour"
  over a bounded sample of the persisted matrix.
- The response MUST name the arm that ran, the measured cosine, the threshold and
  a verdict. A failure MUST say the endpoint is not in the index's space and that
  it must not be switched to; a check that could not run MUST report "not
  verified" (`passed = null`) and MUST NOT report a pass.
- The probe MUST NOT modify the embedding bundle, the serving pack or the index,
  and MUST NOT echo the credential or an upstream response body.
- The embedding card MUST request the check and display the verdict.

### Scenario: a different model behind the same protocol

- GIVEN an endpoint that answers 200 with 4096-element vectors from another space
- WHEN the embedding card's test runs
- THEN the verdict is "not the same space", the cosine is reported, and the
  message tells the operator not to switch.

### Scenario: the same model at a new address

- GIVEN the configured endpoint serves the same model as the bundle records
- WHEN the embedding card's test runs
- THEN the reference arm passes with a cosine at least 0.999.

### Scenario: no reference endpoint, index deployed

- GIVEN the recorded endpoint is unreachable and the serving pack is mounted
- WHEN the embedding card's test runs
- THEN the index arm runs and passes only if the endpoint reproduces the index's
  stored vector for the probe document.
