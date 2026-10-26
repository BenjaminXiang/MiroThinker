# Verification contract: version-customer-runtime

## Classification

Standard, behaviour-preserving adoption. The customer-visible behaviour already
exists on the deployed host; this change makes it versioned, tested and
drift-checked. No retrieval, answer, schema or API semantics are changed.

## RED artefacts

| Behaviour | RED source | Why it is a real red |
|---|---|---|
| Topic-professor anchor guard | `apps/admin-console` chat adapter unit test calling `_standalone_anchor("有哪些做具身智能和灵巧手的教授", resolver)` | On the pre-backport branch the same call returns a company anchor; the guard does not exist |
| Generic appellation blocklist | entity-name-form test over a synthetic index | Pre-backport, `教授` is indexed as a canonical name and matches |
| Cache envelope gate | answer-cache validator test with a mixed-citation envelope | Pre-backport, `local_only` rejects every mixed answer, so the validator returns False |
| Professor claim fields | manual-recall serializer test | Pre-backport, `email/homepage/paper_count/education_history/company_roles` are dropped |

RED proof for adopted hunks (behaviour already shipped): revert the specific
hunk on a scratch copy of the file, run the new test, observe failure, restore.

## GREEN definition

- New tests pass on `hotfix/customer-20261026`.
- Targeted existing suites for the touched modules pass (record counts).
- Drift check reports zero differences against the deployed host.

## Allowed mode

TDD for the deterministic modules (cache validator, name forms, serializer).
The chat adapter test is a unit test on the guard function; no eval run is
required because no retrieval/answer behaviour changes. A replay run is **not**
part of this change — it is required by the next change that actually switches
the customer site.

## Out of scope

- Pack rebuild, data migration, customer-site restart.
- Merging the three lineages.
