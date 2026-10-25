# Tasks: anchor-standalone-professor-relations

- [x] 1.1 Add `create_local_entity_resolver` over the audited lookup view (exact name forms, professor/company, ambiguous → None).
- [x] 1.2 Anchor relation-intent single-turn requests in the chat planning request (resolver attached to the chat adapter; no planner-internal request mutation).
- [x] 1.3 Add regression tests: standalone professor→company anchors; standalone professor→paper anchors; company→professor anchors; ambiguous name declines; unrelated query unchanged.
- [x] 1.4 Live verification: `丁文伯创办的公司是哪家` cites the local company/relationship evidence or a correct public source; `丁文伯有哪些专利` no longer names 丁文博/丁文胜 as him.
- [x] 1.5 Deploy to the customer site, restart, and record evidence.
- [x] 1.6 Add a full-projection company→patent counter and a chat count fast path (relationship-lane candidates are capped).
- [x] 1.7 Live verify `本地知识库收录了优必选多少专利` → 450.

- [x] 1.8 Render the professor fields the pack carries (department/email/homepage/counts/education/work/awards/company roles) and all company-role labels.
- [x] 1.9 Harden same-name extraction (`王伟教授` → `王伟`), prefix-match institution constraints, add the named-professor local-claim guard, and prefer the displayed professor on `他/她` attribute turns.
- [x] 1.10 Attach the exact-name resolver and company→patent counter in the admin composer (runner parity).
- [ ] 1.11 Live verify on the customer site: field query, fake-name guard, professor→paper follow-up anchor, and full golden-set regression.
