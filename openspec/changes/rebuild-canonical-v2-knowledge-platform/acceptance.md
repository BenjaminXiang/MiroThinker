# Acceptance: rebuild-canonical-v2-knowledge-platform

This file defines the lean final-milestone acceptance contract confirmed by the user on
2026-07-26. Historical slice evidence remains in `change-log.md` and `.agents/runs/`; it does not
create additional gates for the remaining work. OpenSpec completeness alone is not product
acceptance.

## 0. Rebaseline decisions

- [x] The customer-provided `docs/测试集答案.xlsx` is the normative case-specific Ground Truth for
      its 17 conversation groups and 25 query turns.
- [x] Workbook query, answer, and key points are interpreted together; an explicit key-point
      correction overrides the inaccurate part of historical answer prose.
- [x] Semantic equivalence is evaluated without requiring wording imitation or loading workbook
      answers as runtime knowledge.
- [x] Task 2.8 contract review, exclusion review, blind calibration, scaled human labeling, and LLM-
      judge acceptance gate are retired. Their artifacts remain non-normative history.
- [x] Separate aggregate Tasks 8.1, 8.8, and 9.8 are retired in favor of the real-runtime benchmark
      milestone in Task 12.3.
- [ ] Production-like promotion, archive, or destructive cleanup remains a separate explicit user
      authorization after final isolated acceptance.

## 1. Preserved safety and architecture invariants

- [x] Original PostgreSQL and Milvus identities are recorded; original PostgreSQL remains paused and
      the original Milvus is not opened by Candidate work.
- [x] Destructive migration, build, or test paths require an explicit disposable or isolated target
      and fail closed on missing or ambiguous target identity.
- [x] Recovery and historical sources are consumed only through verified copies or immutable landing
      artifacts; no accepted path writes an original source.
- [x] Canonical facts and relationships retain evidence lineage, identity decisions, proportional
      time semantics, and release identity.
- [x] Professor, Company, Paper, and Patent remain the only public domains. Internal Person and
      Technology projections remain auxiliary, and Product capability remains answer-scoped.
- [x] Online query, Web, LLM, answer, and feedback paths cannot mutate canonical identity, source
      mappings, active canonical data, or active indexes.
- [x] Candidate publication and rollback mechanics fail closed on release/index mismatch and cannot
      alter active pointers without explicit authorization.

## 2. Serviceable four-domain Candidate

- [x] The isolated Candidate contains non-zero, source-grounded Professor, Company, Paper, and Patent
      populations.
- [x] The Candidate contains the evidence-backed relationship paths needed by the customer workbook,
      including its Professor/Company, Professor/Paper, and Company/Patent or Product questions where
      the admitted sources support them.
- [ ] Every workbook entity and material expected fact is retrievable from admitted local evidence or
      bounded current-Web evidence; a missing item remains a visible product gap and is not
      removed from the benchmark.
- [x] Lookup documents and vector points are built from the same Candidate release with no unexplained
      missing, extra, stale, or cross-release identities.
- [x] A content-addressed read-only serving bundle binds the Candidate database, lookup/vector
      projections, policy/model configuration, and real chat runtime without changing an active
      release pointer.
- [x] The normal chat UI and API can use that bundle end to end; the retired `/review` workflow is not
      an acceptance dependency.

## 3. Customer benchmark behavior

- [x] All 17 workbook conversation groups and 25 query turns execute through the same chat API,
      retrieval, Web, answer, and session path used by the user.
- [ ] Multi-turn groups preserve workbook order, anchors, displayed sets, protected constraints, and
      relationship direction rather than replaying follow-ups as context-free prompts.
- [ ] Actual answers preserve the Ground Truth's material identities, relationships, constraints,
      and conclusions. In particular, the Shenzhen Zhihang Wujie case does not mix in Shenzhen
      Zhihang UAV Company.
- [ ] Newer official evidence may supplement or supersede a time-sensitive workbook fact only when
      the answer identifies the newer source and as-of distinction.
- [ ] Material identity, relationship, role, capability, date, number, and consequential assessment
      claims have local or current-Web evidence. Evidence absence produces an explicit limitation,
      not a model-memory completion.
