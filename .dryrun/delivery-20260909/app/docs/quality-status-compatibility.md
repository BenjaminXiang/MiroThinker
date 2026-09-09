# Quality Status Compatibility

## Canonical Shared States

| Canonical status | Meaning | Gate implication |
| --- | --- | --- |
| `ready` | Required identity, scholarly output signal, and release fields are present with no remaining review flag. | Pass |
| `needs_review` | Released, but summary or structured profile quality still needs human review. | Warn / fail strict quality gate |
| `low_confidence` | Reserved for future identity-confidence driven downgrade flows. | Warn / fail strict quality gate |
| `needs_enrichment` | Released, but discipline-appropriate scholarly output evidence or downstream enrichment signal is still missing. | Warn / fail strict quality gate |

## Legacy Compatibility

| Legacy/internal status | Canonical status | Notes |
| --- | --- | --- |
| `ready` | `ready` | No mapping change |
| `needs_review` | `needs_review` | No mapping change |
| `low_confidence` | `low_confidence` | No mapping change |
| `needs_enrichment` | `needs_enrichment` | Promoted to shared state |
| `incomplete` | `needs_review` | Retained as legacy detail code |
| `shallow_summary` | `needs_review` | Retained as legacy detail code |

## Current Implementation Notes

- Shared contract normalization lives in `apps/miroflow-agent/src/data_agents/contracts.py`.
- Professor quality gate emits canonical `quality_status` and keeps legacy detail in `quality_detail`.
- Professor scholarly output gate is discipline-aware: STEM still requires paper evidence; a narrow HSS subset may use official human-reviewed awards or social-science projects as fallback output evidence.
- Pipeline reports publish both `quality_distribution` and `quality_distribution_legacy`.
- Storage aggregation normalizes legacy values before counting.
