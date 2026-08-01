# S12E isolated candidate rebuild — verification report

- Date: 2026-08-01/02 (UTC+8); executor: Task 7d-2 (isolated rebuild + serving pack + verification).
- Branch: `codex/canonical-v2-s12a-ready` (worktree `.worktrees/canonical-v2-s11-consolidation`), never pushed.
- run-id: `s12e-build-20260801-v1`; candidate-release-id: `candidate-s12e-20260801-v1`.
- database: `miroflow_candidate_s12e_20260801_v1` in container `canonical-v2-s12c-pg-20260726-r8` (127.0.0.1:55458).
- staging: `/var/tmp/mirothinker-canonical-v2-s12e/staging`; index: `/var/tmp/mirothinker-canonical-v2-s12e/index`; pack: `/var/tmp/mirothinker-canonical-v2-s12e/serving-pack`.
- **No cutover**: live release on 18188 untouched (still r8, PID 3419271); r8 DB/index/Milvus/pgtest untouched.

## 1. Build

- Command: `s12a/complete_candidate_runner.py` fresh-build branch (no `--serve`), launched via `nohup` at ≈2026-08-02 00:03 +0800; log `/tmp/s12e_build.log`.
- Duration: launch → envelope written 49m32s (staging marker 00:04:16 → envelope 00:53:48); runner exit 0 at ≈00:57 +0800 → **total ≈ 54 minutes**.
- Receipts (runner stdout):
  - `candidate_release_id=candidate-s12e-20260801-v1`
  - `receipt_sha256=aea9defe583ed70a4f8436ca592a9f8432dc0a7cf01ad8249b3da2e505decadf`
  - `handoff_sha256=8c248bd19c477794e30d0960cbfd4e15aa90b190d62b185811cb93ca762ee062`
  - `envelope_sha256=28909e459c14544b11dea58e6b2dd37216f89f2e85e0cbf96da29e51b266d0e2`
