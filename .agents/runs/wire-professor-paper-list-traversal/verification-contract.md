# Verification Contract: wire-professor-paper-list-traversal

## Status

Candidate historical implementation; local payload delivery is not end-to-end acceptance.

## Local invariant

A professor-anchored paper-list intent reuses the verified-paper helper and does not change a plain
profile request. Local tests may prove only helper/route/candidate delivery.

## Promotion gate

`close-retrieval-generation-contract` Slice A owns the fixed ID oracle, Slice B owns evidence and
citation/generation, and Slice C1 owns complete predicate/pagination/topic-port semantics. Every
linked retrieval, citation, semantic, regression, and latency gate is conjunctive.

## Archive

After linked acceptance, archive only with `--skip-specs`; the umbrella owns canonical behavior.
