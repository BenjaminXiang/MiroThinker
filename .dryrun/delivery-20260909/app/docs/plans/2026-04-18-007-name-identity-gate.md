# Round 7.17 — Name-Identity Gate (canonical_name ↔ canonical_name_en)

**Date:** 2026-04-18
**Status:** Planning → TDD
**Parent plan:** `docs/plans/2026-04-18-005-data-quality-guards-and-identity-gate.md`
**Trigger:** Pipeline verification console surfaced `canonical_name` / `canonical_name_en` mismatches in production.

## 1. Problem

Random sample of 30 from `miroflow_real.professor` (557 rows with non-empty `canonical_name_en`):

| # | canonical_name | canonical_name_en | class |
|---|---|---|---|
| PROF-A4C090364793 | 张成萍 | Thomas Hardy | unrelated person |
| PROF-5BD72AE665CD | 舒阳 | Chunbo Li | unrelated person |
| PROF-9353449AAC7C | 李莉华 | Chunbo Li | unrelated person (dup of above) |
| PROF-C7EA7E1FA98D | 陈海龙 | Qing Yang | unrelated person |
| PROF-2135D8D85E54 | 曹磊峰 | Xiaoyang Guo | unrelated person |
| PROF-1A294DBDA3BA | 张春香 | Laser Technol | junk fragment |
| PROF-63106E709451 | 苏阳 | Area Graphene | junk fragment |
| PROF-80E26C072BEA | 廖庆敏 | Senior Member | junk fragment |

7 of 30 are wrong. Extrapolated: ~130 polluted rows of 557.

Root cause: `homepage_crawler._select_best_english_name_candidate` picks the most-prominent-looking English token sequence from the profile page without verifying it's the same person as `canonical_name`. Bio text routinely contains:
- Co-author names (Chunbo Li gets picked twice for different profs)
- Journal/publisher captions (Laser Technol, Area Graphene)
- IEEE role labels (Senior Member)
- Historical quotes / cited authors (Thomas Hardy)

## 2. Scope

In:
- LLM gate that, given `(canonical_name_zh, candidate_name_en)`, returns accept/reject with confidence.
- Wire into `canonical_writer._upsert_professor_row` so every write of `canonical_name_en` passes the gate.
- Post-hoc scan script that re-evaluates all existing `professor.canonical_name_en` rows, files `pipeline_issue` for rejects (stage=`name_extraction`, severity=`medium`), and optionally clears the field when confidence is very low.

Out:
- Fixing `homepage_crawler` selection logic. Gate catches the output; selection stays as-is.
- Translating names in the other direction (generating `name_en` when empty). Not in scope.
- Auto-clearing mid-confidence rejects. Flag, let a human decide.

## 3. Design

### 3.1 Module layout — `src/data_agents/professor/name_identity_gate.py`

**Sync, not async.** `canonical_writer._upsert_professor_row` is sync (uses `conn.execute`), and per-professor gate calls are one batch at most. Making the gate sync avoids an async bridge inside a sync DB transaction. `paper_identity_gate` is async because it runs in the async paper_collector loop; this one stays sync.

```python
@dataclass(frozen=True, slots=True)
class NameIdentityCandidate:
    canonical_name: str          # e.g. "张成萍"
    candidate_name_en: str       # e.g. "Thomas Hardy"
    source_url: str | None = None   # provenance only, NOT passed to LLM as semantic context

@dataclass(frozen=True, slots=True)
class NameIdentityDecision:
    accepted: bool
    confidence: float            # 0-1
    reasoning: str
    error: str | None = None

CONFIDENCE_THRESHOLD = 0.8       # same bar as paper_identity_gate

def verify_name_identity(
    candidate: NameIdentityCandidate,
    *,
    llm_client,
    llm_model: str,
) -> NameIdentityDecision: ...        # sync

def batch_verify_name_identity(
    candidates: list[NameIdentityCandidate],
    *,
    llm_client,
    llm_model: str,
    batch_size: int = 20,
) -> list[NameIdentityDecision]: ...   # sync
```

`source_url` is stored as provenance in logs / `pipeline_issue.evidence_snapshot`; it is NOT included in the LLM prompt. The LLM sees only `canonical_name` and `candidate_name_en`. Removing institutional context eliminates the "plausible CS professor → rubber-stamp" failure mode.

### 3.1.1 Prompt (concrete, not punted)

Modeled on `paper_identity_gate.py`. Chinese-first, JSON output, precision-first.