- [x] Every normal information request invokes bounded Web search alongside applicable local lanes,
      and relevant local plus current-Web evidence is available to final LLM synthesis. Refusal,
      clarification, safety, and interface-control inputs remain exempt.
- [x] Every normal information request invokes Bocha and Serper concurrently within the existing
      outer Web budget, deduplicates normalized URLs after merge, retains actual provider provenance,
      and degrades to one provider or local evidence without losing usable results.
- [x] After a complete idle interval, one bounded background cycle keeps Bocha, Serper, embedding,
      and prose-LLM paths warm; real requests never wait for it, activity suppresses unnecessary
      cycles, shutdown stops it, and it creates no chat/session/evidence/canonical/index writes.
- [x] Normal information answers use the configured LLM renderer; deterministic grounded text is
      used only for a typed provider/output failure and does not silently become the normal path.
- [x] A local-heavy result set cannot consume the complete final candidate or claim budget: bounded
      current-Web evidence remains available to the same final LLM call without a keyword-specific
      query gate or an additional LLM stage.
- [x] A displayed-set Product-capability follow-up can confirm a Product only from direct retrieved
      Product-capability evidence, distinguish indirect Company or elevator-integration evidence,
      and identify unsupported candidates without converting the online claim into canonical data.
- [x] Public current-Web citations are emitted only when their official hostname is explicitly
      trusted or validated against the same canonical entity's retained official URL; arbitrary
      search-result and internal URLs remain hidden.
- [x] The Ding Wenbo founder follow-up states that Ding Wenbo participated in founding Shenzhen
      Wujie Zhihang Technology Co., Ltd. from the retained relationship evidence before summarizing
      relevant Company information.
- [x] Public chat responses expose only validated official public source links and contain no
      `/browse` URL, private-network URL, internal evidence locator, raw evidence payload, release ID,
      retrieval trace, or selector trace.
- [x] The chat UI keeps `查看依据` collapsed by default, expands only official public sources, and
      renders no internal trace cards or Canonical implementation footer.
- [x] A human-readable report presents each query, Ground Truth, actual answer, material sources,
      limitations, execution status, and any likely semantic mismatch. Automated or LLM comparison
      is advisory only.
- [x] Production query, retrieval, and answer code contains no workbook-row, case-ID, exact-query, or
      reference-answer shortcut.

## 4. Minimal engineering verification

- [x] During implementation, approximately eight representative real-chat smoke cases cover single-
      turn, multi-turn, cross-domain, same-name identity, conditional Web, and insufficient-evidence
      behavior. New focused regressions are added only for observed defects or high-risk changes.
- [x] One final Candidate smoke verifies four-domain population, required relationship reach,
      serving-bundle identity, lookup/vector parity, original-source isolation, and unchanged active
      pointers.
- [x] Changed-module tests pass. Changed Python files pass focused Ruff and Pyright checks.
- [x] Focused tests prove dual-provider merge/provenance/failure behavior and deterministic idle,
      activity, non-overlap, and shutdown semantics; real timing evidence covers warm and post-idle
      requests without weakening answer or public-evidence behavior.
- [x] One real same-session hotel-robot replay narrows the displayed supplier set to Shenzhen Pudu,
      excludes Beijing-headquartered Yunji, confirms FlashBot Arm mechanical-arm elevator operation,
      and confirms access-card/door operation from direct retrieved Product evidence.
- [x] `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and `git diff --check`
      exit successfully.
- [x] Repeated full-suite runs, independent slice reviews, blind calibration, scaled human labels,
      duplicate evidence envelopes, and a second final reviewer are not required unless a concrete
      regression or safety risk makes one necessary.

## 5. Final acceptance and cutover

- [x] The isolated chat system is started on `0.0.0.0` and its reachable URL is provided to the user.
- [ ] The user directly evaluates the running chat system and explicitly accepts or rejects the
      Candidate. Automated success cannot mark the Candidate Accepted.
- [ ] Until separate cutover authorization is given, original sources remain frozen, active release
      pointers remain unchanged, and no production-like promotion, archive, or cleanup occurs.
