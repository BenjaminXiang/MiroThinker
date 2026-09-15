#!/usr/bin/env python3
"""completeness / vocab / uniqueness / placeholder metrics for the company domain."""
import sys, json, collections
sys.path.insert(0, '/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/scripts')
from dqlib import load, classify_str, is_filled, pct, true_str

FIELDS = ['name','normalized_name','aliases','industry','industry_tags','tech_tags','geography',
          'founded_at','legal_representative','website','credit_code','registered_capital',
          'registered_address','patent_count','product_description','profile_summary',
          'technology_route_summary','team_description','key_personnel','products',
          'business_scenarios','capabilities','financing_events','latest_public_updates',
          'personnel_education','personnel_work_experience','_supplementary']

recs = list(load('company'))
N = len(recs)
print(f'# company  n={N}')

# ---------- 1. completeness ----------
print('\n## fill rate + placeholder rate')
print(f'{"field":30s} {"filled":>7s} {"rate":>7s}  {"placeholder":>11s}  {"empty":>7s}')
rows = []
for f in FIELDS:
    filled = 0; ph = collections.Counter(); empty = 0
    for r in recs:
        v = r.get(f, None)
        if is_filled(v): filled += 1
        else: empty += 1
        for s in true_str(v):
            c = classify_str(s)
            if c: ph[c] += 1
    tot_ph = sum(v for k, v in ph.items() if k != 'empty')
    rows.append((f, filled, empty, tot_ph, dict(ph)))
    detail = ' '.join(f'{k}={v}' for k, v in sorted(ph.items()))
    print(f'{f:30s} {filled:>7d} {pct(filled,N):>7s}  {tot_ph:>11d}  {empty:>7d}   {detail}')

# ---------- 2. industry distribution ----------
print('\n## industry value distribution')
ind = collections.Counter()
ind_empty = 0
for r in recs:
    v = r.get('industry')
    if isinstance(v, str) and v.strip():
        ind[v.strip()] += 1
    elif isinstance(v, dict):
        for s in true_str(v):
            if s.strip(): ind[s.strip()] += 1
    else:
        ind_empty += 1
print(f'distinct industry raw = {len(ind)}   missing = {ind_empty}')
for k, c in ind.most_common(30):
    print(f'  {c:>5d}  {k[:80]}')

# ---------- 3. industry_tags / tech_tags vocabulary ----------
for fld in ['industry_tags', 'tech_tags', 'aliases']:
    vals = collections.Counter(); n_ent_with = 0; lengths = []
    for r in recs:
        v = r.get(fld)
        items = []
        if isinstance(v, list): items = [x for x in v if isinstance(x, str)]
        elif isinstance(v, dict) and 'v' in v: items = v['v']
        elif isinstance(v, str): items = [v]
        items = [x.strip() for x in items if x and x.strip()]
        if items: n_ent_with += 1
        lengths.append(len(items))
        for x in items: vals[x] += 1
    tot = sum(lengths)
    print(f'\n## {fld}: entities_with={n_ent_with}/{N} ({pct(n_ent_with,N)}) total_items={tot} '
          f'unique={len(vals)} avg_per_entity={tot/N:.1f} max={max(lengths) if lengths else 0}')
    for k, c in vals.most_common(25):
        print(f'  {c:>5d}  {k[:90]}')

# ---------- 4. suffix / glued / fullwidth anomaly scan ----------
print('\n## tech_tags / industry_tags anomaly scan')
SUFFIX = ['研发商', '制造商', '生产商', '服务商', '供应商', '提供商', '集成商', '方案商', '运营商']
for fld in ['industry_tags', 'tech_tags']:
    items = []
    for r in recs:
        v = r.get(fld)
        if isinstance(v, list): items += [x for x in v if isinstance(x, str)]
        elif isinstance(v, dict) and 'v' in v: items += v['v']
    sfx = collections.Counter()
    for x in items:
        for s in SUFFIX:
            if x.endswith(s): sfx[s] += 1
    fw = sum(1 for x in items if any('\uff01' <= ch <= '\uff5e' or ch in '，。、；：（）' for ch in x))
    glued = sum(1 for x in items if classify_str(x) == 'placeholder-glued')
    print(f'  {fld}: items={len(items)} suffix_hits={dict(sfx)} fullwidth_hits={fw} glued_placeholder={glued}')
    for x in items[:0]: pass
    ex = [x for x in items if any(x.endswith(s) for s in SUFFIX)][:8]
    print(f'    suffix examples: {ex}')
    ex2 = [x for x in items if re_glue(x)][:5] if False else []

def re_glue(x): return False

