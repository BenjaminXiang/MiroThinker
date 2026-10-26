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
- [x] 1.11 Live verify on the customer site: field query (email/院系), fake-name guard (赵大锤 no substitution), professor→paper follow-up anchor (丁文伯有哪些论文 → 他的研究方向, 11.42s / 12 citations), and full golden-set regression (81/120, 27 turns).

- [x] 1.12 P0 entity grounding: only deterministic views carry bound subjects; rewrite/term/authority views are recall-only; professor-topic queries cannot bind a company; 2-char bound names are not subjects; web subject gate fails open on topic queries.

- [x] 1.13 Add a topic-professor guard in `_standalone_anchor`: `有哪些…教授` without a company/enterprise word must not resolve a company anchor.

- [x] 1.14 Local data bridge: expand manual professor fields (email/homepage/counts/education/work/awards/company_roles), boost exact-name manual points, and blocklist generic person names (教授/副教授/讲师/老师/教师/博士/研究员/院士) from entity linking.
