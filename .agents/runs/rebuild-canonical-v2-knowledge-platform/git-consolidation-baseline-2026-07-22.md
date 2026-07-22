# Git Consolidation Baseline: Canonical V2 S11

## Status

Accepted as the sole local development baseline on 2026-07-22. The OpenSpec Epic remains In
Progress at `70/80`; accepting this Git baseline does not accept the Epic, close an open task, move
`main`, or authorize S12. S12 remains paused.

## Decision

The final accumulated S11 bytes are authoritative. Git cannot honestly reconstruct the historical
S7-S11 task commits because the intermediate blobs were never committed and the receipts retain
hashes rather than complete trees. The baseline therefore uses two independent local histories:

1. an exact aggregate recovery snapshot that preserves every nonignored byte; and
2. an aggregate formal import that excludes preview-only artifacts but retains all implementation,
   contract, and receipt-bound acceptance authority.

Neither commit is described as reconstructed task history.

## Exact identities

- Historical Git base and unchanged local `main`:
  `f0e6224e1c675c6d6c58993676783b2fbe0cd8f6`.
- Authoritative dirty source branch: `canonical-v2-s2-baseline`.
- Authoritative pre-write status SHA-256:
  `7bbd1bc6269ea9b8cddcf4c67532e296bbb0748e8bde076c771e2b2968bc5bf5`.
- Authoritative pre-write real-index SHA-256:
  `a17873ba3fc6f0ceb81450450c019196d91d4526872941b468b1df488dafe06a`.
- Recovery branch: `codex/canonical-v2-s11-recovery-20260722`.
- Recovery commit: `8fd5f26c0749599860d4a08a26e6a9694d05a017`.
- Recovery tree: `cab28d6985c886e40840662b8ef7e98ef5291f36`.
- Consolidation branch: `codex/canonical-v2-s11-consolidation`.
- Aggregate import commit: `641278f01b005c66bd356533d4df0fd11b678394`.
- Aggregate import tree: `8b2585502808a512386cddf41e18e16950b9d029`.
- Relocation-safe S11C successor correction commit:
  `438c715190d4f8b5c2bbf9f29b6abe3899ec2330`.
- External archive SHA-256:
  `6aae79b70cd558c4ab0b9cfbb6cd02a7bce112978f8c357df2dbbd7c9c35ca2b`.
- Recovery bundle SHA-256:
  `10ad55b176f7713993b4d34503f0d8fe5c67c365b76f04d78b324f336a4ce29c`.
- Historical ignored root-helper sidecar archive SHA-256:
  `313ea9667c8f8339ac4d7a1f1e8aa5df3d71bb8401b63fb9b50e809dae58150d`.

The external archive is permission-restricted under
`/home/longxiang/.mirothinker_recovery/20260722T041501Z-canonical-v2-s11-consolidation/`. It contains
354 paths, and independent extraction reproduced all 354 per-file hashes exactly.

The sidecar archive
`external-root-helper-openai-client-compat.tar` preserves the historical ignored
`openai_client_compat.py` byte stream separately. Its extracted file SHA-256 is
`95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a`, matching the S11A receipt.
It remains historical provenance only: the current S11A Admin owner passes without adding this
external root to `PYTHONPATH`.

## Included and quarantined scope

The recovery commit contains all 354 changed/nonignored paths. The formal import contains 299 paths.
The following 55 preview-only paths remain recoverable from the archive, bundle, and recovery commit
but are absent from consolidation history:

```text
.agents/runs/rebuild-canonical-v2-knowledge-platform/frontend-preview-2026-07-21/
.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/
docs/superpowers/plans/2026-07-21-canonical-v2-real-data-preview.md
docs/superpowers/specs/2026-07-21-canonical-v2-real-data-preview-design.md
```

Receipt-bound S7/S8 evidence, both S9J screenshots, S11B baseline evidence, and all S11C evidence are
included. No ignored `.venv`, cache, coverage, build, original Milvus, or protected source artifact is
forced into either commit.

## Contract state

- OpenSpec change: `rebuild-canonical-v2-knowledge-platform`.
- Lifecycle: In Progress; not Candidate or Accepted as an Epic.
- Tasks: `70/80`.
- Acceptance criteria checked: `49/97`.
- Accepted implementation foundations: S1-S7, deterministic S8/S9 implementation slices, S10, and
  S11C, subject to their existing exact contracts and receipts.
- Open tasks: `2.8`, `8.1`, `8.8`, `9.8`, and `12.1` through `12.6`.
- No S12 implementation, production-like promotion, or Cutover is part of this baseline.

Key accepted receipt SHA-256 values remain:

```text
S9I   658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366
S9J   ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc
S10O  e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246
S11A  b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3
S11B  cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945
S11C  281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717
```

## Branch dispositions

