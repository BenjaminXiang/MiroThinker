#!/usr/bin/env bash
# Full E2E — 3-way parallel, 3 batches
set -uo pipefail

LIMIT="${1:-5}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/load_professor_e2e_env.sh"
cd "${SCRIPT_DIR}/.."

run_school() {
  local school="$1" name="$2"
  local outdir="logs/data_agents/professor_v3_full_e2e_${school}"
  echo "[START] $name ($school)"
  .venv/bin/python scripts/run_professor_pipeline_v3_e2e.py \
    --seed-doc "scripts/e2e_seeds/${school}.md" \
    --output-dir "$outdir" \
    --limit "$LIMIT" \
    --skip-vectorize 2>&1 | tail -1
  echo "[DONE]  $name ($school)"
}

echo "================================================================"
echo " Professor Pipeline V3 — Full E2E (3-way parallel, limit=$LIMIT)"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
echo ""

# Batch 1: sustech, tsinghua_sigs, pkusz
echo "=== Batch 1/3 ==="
run_school sustech "南方科技大学" &
run_school tsinghua_sigs "清华SIGS" &
run_school pkusz "北大深研院" &
wait
echo ""

# Batch 2: szu, suat, hitsz
echo "=== Batch 2/3 ==="
run_school szu "深圳大学" &
run_school suat "深圳理工大学" &
run_school hitsz "哈工大深圳" &
wait
echo ""

# Batch 3: sysu, sztu, cuhksz
echo "=== Batch 3/3 ==="
run_school sysu "中山大学深圳" &
run_school sztu "深圳技术大学" &
run_school cuhksz "港中深" &
wait
echo ""

echo "================================================================"
echo " Summary"
echo "================================================================"

.venv/bin/python -c "
import json

schools = ['sustech','tsinghua_sigs','pkusz','szu','suat','hitsz','sysu','sztu','cuhksz']
names = ['南方科技大学','清华SIGS','北大深研院','深圳大学','深圳理工大学','哈工大深圳','中山大学深圳','深圳技术大学','港中深']

print()
print(f\"{'#':>2} | {'高校':^12} | {'发现':>4} | {'释放':>4} | {'阻断':>4} | {'Ready':>5} | {'WebSrch':>7} | {'IDVerif':>7} | {'状态':^8}\")
print('-' * 90)

t_disc=t_rel=t_blk=t_rdy=t_ws=t_iv=0
for i,(school,name) in enumerate(zip(schools,names)):
    path=f'logs/data_agents/professor_v3_full_e2e_{school}/e2e_report.json'
    try:
        with open(path) as f:
            rpt=json.load(f)['report']
        disc=rpt['stage1_discovery']['discovered_count']
        rel=rpt['stage8_release']['released']
        blk=rpt['stage8_release']['l1_blocked']
        rdy=rpt['stage8_release']['quality_distribution']['ready']
        ws=rpt['stage5_web_search']['search_count']
        iv=rpt['stage5_web_search']['identity_verified']
        t_disc+=disc;t_rel+=rel;t_blk+=blk;t_rdy+=rdy;t_ws+=ws;t_iv+=iv
        st='PASS' if blk==0 else('PARTIAL' if rel>0 else 'BLOCKED')
        print(f'{i+1:>2} | {name:^12} | {disc:>4} | {rel:>4} | {blk:>4} | {rdy:>5} | {ws:>7} | {iv:>7} | {st:^8}')
    except Exception as e:
        print(f'{i+1:>2} | {name:^12} | (error: {e})')

print('-' * 90)
tot=t_rel+t_blk
print(f'   | {\"合计\":^12} | {t_disc:>4} | {t_rel:>4} | {t_blk:>4} | {t_rdy:>5} | {t_ws:>7} | {t_iv:>7} |')
print()
if tot>0: print(f'L1 通过率: {t_rel}/{tot} = {t_rel/tot*100:.0f}%')
print(f'Web Search 覆盖: {t_ws}/{tot} professors')
print(f'Identity Verified: {t_iv} pages confirmed')
print(f'检索系统可用(Ready): {t_rdy} 条教授数据')
"
