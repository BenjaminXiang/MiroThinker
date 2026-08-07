# Verification Contract: fix-professor-ambiguity-intro-rule

## Status

Candidate historical implementation; type-only GREEN is insufficient.

## Local invariant

The ambiguous-intro rule does not consume academic-title professor queries, while title-less names
remain ambiguous. Local deterministic tests may prove only this classifier seam.

## Promotion gate

`close-retrieval-generation-contract` Slice A owns full classifier row fields, Slice B owns grounded
response behavior, and Slice C0 owns normalized name, professor endpoint/ID, citation, semantics,
regression, and latency for Q004/Q017.

## Archive

After linked acceptance, archive only with `--skip-specs`; the umbrella owns canonical behavior.