```
你是一位中英姓名核对专家。我会给你一位中国教授的中文姓名和一个候选英文姓名，
判断该英文姓名是否是这位教授本人的英文形式（本人选用的英文名、标准汉语拼音、
粤语拼音 Jyutping、威妥玛拼音 Wade-Giles，都视为合法；姓名顺序可以是东方式或
西方式）。

接受标准（examples, two-shot）：
- (熊会元, Huiyuan Xiong) → is_same_person=true, confidence=0.95
  reason: 标准汉语拼音，"Xiong Huiyuan" 的西方姓后写法
- (夏树涛, Shu-Tao Xia) → is_same_person=true, confidence=0.92
  reason: 连字符拼音
- (谢霆锋, Nicholas Tse) → is_same_person=true, confidence=0.90
  reason: Tse = 谢的粤语拼音；Nicholas 为本人英文名

拒绝标准（examples, three-shot）：
- (张成萍, Thomas Hardy) → is_same_person=false, confidence=0.05
  reason: Thomas Hardy 与 张成萍 无音近、无语义关联，像是页面上另一个人的名字
- (廖庆敏, Senior Member) → is_same_person=false, confidence=0.02
  reason: "Senior Member" 不是人名，是 IEEE 会员级别
- (张春香, Laser Technol) → is_same_person=false, confidence=0.02
  reason: "Laser Technol" 是期刊名缩写，不是人名

输出 JSON（不要 markdown fence）：
{
  "is_same_person": boolean,
  "confidence": float 0-1,
  "reasoning": "<= 60 字的简短理由"
}

现在判断：
- 中文姓名: {canonical_name}
- 候选英文姓名: {candidate_name_en}
```

### 3.1.2 Gate decision rules

- `confidence < 0.8` → `accepted=False` regardless of `is_same_person`.
- JSON parse error → `accepted=False, error="parse"`.
- LLM client exception → `accepted=False, error="llm_exception"`.
- Empty `candidate_name_en` → never called (guarded at caller).
- Never expand pollution on failure.

### 3.2 Gate at write time — `canonical_writer._upsert_professor_row`

New signature (sync callable, optional, legacy path = no gate):
```python
def _upsert_professor_row(
    conn,
    *,
    professor_id,
    enriched,
    primary_page_id,
    name_identity_gate=None,     # optional sync callable(NameIdentityCandidate) -> NameIdentityDecision
) -> bool:
    canonical_name = _clean_text(getattr(enriched, "name", None))
    candidate_name_en = _clean_text(getattr(enriched, "name_en", None))
    if candidate_name_en and canonical_name and name_identity_gate is not None:
        decision = name_identity_gate(NameIdentityCandidate(
            canonical_name=canonical_name,
            candidate_name_en=candidate_name_en,
            source_url=getattr(enriched, "homepage", None),   # provenance only
        ))
        if not decision.accepted:
            logger.info("name_identity_gate rejected %s / %s (conf=%.2f)",
                        canonical_name, candidate_name_en, decision.confidence)
            candidate_name_en = None
    # INSERT uses the (possibly-nulled) candidate_name_en, so rejection
    # propagates to the DB column, not just the local variable.
    conn.execute("INSERT ... canonical_name_en = %s ...", (..., candidate_name_en, ...))
```

Gate is sync-only. `name_identity_gate=None` (default) preserves legacy behavior exactly.

### 3.3 Post-hoc scan — `scripts/run_name_identity_scan.py`

Reads all `professor` rows with non-empty `canonical_name_en`, batches through `batch_verify_name_identity`, writes a `pipeline_issue` row for each rejection.

**Stable description template** (no confidence/timestamp in description text — that breaks the partial unique index on `description_hash = md5(description)`). Variable data goes into `evidence_snapshot` jsonb only:

```python
DESCRIPTION_TEMPLATE = "canonical_name_en rejected for {canonical_name}: {candidate_name_en}"
# ↑ deterministic: same prof × same candidate → same hash → dedup
```

```python
description = DESCRIPTION_TEMPLATE.format(
    canonical_name=row["canonical_name"],
    candidate_name_en=row["canonical_name_en"],
)
snapshot = {
    "type": "name_extraction_report",
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "professor": {
        "professor_id": row["professor_id"],
        "canonical_name": row["canonical_name"],
        "canonical_name_en": row["canonical_name_en"],
        "institution": row["institution"],
    },
    "gate_decision": {
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "error": decision.error,
    },
}
INSERT INTO pipeline_issue (
    professor_id, stage, severity, description, evidence_snapshot, reported_by
) VALUES (%s, 'name_extraction', 'medium', %s, %s::jsonb, 'round_7_17_scan')
ON CONFLICT DO NOTHING   -- partial unique index dedupes open issues
```

Optional `--auto-clear-threshold 0.95` flag: if gate is ≥ 95% confident the name is wrong (e.g. totally unrelated), NULL out `canonical_name_en`. Default off.

## 4. TDD spec

### 4.1 Unit tests — `tests/data_agents/professor/test_name_identity_gate.py`

Mocked-LLM cases (12 total):

