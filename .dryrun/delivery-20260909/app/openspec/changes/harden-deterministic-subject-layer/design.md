# Design: harden-deterministic-subject-layer

## Grounding (traced 2026-08-18)

- Headline anchors: `_sanitize_soft_turn_anchor` never drops web handles; a
  web handle whose `display_name` is an article title ("河套深圳园区打造深港
  科技创新聚集地 - 香港中联办") becomes `context_receipt.active_anchor` and
  poisons the session (G1/G3 attribution evidence, 1.2).
- Anchor commit path: `canonical_v2_chat.py::_answer_locked` →
  `_sanitize_soft_turn_anchor(turn_result.context_receipt, …)` → committed
  `_CommittedSession.context_receipt/soft_subject_name`.
- Expansion: G5 trace shows anchor=优必选 but answer_subject=微众银行 with
  web lane (0,0) — the expansion views did not bind the session subject.

## 3.4 Headline-shape detector (deterministic)

`is_headline_shaped_name(name)`:

1. source-suffix: ` - X` / `——X` / `_X` / `｜X` before-final-segment pattern
   where the suffix is a short media-like token;
2. event-verb markers: 打造|推进|揭牌|正式成立|加快建设|落地|签署|发布|合作共建
   (regex, entity names essentially never contain these mid-name);
3. sentence-scale length: > 24 CJK chars without 、/（）company markers.

Any hit → headline. Conservative by construction (misses are tolerable —
the soft-subject fallback still answers correctly; false positives on real
entity names are the risk, hence three narrow signals).

Sanitize change: when the receipt anchor is a WEB handle (no canonical id)
AND headline-shaped → drop it; if the session already has an anchor
(committed is not None) keep the previous `context_receipt.active_anchor`
(previous anchor wins); else re-anchor to None and keep
`soft_subject_name` (the carryover machinery from the register §1 fix binds
the soft subject on later turns).

## 3.3 Expansion base

Expansion turns（`has_set_referent`/类似/同类 family）currently free-retrieve.
Fix at planning input: `_planning_displayed_ids`/enumeration context must
carry the active anchor/soft subject into the plan (bound_entity_names), so
serving expansion views（`还有哪些类似的`) search "类似 {subject}" anchored to
the session subject, and the subject-consistency gate filters peers to the
subject's domain. Deterministic assertion: expansion turns bind
displayed_ids/soft subject exactly as deepening turns do.

## 3.1 Echo-guard relaxation

The bare-name clarification loop (P3) fires because a bare institution name
is treated as an ambiguous referent needing disambiguation. Rule: a query
that IS a bare entity name (matches entity-name shape: CJK run + optional
（深圳）qualifier, no operators/referent words) is a subject statement —
clarification only when a referent word (他/该/这家/它…) is present without
a bindable subject.

## 3.2 Type-aware gate

`referent_subject_domain` already exists (followup_referents). Gate:
personal referent + session anchor domain != professor/person → typed
clarification before synthesis. Synthesis-side: answer subject handle domain
must match the referent's expected domain; mismatch → re-anchor to the
referent's bound person or degrade to typed clarification.

## 3.5 P7 note

Adjudicated in Phase 0 (product contract: cookie carryover); verification =
G6 replay PASS stands; no code.
