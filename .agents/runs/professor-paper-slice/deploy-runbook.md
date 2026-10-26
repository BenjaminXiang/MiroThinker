# Deploy runbook: professor projection overlay

Target: customer site `100.64.0.96:/root/deploy/fullstack-v2` (runtime authority).
The code side is done and committed (`bd2ef5bf`); this is the remaining slice.

## Files to ship

| local | customer |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/professor_projection_overlay.py` | `code/apps/miroflow-agent/src/data_agents/canonical_v2/` |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (overlay wiring, +8 lines) | same path |
| `.agents/runs/professor-paper-slice/professor-projection-allowlist.json` | `var/professor-projection-allowlist.json` (new file, ~700 KB) |

Both code files must be copied **together**: the serving module imports the new
module, so a half copy fails at import.

## Step 1 — flag off (proves zero change)

```bash
scp <two code files> root@100.64.0.96:/root/deploy/fullstack-v2/code/apps/...
scp professor-projection-allowlist.json root@100.64.0.96:/root/deploy/fullstack-v2/var/
ssh root@100.64.0.96 'cd /root/deploy/fullstack-v2 && bash run.sh > serve.log 2>&1 &'   # ~6–10 min
```

Verify (flag still unset):

- `/api/health` → 200, `/main` → 200
- one professor question returns the same answer as before (no `论文数` / `代表作`)
- `grep -c professor-projection serve.log` → 0

## Step 2 — flag on, gate

Add to `run.sh` (or the systemd environment file):

```bash
export CANONICAL_V2_PROFESSOR_PROJECTION="$B/var/professor-projection-allowlist.json"
```

Restart, then:

```bash
cd apps/admin-console
uv run python scripts/eval_full_testset.py --base http://127.0.0.1:18188 \
    --mode full --out /tmp/eval-overlay.json \
    --baseline scripts/eval-baselines/baseline-full.json --fail-on-regression
```

Green = `verdict: pass`, `required_recall` within tolerance of 77/120.

Spot-check five questions (cookie jar per conversation, `/api/chat`):

1. `介绍清华的丁文伯` — unchanged (not on the allowlist unless linked)
2. `王向荣教授的研究方向` — should now include 论文数 + 代表作
3. `曲强教授的研究方向` — same
4. `黎维彬教授的研究方向` — unchanged (review bucket)
5. `有哪些做具身智能和灵巧手的教授` — q27 behaviour unchanged

## Rollback

Unset `CANONICAL_V2_PROFESSOR_PROJECTION` and restart. No file, pack or database
change is involved; the overlay is read-only. If the copy itself misbehaves,
restore both files from `hotfix/customer-20261026` and restart.

## Risks

- Two restarts (10–20 min total) — schedule a window; the site is single-node.
- Allowlist is 533 records after the duplicate-name filter; a wrong count here is
  user-visible, which is why step 1 exists.
- The eval gate runs 27 turns against the live site and consumes LLM quota.
