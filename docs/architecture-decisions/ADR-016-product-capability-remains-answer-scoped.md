# ADR-016: Product capability remains answer-scoped

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Product capability claim, Material claim); ADR-015; OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S8-S10
- **Contract:** carried by the active OpenSpec query/answer/gap requirements before the
  affected slices are implemented

## Context and decision

Canonical V2 currently models Company products and Company capabilities separately. A product-level
canonical capability relationship would support structured traversal and reuse, but it would also
expand the accepted canonical catalog and require durable status/maturity semantics that are not yet
part of the confirmed model. Conversely, allowing answer generation to copy a Company capability to
one of its products would turn organizational potential or general feasibility into an unsupported
product fact.

This change will keep capability canonical at the Company level and will not add
`ProductCapabilityAssertion` or `product_has_capability` to Canonical V2. The answer stage may create
an answer-scoped `ProductCapabilityClaim` only when retrieved local or current-Web evidence directly
binds the named product and capability. The claim-evidence map must retain that direct evidence and
its source nature/time. Company-level capability, a general technology route, another product's
feature, or model plausibility may guide retrieval but cannot support the product claim.

When direct evidence is absent or does not distinguish claimed, demonstrated, and commercially
available behavior, the answer reports the product capability as unsupported or qualified rather
than inferring it. Repeated product-capability demand or missing evidence may create a typed offline
knowledge gap; it does not cause an online canonical write.

## Consequences

- S8 sufficiency treats each requested product capability as a separate material answer part and may
  run targeted bounded retrieval for direct binding evidence.
- S9 validates the answer-scoped claim, citation, qualification, and coverage status. It cannot use a
  Company capability edge as entailment for a Product claim.
- Product capability is unavailable as a canonical structured filter or reusable relationship
  traversal in this change; repeated answers may have to re-evaluate the evidence.
- S10 may prioritize recurring product-capability gaps for a later reviewed canonical-model extension.
- ADR-015 Technology relations must not be interpreted as an implicit product-capability contract.
- This ADR records the boundary decision but does not itself change the active OpenSpec behavior.

## Alternatives rejected

- **Canonical product-capability assertion:** stronger reuse and filtering, but requires catalog,
  maturity, temporal, publication, and migration contracts beyond the selected V2 boundary.
- **Free product capability text:** easy to populate but cannot prove direct product binding or
  prevent Company-level capability propagation.
