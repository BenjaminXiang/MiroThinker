# Spec delta: canonical-v2-embedding-identity (new capability)

## ADDED Requirements

### Requirement: One embedding authority SHALL govern a release, its index, and its serving boot

A release SHALL be built with exactly one embedding authority — the
`(content_sha256, dimension)` pair the loader accepts, together with the model id,
the route and the credential slot the bundle records. The build SHALL refuse an
adapter whose model id differs from the release policy; the serving boot SHALL
refuse a pack, a persisted vector matrix, or a serving bundle whose
`embedding_model_id` or dimension differs from the release policy. Crossed pairs
(a candidate digest with the pre-switch dimension, or the pre-switch digest with
the candidate dimension) SHALL be refused, never reconciled.

#### Scenario: the rebuilt release carries the candidate identity end to end
- **GIVEN** the candidate embedding bundle and a full rebuild of the accepted source set
- **WHEN** the build completes and the pack is sealed
- **THEN** the release policy's embedding model, the `vector_matrix.npz` meta, the pack manifest and the serving bundle all name the candidate model at 1024 dimensions, and the point count equals the run16 point count

#### Scenario: the pre-switch adapter cannot read the new index
- **GIVEN** the rebuilt 1024-dimension index and the pre-switch 4096-dimension embedding authority
- **WHEN** a serving boot or a read is attempted with the pre-switch bundle
- **THEN** the boot fails closed with a pack/matrix identity error, and no query is answered from a mixed vector space

#### Scenario: a bundle that claims one provider and carries another identity is refused
- **GIVEN** a candidate bundle document whose provider, model, dimension, address, credential slot or content hash differs from its frozen authority
- **WHEN** the loader is asked for an adapter
- **THEN** the load raises, and no HTTP request is issued

### Requirement: The gateway route SHALL be part of the frozen identity

The gateway's OpenAI-compatible route and its DashScope-native route SHALL each be
represented by their own frozen bundle. Exactly one route SHALL be used for both
the rebuild and the serving of one release; the routes SHALL NOT be mixed, because
the same text embedded through both is measurably not the same vector (cosine
0.808–0.920). Changing the route for an existing release SHALL require a rebuild.

#### Scenario: rebuild and serving agree on the route
- **GIVEN** an index rebuilt through the OpenAI-compatible route
- **WHEN** the serving boot loads the native-route bundle of the same model
- **THEN** the boot fails closed rather than mixing two pipelines' vectors

#### Scenario: the address is configurable, the identity is not
- **GIVEN** an operator-supplied effective base URL for the embedding endpoint
- **WHEN** the adapter is loaded
- **THEN** the request goes to the effective address while the model id, the dimension and the credential slot stay those of the frozen bundle, and a changed model, dimension or content hash still refuses the load

### Requirement: The cutover SHALL require the calibrated recall non-regression gate

No cutover SHALL happen before the recall gate defined by
`.agents/runs/embedding-model-switch/protocol.md` has been run against a scratch
instance booted from the new pack, twice, with the second pass judged by `--diff`
against both the frozen pre-switch baseline and the frozen pre-switch control. A
FAIL verdict SHALL block the cutover; a REVIEW verdict SHALL require a recorded
human decision naming the case and the reason. The capture SHALL run with the
turn-debug and turn-trace directories enabled, because a capture without the
candidate layer degrades to a coverage REVIEW instead of a pass.

#### Scenario: a labeled entity disappears from both layers
- **GIVEN** a labeled entity that the baseline had in the candidate set and in the answer
- **WHEN** the judged pass has it in neither
- **THEN** the verdict is FAIL and the cutover does not proceed

#### Scenario: concept strings flip without an entity loss
- **GIVEN** a case whose 关键点 wording changes while the labeled entities of that case are unchanged
- **WHEN** the judged pass is diffed
- **THEN** the verdict is REVIEW, and the gate is not read as a pass or as a fail without a human decision

#### Scenario: the capture lacks the candidate layer
- **GIVEN** a switched instance started without the turn-debug directory
- **WHEN** the diff runs
- **THEN** the affected cases are reported as REVIEW coverage gaps, and the captured run SHALL NOT be used as acceptance evidence

### Requirement: The switch SHALL be reversible from artifacts left on disk

The pre-switch pack, index root, embedding bundle and serving bundle SHALL remain
present and unmodified through the switch window. Rollback SHALL be the previous
serve command restored and the service restarted — no rebuild, no restore from
backup — and SHALL return the pre-switch release identity.

#### Scenario: rollback returns the pre-switch release
- **GIVEN** a completed cutover to the new pack
- **WHEN** the previous command file is restored and the service restarts
- **THEN** the served release id, index marker and embedding model are the pre-switch ones, and the new pack and index remain on disk untouched

#### Scenario: the old artifacts survive the window
- **GIVEN** the switch window has finished
- **WHEN** the pre-switch pack directory and index root are inspected
- **THEN** their files and recorded hashes are byte-identical to the pre-window state

### Requirement: The gateway credential SHALL live in its own slot and SHALL NOT be logged

The candidate bundle SHALL read the credential from
`env:CANONICAL_V2_EMBEDDING_API_KEY` only. The local endpoint's credential slot
(`API_KEY` / `OPENAI_API_KEY` / `SGLANG_API_KEY` / `.sglang_api_key`) SHALL NOT be
used for any bundle that addresses a third-party host, and no secret value SHALL
appear in a command file, an artifact, or a log line.

#### Scenario: the local slot cannot leak to the gateway
- **GIVEN** a set local credential and an unset gateway credential
- **WHEN** the candidate adapter embeds
- **THEN** it raises without issuing any HTTP request

#### Scenario: the command file names the slot, not the value
- **GIVEN** the cutover serve command
- **WHEN** it is inspected
- **THEN** the gateway key is obtained from the process environment or a key file path, and no literal key material is present anywhere in the repository or the run artifacts

### Requirement: The switch SHALL change the embedding identity only

The rebuild SHALL consume the same frozen source manifest, the same accepted
restore root and the same cleaning/projection rules as the release it replaces;
the released objects, row counts and relationship graph SHALL be unchanged apart
from the embedding identity. Any other difference SHALL be treated as an
unintended change and stopped, not accepted as part of the switch.

#### Scenario: a rebuild with a different source set is stopped
- **GIVEN** a rebuild launched with a source manifest whose content hash differs from the accepted one
- **WHEN** the build starts
- **THEN** the runner refuses before any index is written

#### Scenario: the object inventory is compared after the rebuild
- **GIVEN** the completed new release
- **WHEN** its object counts and source hashes are compared with the pre-switch release
- **THEN** they match, and only the embedding model, the vector matrix and the identity documents differ