- Envelope: `s12e/complete-candidate-build-envelope.json` (716,703,650 bytes; envelopes are `.gitignore`d — kept on disk like r8's).
- Landing after build: `landing.source_record`=5586, `landing.ingest_run`=6 — byte-identical batch set to r8.
- Index: marker `1fafb12bf8870244b34862801ccef6e6ea58434a95592c29355eee11c3ce04b1`, `lookup.sqlite3` 54,849,536 B, `milvus.db` 131,604,480 B.
- Index target prepared with `prepare_isolated_index_target` (same helper r8 used).

### 1.1 Invocation deviations (all documented, none silent)

1. **Source manifest regenerated (required by this round's edits).** The whitelist widenings (750dfbe/3f60ca8/6abfbad) changed `_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE`, so the derived `_RELEASED_OBJECTS_MAPPER_POLICY_SHA256` moved `5c281568…` → `4c6265ce…`; the r7 manifest failed exact validation ("released_objects mapper policy/count authority differs"). Fix: `s12e/generate_s12e_source_manifest.py` re-binds only the mapper hash; output `s12e/source-build-manifest-s12e.json`, `content_sha256=fd1d12ff57864b10a28c902cc1867d50b9b8d8481d66848bd2668660f72cf9ab`. Diff vs r7 verified: only `released_objects_mapper_policy_sha256` + `content_sha256` differ.
2. **DB provisioning (environment, not code).** New DB needed the destructive-target marker (`COMMENT ON DATABASE … 'miroflow:destructive-target:v1:disposable:miroflow_candidate_s12e_20260801_v1'`, matching r8's marker kind) and the canonical-v2 migration chain (`alembic -c canonical_v2_alembic.ini upgrade head` → `C2_0011`).
3. **Fixed envelope path.** The runner pins `--envelope-output` by release prefix; `candidate-s12e-*` falls to `s12a/complete-candidate-build-envelope.json`. The committed s12a envelope was moved aside before the build and **restored byte-exact afterward** (sha256 `ab21c0a6…` re-verified; 0600 perms preserved; git clean).
4. **Scratch port.** The runner pins serving to `0.0.0.0:18188` (owned by the live r8 server). Smoke used `s12e/serve_s12e_candidate.py`, which remaps only the socket to **18199**; every other runner safety check unchanged.
5. All other args byte-identical to the r8 invocation (gate root, r7-derived batch set, parser/policy/model versions, decision bundle `s12a/recorded-decision-bundle-v1.json`, embedding bundle `s12c/qwen-embedding-bundle-v1.json`, accepted-original-milvus triple).

## 2. Professor backfill `s12e-professor-backfill-v1` — did NOT merge (stop point documented)

The brief asked to add the batch as a 7th `--source-batch-id`. Result, reproduced twice:

- With the r7 manifest and with the regenerated s12e manifest, the runner fails fast in `_preflight` (`knowledge_build_isolated.py:6877`): `SourceBuildManifestError: request source batches differ from the source-build manifest`. Non-destructive (verified: DB schema/data untouched, no staging, no envelope).
- Root cause: `SourceBuildManifest.validate_source_authority` pins the inventory to exactly the 50 accepted sources and `_SUPPLEMENTAL_SOURCE_AUTHORITIES` to the 5 s12c-r7 batches; there is no manifest authority for a 7th batch, and no merge purpose for the backfill payload shape (`professor_id` + `fields.<field>.{value,source_url,…}`) anywhere in the build. The 16 records exist only in the r8 DB landing (never read by a fresh build) and in `s12e/professor_backfill_batch.jsonl` / `/var/tmp/mirothinker-canonical-v2-s12e/preseed-backup/staging/professor_backfill_s12e_v1.jsonl`.
- Per the task rules this is a data-side-prep gap from this round's work, so it is **reported, not patched**. Consequence: 王学谦's projection keeps the placeholder department (§3, §4a). The build below therefore ran with the exact r8 6-batch set.

## 3. Build-output verification (DB `miroflow_candidate_s12e_20260801_v1`)

| Check | Expectation | Actual | Verdict |
| --- | --- | --- | --- |
| `professor.current_projection` | ≈1430 (554+882−pollution) | **1428** | ✓ within tolerance; exact funnel: 1439 landing → 1433 selected (6 pollution hard rejects) → 1428 canonical identities (5 identity merges) → 1428 projected (100% inclusion accept) |
| `knowledge.canonical_identity` (professor) | — | 1428 | ✓ all projected |
| 王学谦 present | yes | yes (`professor-c-6c27ec7bab291ecfc6a3d9f2`, 清华大学深圳国际研究生院, 教授、博士生导师, 7 research_directions) | ✓ |
| 王学谦 department=数据与信息研究院 | backfill merged | **placeholder** `Not supplied by the historical source.` | ✗ backfill not merged (§2) |
| `company.current_projection` | — | 1037 | ✓ (= landing) |
| company industry non-empty | ≈100% | **1037/1037 = 100.0%** | ✓ |
| company website non-empty | ≈60% | **625/1037 = 60.3%** | ✓ |
| company key_personnel non-empty | ≈82% | **851/1037 = 82.1%** | ✓ |
| `paper.current_projection` | — | 563 (r8: 262; +301 from widened professor anchors; 574 landing − 11 identity merges) | ✓ |
| pFedGPA doi/arxiv | present | doi `10.1609/aaai.v39i17.33980`, arxiv_id `2409.05701` | ✓ |
| paper doi rate | — | 494/563 = 87.7% | ✓ |
| `patent.current_projection` | — | 1931 (= landing) | ✓ |
| patent filing_date | present | **1931/1931 = 100%** | ✓ |
| `patent_has_applicant` relationships | ≈121 (76+45) | **121** | ✓ exact |
| `knowledge.current_relationship_projection` total | — | 692 | ✓ |
| 6 pollution names (师资列表/师资介绍/教育经历/相关教师/教师名录/科研成果) | absent | **0** | ✓ |
| reversed anti-scrape emails | decoded to real addresses | **0** reversed-pattern strings (r8 had 8); 39 `@hit.edu.cn` all real (`gangyu@`, `buyu.liu@`, `honghai.liu@`, …) | ✓ |
| placeholder fields (backfill would have filled 16 people) | — | department placeholder 156, email placeholder 677 (omitted from display by 45af375) | noted |

## 4. Serving pack

- Built with `s12c/build_serving_pack.py` (`--generator-run-id s12e-pack-20260801-v1`) from the s12e envelope + index.
- Path: `/var/tmp/mirothinker-canonical-v2-s12e/serving-pack` — `manifest.json` (1,198,547 B), `relationships.json` (289,902,106 B), `institution_catalog.json` (387 B), `lookup.sqlite3`, `milvus.db`, index marker.
- Phases: index_snapshot_verify 6.91s, copies 0.35s, authority docs 10.44s, manifest 0.45s, **dogfood_open 27.35s — reloaded authority matched the envelope exactly**.
- Serving bundle: `s12e/serving-bundle-s12e.json`, `content_sha256=5a63b566601f329ff1180c7c0e3a0285e23286d2f78d72e03eefa5b9606f0731` (derived from r8 bundle; only release-bound identities changed; self-hash recomputed via `RecordedServingBundle.model_validate`).

## 5. Candidate smoke (pack mode, `CANONICAL_V2_FAST_BOOT=1`, port 18199; server killed afterwards)

(a) **王学谦是谁** → 200, `canonical_v2:A:answer`, llm_synthesized. Answer disambiguates two 王学谦 and gives the SIGS professor: "清华大学深圳国际研究生院教授、博士生导师，担任数据与信息研究院副院长及深圳市空间机器人与遥科学重点实验室主任…空间机器人领域…2025年广东省'最美科技工作者'". The 数据与信息研究院 affiliation appears **via the web lane**, not the local projection (placeholder department — §2); the 7 local research directions were not enumerated in the prose. Partial pass with the backfill caveat.

(b) **介绍清华的丁文伯** → 200. "清华大学深圳国际研究生院数据与信息学院的副教授、博士生导师…科研处处长…国家青年特聘专家" + full education/career + all research directions (摩擦电自供电传感器设计、基于摩擦电效应的触觉感知、柔性可穿戴智能手套、多模态人机交互界面、通信高效的联邦学习算法、基于自适应量化的分布式学习) + awards. Quality unchanged vs r8. ✓

(c) **pFedGPA 论文** → 200. "…最初于 2024 年 9 月 9 日提交至 arXiv（编号 **2409.05701**），并于 2025 年正式发表于 AAAI 会议" + method summary. arXiv id present. ✓

(d) **普渡科技有哪些专利** → 200. Non-empty list of specific local patent titles: 机器人的路口检测方法、停靠位置确定方法、机器人控制方法、一种手指、腱/腱鞘传动组件、一种驱动总成、手腕结构机械臂、充电组件及充电桩、一种自移动设备、停靠基站及清洁系统、水泵装置、多自由度云台移动机器人等. New applicant links serve correctly. ✓

(e) **中国有哪些成熟的酒店送餐机器人供应商** → **409 `canonical_v2_consumer_integrity_error` ("supplemental budget receipt exceeds the server-owned plan"), deterministic** (3/3 attempts, each ≈23.5s). Analysis: the only budget axis that can trip here is `elapsed_ms > 10000` (theme probes capped 12×0.5=6.0=max cost; provider_calls=1≤2; retries/attempts 0/1). The wide theme-enumeration probe round (discovery + 12 web probes + LLM judge + tiered page fetch, all keyless/slow) exceeds the 10s supplemental wall budget. This is serving-stack latency from the Jul-31 gap-check/web commits (5e1d601/8913b79/85117e6/eb44a2b/fff5194/ac93f14), **not an s12e data regression**: the company corpus is byte-identical to r8's (1037), and sibling phrasings succeed on the same candidate:
- "深圳有哪些送餐机器人公司" → 200 in 6.5s: 普渡科技、云智星 (both with founded/HQ/product detail).
- "中国有哪些酒店机器人公司" → 200 in 4.2s: 云迹科技、擎朗智能、普渡科技、博歌 temi (sane supplier list).
The live 18188 server predates those commits (started 2026-07-31 15:21 UTC; commits landed 18:54–22:37 UTC), so it cannot exhibit this failure; r8-with-current-code would hit the same wall on this phrasing. Follow-up (outside this slice): raise `max_wall_time_ms` for the supplemental budget or cut probe latency (page-fetch/judge) for wide enumerations.

## 6. Artifacts created this round

- `s12e/source-build-manifest-s12e.json` (regenerated manifest; sha `fd1d12ff…`)
- `s12e/generate_s12e_source_manifest.py`
- `s12e/serving-bundle-s12e.json` (sha `5a63b566…`)
- `s12e/generate_s12e_serving_bundle.py`
- `s12e/serve_s12e_candidate.py` (scratch-port pack-mode wrapper)
- `s12e/complete-candidate-build-envelope.json` (716 MB; `.gitignore`d, on disk)
- DB `miroflow_candidate_s12e_20260801_v1`; staging/index/pack under `/var/tmp/mirothinker-canonical-v2-s12e/`
- `/tmp/s12e_build.log`, `/tmp/s12e_serve.log`

## 7. Explicit non-actions

- Live release NOT cut over; 18188 NOT restarted (PID 3419271 still serving r8).
- r8 candidate DB / r8 index / original Milvus / paused pgtest (15432): untouched.
- No code changes to product modules; the only new code is the three s12e run-artifact scripts above.
