# Attribution evidence: serving vector-lane latency (2026-09-15)

Change: `serving-index-process-scope`. Method: **py-spy sampling of the live
serving process** (read-only; no restart, no code change) while a fresh session
ran a vector-using query, plus isolated sub-step measurements on an index copy.

## Method (reproducible)

```bash
# real python PID = child of the unit's MainPID (the MainPID itself is `uv`)
PY=$(pgrep -P $(systemctl --user show canonical-v2-backend -p MainPID --value) | tail -1)
# fresh-session query in the background, 14s of 200Hz sampling on the real PID
python3 /tmp/post-switch-probe.py http://127.0.0.1:18188 "深圳有哪些做机器人的公司" &
sudo -n env "PATH=$PATH" ~/.local/bin/py-spy record --pid "$PY" --duration 14 \
  --rate 200 --format raw --output /tmp/attr-prof.txt
# correlate with the turn-debug lane timings for that query
```

Window measured: `turn-debug-NfyUVbZb23eQ-01.json`, `vector = 12.5s`,
`lexical 4.5s`, `web 10.6s`, `exact 1.8s`. Samples: **3311**.

## Result — where the time goes (share of samples)

| Share | Frame | Meaning |
|---|---|---|
| **28.7%** | `_canonical_sha256` (`knowledge_read.py:147/153`) | canonical JSON hashing |
| — of which **90.8%** | `bind_trace` (`:1345` 31.2%, `:1352` 27.3%, `:1358` 32.3%) | **the trace binding**: per trace object it does `model_dump(exclude=…)` → `_canonical_sha256` (candidate id) → `model_dump` → `_canonical_sha256((lineage, candidate_id))` (evidence id) → `model_dump` → `_canonical_sha256(content)` (content hash) |
| — only **5.5%** of it | `bind_content` (`:164`) | the content-model self-hash |
| **10.0%** | `_normalize` (`knowledge_read_isolated.py:8503`) via `visit` (`:8523`) | recursive NFKC + casefold + split over every scalar value |
| **10.3% / 7.1%** | numpy `read_array` / `_read_bytes` | reading `vector_matrix.npz` (1.68GB) |
| ~7% | pydantic `model_dump` / `__init__` | model (de)serialisation |
| ~15% | `asyncio` runner / provider + SSL | waiting on network lanes |
| 1.9% | `_ContentModel` construction overall | content-addressed model cost is *minor* |

## Isolated sub-step measurements (index copy, no live interference)

| Step | Time |
|---|---|
| `open_manifest_verified_index_snapshot` on a warm copy | **59.9 / 65.3 / 60.5s** (3 runs) |
| — artifact hashing (`lookup.sqlite3` 638MB + `milvus.db` 1029MB) | **10.24s** |
| — Milvus checks | **≈50s of 60s timeouts** (`failed to get mvccTs from milvus server` once per 60s) |
| `vector_matrix.npz` load (51,026 × 4096 float64) | **1.41s** |
| remote query embedding (`100.64.0.27:18005`) | **0.03s** (×3) |

## Reading

- The per-turn serving cost is dominated by **re-deriving content hashes and
  normalised values that are deterministic functions of immutable data**
  (`bind_trace` ≈26% of samples; `_normalize` over scalars ≈10%), plus a
  **per-session re-load** of the 1.68GB matrix (≈10%) and general model
  (de)serialisation (~7%).
- The 60s snapshot open is a separate, boot/verification-shaped cost; ~50s of it
  is Milvus waiting on timeouts for a store the serving path never queries.
- Caveat: single 14s sampling window; the split is consistent with the
  independent sub-step measurements and with the warm/cold lane timings
  (3.0–3.2s warm / 12.5–30.6s cold), but a repeat window is cheap if a tighter
  confidence interval is wanted.
