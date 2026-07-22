# Source Links

## User-confirmed requirements

- `.agents/runs/canonical-v2-logical-rebuild/requirements-grill.md`
- `.agents/runs/canonical-v2-logical-rebuild/outcome-requirements.md`
- `CONTEXT.md`
- `docs/architecture-decisions/ADR-013-canonical-v2-hybrid-enumeration-coverage.md`
- `docs/architecture-decisions/ADR-014-canonical-v2-internal-person-projection.md`
- `docs/architecture-decisions/ADR-015-canonical-v2-internal-technology-model.md`
- `docs/architecture-decisions/ADR-016-product-capability-remains-answer-scoped.md`
- `docs/architecture-decisions/ADR-017-web-only-entities-use-session-handles.md`
- `docs/architecture-decisions/ADR-018-machine-readable-claim-level-case-contract.md`
- `docs/architecture-decisions/ADR-019-conditional-structured-continuation-offers.md`
- `docs/architecture-decisions/ADR-020-local-safety-questions-use-safety-guidance.md`
- `docs/architecture-decisions/ADR-021-confidence-gated-entity-ambiguity.md`
- `docs/architecture-decisions/ADR-022-llm-selected-assessment-dimensions.md`

## Authoritative product/data sources

- `docs/Data-Agent-Shared-Spec.md`
- `docs/Agentic-RAG-PRD.md`
- `docs/Company-Data-Agent-PRD.md`
- `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`
- `docs/Professor-Requirement-Review-2026-05-10.md` — explicit locked decisions override the
  Professor audit where they differ; the audit plus review replace the legacy Professor PRD
- `docs/Paper-Data-Agent-PRD.md`
- `docs/Paper-Requirement-Review-2026-05-10.md` — explicit locked decisions override the Paper PRD
  where they differ
- `docs/Patent-Data-Agent-PRD.md`
- `docs/Multi-turn-Context-Manager-Design.md`
- `docs/测试集答案.xlsx` — its query/answer rows are high-value case-specific requirement evidence and
  seed scenarios; prose/key points are not normative pass/fail truth, a generalized answer template,
  or the sole acceptance source

For Canonical V2 domain-catalog work, precedence is the active OpenSpec behavior contract, then the
shared data-agent contract, then each domain's authoritative PRD/audit plus its explicit locked
review decisions, then accepted S2 coverage evidence. Legacy code and workbook vocabulary are
evidence, not schema authority.

## Existing OpenSpec capabilities affected

- `openspec/specs/paper-identity-status/spec.md`
- `openspec/specs/professor-retrieval-index-split/spec.md`
- `openspec/specs/paper-web-attribution-gate/spec.md`
- Active overlapping changes including `add-web-augment` and
  `close-retrieval-generation-contract` must be reconciled before dependency use.

## Recovery evidence

- `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/FORENSIC-CHECKPOINT.md`
- `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/RECOVERY-EXPERIMENT-REPORT.md`
- `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/LOGICAL-REBUILD-PLAN.md`

Recovery evidence is an input and constraint, not a statement of desired behavior.
