#!/usr/bin/env bash
# Full E2E validation for all 9 Shenzhen universities
# Includes web search + identity verification (no --skip-web-search)
set -euo pipefail

LIMIT="${1:-5}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/load_professor_e2e_env.sh"
cd "$SCRIPT_DIR/.."

SCHOOLS=(sustech tsinghua_sigs pkusz szu suat hitsz sysu sztu cuhksz)
SCHOOL_NAMES=("南方科技大学" "清华SIGS" "北大深研院" "深圳大学" "深圳理工大学" "哈工大深圳" "中山大学深圳" "深圳技术大学" "港中深")

echo "================================================================"
echo " Professor Pipeline V3 — Full E2E (with web search)"
echo " Limit: $LIMIT per school | $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
echo ""

for i in "${!SCHOOLS[@]}"; do
  school="${SCHOOLS[$i]}"
  name="${SCHOOL_NAMES[$i]}"
  outdir="logs/data_agents/professor_v3_full_e2e_${school}"

  echo "--- [$((i+1))/9] $name ($school) ---"

  .venv/bin/python scripts/run_professor_pipeline_v3_e2e.py \
    --seed-doc "scripts/e2e_seeds/${school}.md" \
    --output-dir "$outdir" \
    --limit "$LIMIT" \
    --skip-vectorize 2>&1 | tail -1

  echo ""
done

echo ""
echo "================================================================"
echo " Summary"
echo "================================================================"

.venv/bin/python -c "
import json, os, sys

schools = ['sustech','tsinghua_sigs','pkusz','szu','suat','hitsz','sysu','sztu','cuhksz']
names = ['南方科技大学','清华SIGS','北大深研院','深圳大学','深圳理工大学','哈工大深圳','中山大学深圳','深圳技术大学','港中深']

print(f\"{'#':>2} | {'高校':^12} | {'发现':>4} | {'释放':>4} | {'阻断':>4} | {'Ready':>5} | {'WebSearch':>9} | {'IDVerified':>10}\")
print('-' * 85)

t_disc = t_rel = t_blk = t_rdy = t_ws = t_iv = 0
for i, (school, name) in enumerate(zip(schools, names)):
    path = f'logs/data_agents/professor_v3_full_e2e_{school}/e2e_report.json'
    try:
        with open(path) as f:
            rpt = json.load(f)['report']
        disc = rpt['stage1_discovery']['discovered_count']
        rel = rpt['stage8_release']['released']
        blk = rpt['stage8_release']['l1_blocked']
        rdy = rpt['stage8_release']['quality_distribution']['ready']
        ws = rpt['stage5_web_search']['search_count']
        iv = rpt['stage5_web_search']['identity_verified']
        t_disc+=disc; t_rel+=rel; t_blk+=blk; t_rdy+=rdy; t_ws+=ws; t_iv+=iv
        status = 'PASS' if blk == 0 else ('PARTIAL' if rel > 0 else 'BLOCKED')
        print(f'{i+1:>2} | {name:^12} | {disc:>4} | {rel:>4} | {blk:>4} | {rdy:>5} | {ws:>9} | {iv:>10}  {status}')
    except Exception as e:
        print(f'{i+1:>2} | {name:^12} | ERROR: {e}')

print('-' * 85)
print(f'   | {\"合计\":^12} | {t_disc:>4} | {t_rel:>4} | {t_blk:>4} | {t_rdy:>5} | {t_ws:>9} | {t_iv:>10}')
print()
print(f'L1 通过率: {t_rel}/{t_rel+t_blk} = {t_rel/(t_rel+t_blk)*100:.0f}%' if t_rel+t_blk>0 else '')
print(f'Web Search 覆盖: {t_ws}/{t_rel+t_blk} professors searched')
print(f'Identity Verified: {t_iv} pages confirmed same person')
"