| Branch | Disposition | Reason |
|---|---|---|
| `main` | historical durable S6; preserved | Remains `f0e6224`; no implicit promotion. |
| `canonical-v2-s2-baseline` | authoritative source; preserved | Dirty source bytes remain unchanged after recovery. |
| `codex/canonical-v2-s11-recovery-20260722` | recovery | Exact aggregate preservation; never a fabricated task history. |
| `codex/canonical-v2-s11-consolidation` | Accepted future parent | Clean aggregate import, relocation correction, and control-plane reconciliation. |
| `canonical-v2-s1-safety` | included ancestor; preserved | Fully reachable from `f0e6224`. |
| `codex/canonical-v2-task61-prep` | included code ancestor with separate untracked notes; preserved | No deletion or cleanup is authorized. |
| `codex/canonical-v2-s6c-db-red` | divergent-preserved | Unique Git commits remain; historical aggregate review says their behavior is superseded. |
| `codex/canonical-v2-s6d-red` | divergent-preserved | Unique RED commit remains; no deletion before a later cleanup decision. |
| `codex/canonical-v2-s6f-red` | divergent-preserved | Unique RED commit remains; no deletion before a later cleanup decision. |

All non-Canonical dirty worktrees and branches are outside this consolidation and remain untouched.

## Verification

Completed on the isolated consolidation worktree:

- `openspec validate rebuild-canonical-v2-knowledge-platform --strict` — valid.
- `PYTHONDONTWRITEBYTECODE=1 uv run alembic -c canonical_v2_alembic.ini heads` — unique head
  `C2_0011 (canonical_v2)`.
- Safe S7/S8 build/release/read owner matrix — `26 passed`.
- S11C evidence validator plus S11B consumer-migration owner — `58 passed`; this includes checkout
  relocation, live-filesystem-independent historical path checks, and the existing cwd/root/
  basetemp/hash tamper rejections.
- Current Admin S11A HTTP owner, without the historical ignored root helper on `PYTHONPATH` —
  `7 passed`.
- Focused Ruff check and format check for the relocation correction — passed.
- `git diff --check 641278f01b005c66bd356533d4df0fd11b678394..HEAD` — passed for the
  relocation correction and control-plane acceptance commits.
- `git diff --check f0e6224e1c675c6d6c58993676783b2fbe0cd8f6..HEAD` — exits `2` only on
  four verbatim imported, content-addressed historical artifacts; they are intentionally not
  whitespace-normalized because their exact hashes are acceptance authority:
  `.agents/runs/canonical-v2-provider-compat-self-contained/verification.md`,
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7i/implementation-plan.md`,
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/admin-no-external.xml`,
  and `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/admin-no-external.xml`. Their
  current SHA-256 values remain respectively
  `64ae8d8755a6cde55d26cf12c20fc3e0cb97a2ade664cd5d2219cc452e84c890`,
  `8c701a07be6c0fa84bb52e812725dc77928a6e1685fb27b76a6605060cbf336e`,
  `1feaf63e10e29eede180dd6098c787cfe4e51866c3b501ba62375fff55a96e5e`, and
  `9e03b138fb5628d7d91dd5f97330f8e44cd14c66e55bfe044f77da8b57966c29`.
- Strict receipt JSON/hash audit — S9I, S9J, S10O, S11A, S11B, and S11C receipt hashes match their
  recorded authorities; receipt-bound S9J/S11B/S11C evidence is present.
- Recovery audit — 354/354 archive paths independently rehashed; recovery bundle verified;
  recovery commit passed `git fsck --strict`.
- Scope audit — no changed symlink, nested repository, tracked binary, high-confidence credential,
  or forced ignored runtime/database artifact; 55 preview-only paths remain preserved only in
  recovery.
- Ledger audit — exactly `70/80` tasks and `49/97` acceptance checks; the ten open tasks are
  unchanged.
- Git identity audit — the dirty authority branch and real index remained unchanged, all divergent
  side branches remain reachable, and local `main` remains `f0e6224`.

Real PostgreSQL, Milvus, live providers, S2C external review, aggregate Tasks 8.8/9.8, and S12 are not
baseline checks and remain separately gated.

## Future development rule

Every new Ready slice must branch from the committed tip of
`codex/canonical-v2-s11-consolidation`; implementation content is anchored by correction commit
`438c715190d4f8b5c2bbf9f29b6abe3899ec2330`, followed only by this baseline's control-plane
acceptance commit. Each slice has one writer, one explicit contract, one independently verifiable
checkpoint, and serial integration only after acceptance. `main` movement, push, branch deletion,
and S12 activation remain separate user decisions.

## Rollback

No existing ref was moved. To abandon this baseline, stop using the consolidation branch/worktree.
The original dirty worktree, exact recovery ref, verified bundle, and external archive remain. No
recovery artifact may be removed until a later user-authorized cleanup verifies an independently
accepted successor.
