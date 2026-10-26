# Proposal: polish-professor-claims

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.3.

## Why

Two defects showed up the moment the paper overlay went live on the customer
site (2026-10-26):

1. **The count reads as a publication total.** The overlay counts papers in this
   pack's relationship graph, but the claim said `论文数：90`. Asked
   「王向荣一共发表了多少篇论文」 the synthesizer answered "至少 32 篇" from web
   evidence — the claim and the answer disagree because the label over-claims.
2. **Template summaries crowd the claim.** 53.8% of professor summaries are one
   sentence repeated ("该教授在深圳科创领域有持续贡献…"). The claim now also
   carries paper evidence, but the repeated text still occupies most of it.

## What Changes

1. A count injected by the overlay renders as `本地收录论文：N 篇`; a count that
   comes from the pack keeps the existing `论文数` label (pack values are not
   re-interpreted).
2. Professor `简介` collapses repeated sentences before truncation, so a template
   repeated five times appears once.

## Impact

- Claim text only; retrieval, routing and the pack are untouched.
- The repetition collapse applies to professor and company? No — professor claims
  only, where the template share was measured (53.8%).

## Out of scope

- Fixing the summaries at the source (a data-pipeline slice).
- Forcing the synthesizer to prefer a local count over a web figure (answer
  policy, separate evaluation).
