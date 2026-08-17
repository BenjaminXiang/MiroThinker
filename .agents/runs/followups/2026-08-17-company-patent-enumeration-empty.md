# Follow-up: canonical company's patent follow-up answers "not found" and deflects to external patent databases

Status: **Open — recorded only, root-cause analysis deferred** (user test-and-record
mode 2026-08-17).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: user-testing round-1 findings P5
(`.agents/runs/2026-08-17-user-testing-round-1/findings.md` + `transcripts.md`);
register §3 (telemetry — again blocks attribution); legacy-line analogs
(`wire-professor-paper-list-traversal`, FM4) for the same DEFECT CLASS in the old
serving line.

## Problem (user-reported, verbatim in transcripts.md group 4)

- T1 `优必选科技怎么样` → correct company profile (canonical path works).
- T2 `该公司的专利有哪些` → "公开信息中未找到深圳市优必选科技股份有限公司具体的
  专利列表" + company re-description + **explicit advice to search 国家知识产权局
  官网 / Incopat / PatSnap externally**.

Why this matters beyond wording: patents are one of the platform's four core
domains and UBTECH is a canonical entity; the turn is a typed referent
（该公司 → company）that should bind the canonical anchor and enumerate its
patents from the local store. Instead the product deflected a core-domain
question to external services.

## Analysis deferred — open questions parked for the chain audit

**RESOLVED 2026-08-17 (coverage audit, `.agents/runs/2026-08-17-serving-pack-coverage-audit.md`)**:
question 3 answered — the serving pack contains only the OLD 1,931-patent set
with 727 company↔patent links total, and UBTECH has **zero** patent links in the
relationship graph. The turn had no local patent data to enumerate: data absence,
not a retrieval/wiring failure. The never-refuse/deflection wording remains a
separate open defect. Remaining parked questions (binding/path-firing telemetry)
are moot for this instance but stay parked for the general audit.

Per the user's instruction (record now, analyze later), the following were parked,
NOT investigated yet:

1. Did the typed referent bind the canonical UBTECH anchor at planning time?
2. Did the `company_has_patent` relationship path fire, fire-and-return-empty,
   or never fire?
3. ~~If it fired empty: does the V2 serving pack contain patents for UBTECH~~ —
   ANSWERED: no (0 links; 727 total).
4. Never-refuse invariant: the "未找到 + 外甩" wording family (P2/P4/P5) —
   is the deflection template behavior or model phrasing?

None of these are answerable from today's logs (§3 telemetry gap).

## Expected behavior (recorded for the future fix contract)

A typed-referent patent enumeration over a canonical company returns the local
patent list (or an honest bounded summary with counts), never a deflection to
external databases.