**Accept:**
1. Exact pinyin: (熊会元, Huiyuan Xiong) → accepted, conf ≥ 0.9
2. Hyphenated pinyin: (夏树涛, Shu-Tao Xia) → accepted
3. Reversed order: (李强, Li Qiang) and (李强, Qiang Li) → both accepted
4. Self-declared English: (张辰, Steve Zhang) → accepted when LLM confidence ≥ 0.8

**Reject — unrelated person:**
5. (张成萍, Thomas Hardy) → rejected
6. (舒阳, Chunbo Li) → rejected
7. (曹磊峰, Xiaoyang Guo) → rejected

**Reject — non-person:**
8. (张春香, Laser Technol) → rejected
9. (廖庆敏, Senior Member) → rejected
10. (苏阳, Area Graphene) → rejected

**Fail-safe:**
11. LLM raises → `accepted=False, error="llm_exception"`
12. LLM returns unparseable JSON → `accepted=False, error="parse"`

Mock LLM returns canned JSON per test. No real network.

### 4.2 Wiring tests — `tests/data_agents/professor/test_canonical_writer_name_gate.py`

Integration against a pg fixture, not mocks. Catches wiring bugs that unit tests miss.

- `test_legacy_no_gate_leaves_name_en_unchanged` — `name_identity_gate=None`, input profile has `name_en="Thomas Hardy"`, asserts DB row has `canonical_name_en='Thomas Hardy'` (preserves backward compat).
- `test_rejected_decision_nulls_db_column` — fake gate returns `accepted=False`; asserts DB row has `canonical_name_en IS NULL` (not just a local variable; actually written).
- `test_accepted_decision_persists_name_en` — fake gate returns `accepted=True`; asserts DB row has `canonical_name_en='Huiyuan Xiong'`.
- `test_gate_called_with_cleaned_name` — fake gate captures its argument; asserts `canonical_name` is the `_clean_text(enriched.name)` result, not raw.
- `test_sync_callable_contract` — asserts the gate parameter is called synchronously (no `await`); an async gate would fail this path deliberately.

Total: 5 wiring tests + 12 unit tests = 17.

## 5. Wire point — `pipeline_v3.py`

Independent feature flag. The name gate is separate-risk from the paper gate: a bad paper-gate prompt pollutes paper links (recoverable per-link); a bad name-gate prompt silently nulls `canonical_name_en` across the whole professor table (harder to recover). Split the kill switches.

```python
# New param, defaults to True in production, can be flipped independently
name_identity_gate_enabled: bool = True

name_identity_gate = functools.partial(
    verify_name_identity,
    llm_client=identity_gate_llm_client,   # reuses Round 7.6 Gemma client
    llm_model=identity_gate_llm_model,     # reuses Round 7.6 model
) if name_identity_gate_enabled else None
```

The LLM client is shared with paper gate (same Gemma endpoint), but the feature flag is its own switch. Operators can disable the name gate without losing paper-gate protection, and vice versa.

## 6. Verification plan

1. `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_name_identity_gate.py -q` — 12/12 green.
2. `uv run pytest apps/miroflow-agent/tests/data_agents/professor/ -q` — no regressions.
3. Post-hoc scan dry run: `python scripts/run_name_identity_scan.py --dry-run --institution 深圳技术大学` — reports count without writes.
4. Full scan: `python scripts/run_name_identity_scan.py` — populates pipeline_issue; verify via `/browse` review tab.
5. Expected: ~20-30% of 557 rows flagged.

## 7. Known limits & rejected alternatives

**Pinyin-only heuristic, rejected.** `pypinyin` could generate expected romanizations from `canonical_name` and check set membership. This catches malformed pinyin but the dominant failure mode is well-formed English names that belong to a different person (Thomas Hardy, Chunbo Li) or non-person fragments (Senior Member). Set membership gives no signal on those — rule returns "not in pinyin set" for every polluted row, same verdict as for legitimate self-declared English names. LLM is the right tool for "is this the same person," not "is this valid pinyin."

- Gate relies on Gemma knowing romanization conventions. For Wade-Giles, Cantonese Jyutping, Hong Kong / Taiwan conventions, the prompt shows few-shot examples. If miscalibrated, tune the prompt, not the threshold.
- Gate is gated by its own `name_identity_gate_enabled` flag, independent of the paper gate. Blast radius: disabling the name gate doesn't weaken paper attribution, and vice versa.
- Post-hoc `--auto-clear-threshold` is off by default. Human review via `/browse` is authoritative; scan only files `pipeline_issue` rows.

## 8. Estimated delta

| Artifact | Size |
|---|---|
| `name_identity_gate.py` | ~120 LOC |
| `test_name_identity_gate.py` | ~180 LOC |
| `canonical_writer.py` changes | ~20 LOC |
| `pipeline_v3.py` wiring | ~10 LOC |
| `run_name_identity_scan.py` | ~100 LOC |

Total ~430 LOC including tests. Small, focused, no schema churn.