# normalized merge potential for tech_tags
def norm(s):
    s = s.strip().lower()
    s = s.replace('（','(').replace('）',')').replace('，',',').replace('　','')
    s = ' '.join(s.split())
    return s
for fld in ['industry_tags', 'tech_tags']:
    vals = collections.Counter()
    for r in recs:
        v = r.get(fld)
        items = v if isinstance(v, list) else (v.get('v') if isinstance(v, dict) and 'v' in v else [])
        for x in items:
            if isinstance(x, str) and x.strip(): vals[x.strip()] += 1
    merged = collections.Counter()
    for k, c in vals.items(): merged[norm(k)] += c
    print(f'  {fld}: unique_raw={len(vals)} unique_after_case/fullwidth/space-norm={len(merged)} '
          f'collapsible={len(vals)-len(merged)}')

# ---------- 5. uniqueness / identity ----------
print('\n## identity / name uniqueness')
byname = collections.defaultdict(list)
for r in recs:
    nm = r.get('name')
    nm = nm.strip() if isinstance(nm, str) else ''
    byname[nm].append(r['object_id'])
dups = {k: v for k, v in byname.items() if len(v) > 1}
print(f'distinct name={"<empty>" if "" in byname else "-"} raw_names={len(byname)} duplicate_name_groups={len(dups)} '
      f'entities_in_dup_groups={sum(len(v) for v in dups.values())}')
for k, v in sorted(dups.items(), key=lambda kv: -len(kv[1]))[:15]:
    print(f'  {len(v):>3d}  {k[:70]}')
print('empty name count:', len(byname.get('', [])))

# credit_code uniqueness
cc = collections.Counter()
cce = 0
for r in recs:
    v = r.get('credit_code')
    if isinstance(v, str) and v.strip(): cc[v.strip()] += 1
    else: cce += 1
print(f'credit_code: filled={N-cce} ({pct(N-cce,N)}) distinct={len(cc)} dup_groups={sum(1 for v in cc.values() if v>1)} '
      f'entities_with_dup_credit_code={sum(v for v in cc.values() if v>1)}')
for k, v in sorted(cc.items(), key=lambda kv: -kv[1])[:10]:
    if v > 1: print(f'  {v:>3d}  {k}')

# normalized_name uniqueness
nn = collections.Counter()
for r in recs:
    v = r.get('normalized_name')
    if isinstance(v, str) and v.strip(): nn[v.strip()] += 1
print(f'normalized_name: filled={sum(nn.values())} distinct={len(nn)} dup_groups={sum(1 for v in nn.values() if v>1)}')

# aliases cross-entity collision
alias_owner = collections.defaultdict(set)
for r in recs:
    v = r.get('aliases')
    items = v if isinstance(v, list) else (v.get('v') if isinstance(v, dict) and 'v' in v else [])
    for x in items:
        if isinstance(x, str) and x.strip(): alias_owner[x.strip()].add(r['object_id'])
coll = {k: v for k, v in alias_owner.items() if len(v) > 1}
print(f'alias strings shared by >1 company: {len(coll)} (distinct alias values total={len(alias_owner)})')

# ---------- 6. category query support ----------
print('\n## category query support (naive substring match on published text fields)')
def blob(r):
    parts = []
    for f in ['name','industry','technology_route_summary','product_description','profile_summary',
              'team_description','latest_public_updates','registered_address','geography']:
        v = r.get(f)
        if isinstance(v, str): parts.append(v)
        elif isinstance(v, dict):
            if 'head' in v: parts.append(v['head'])
            elif 'v' in v: parts.extend(v['v'])
    for f in ['industry_tags','tech_tags','aliases']:
        v = r.get(f)
        if isinstance(v, list): parts.extend(x for x in v if isinstance(x, str))
        elif isinstance(v, dict) and 'v' in v: parts.extend(v['v'])
    return ' '.join(parts)

blobs = [blob(r) for r in recs]
for cat in ['机器人', '人工智能', '半导体', '新能源', '生物医药', '医疗器械', '无人机', '自动驾驶']:
    # match with per-field granularity: count entities where the tag fields contain it
    taghit = 0; txtonly = 0
    for r in recs:
        tags = []
        for f in ['industry_tags','tech_tags','industry']:
            v = r.get(f)
            if isinstance(v, str): tags.append(v)
            elif isinstance(v, list): tags.extend(x for x in v if isinstance(x, str))
            elif isinstance(v, dict) and 'v' in v: tags.extend(v['v'])
        if any(cat in t for t in tags): taghit += 1
    for b in blobs:
        if cat in b: txtonly += 1
    print(f'  {cat:8s} in_tag_fields={taghit:>5d}   in_any_text={txtonly:>5d}')
