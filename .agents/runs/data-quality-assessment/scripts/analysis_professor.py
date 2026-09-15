#!/usr/bin/env python3
import sys, collections, re, json
sys.path.insert(0,'/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/scripts')
from dqlib import load, classify_str, is_filled, pct, true_str

recs=list(load('professor')); N=len(recs)
print(f'# professor  n={N}')
FIELDS=['name','canonical_name_zh','canonical_name_en','institution','department','title','email',
        'homepage','phone','office','research_directions','paper_count','citation_count','h_index',
        'patent_ids','projects','awards','company_roles','education_history','work_history',
        'affiliation_history','metric_snapshots','contacts','profile_summary','paper_summary',
        'patent_summary','aliases','lifecycle_state','manual_override','quality_status','_supplementary']
print('\n## fill rate / placeholder rate')
print(f'{"field":24s} {"filled":>7s} {"rate":>7s} {"empty":>7s} {"placeholder":>12s}  families')
for f in FIELDS:
    filled=empty=0; ph=collections.Counter()
    for r in recs:
        v=r.get(f)
        if is_filled(v): filled+=1
        else: empty+=1
        for s in true_str(v):
            c=classify_str(s)
            if c: ph[c]+=1
    tot=sum(v for k,v in ph.items() if k!='empty')
    print(f'{f:24s} {filled:>7d} {pct(filled,N):>7s} {empty:>7d} {tot:>12d}  {dict(ph)}')

print('\n## effective fill (placeholder values counted as NOT filled)')
for f in ['email','homepage','title','department','research_directions','profile_summary',
          'paper_summary','patent_summary','canonical_name_en']:
    good=0
    for r in recs:
        v=r.get(f)
        vals=true_str(v)
        if not vals: continue
        if all(classify_str(s) or s.strip()=='' for s in vals): continue
        good+=1
    print(f'  {f:24s} effective={good:>5d}/{N} ({pct(good,N)})')

print('\n## research_directions vocabulary')
vals=collections.Counter(); n_with=0; lens=[]
for r in recs:
    v=r.get('research_directions')
    items = v.get('v') if isinstance(v,dict) and 'v' in v else []
    items=[x.strip() for x in items if isinstance(x,str) and x.strip()]
    lens.append(len(items))
    if items: n_with+=1
    for x in items: vals[x]+=1
print(f'  entities_with>=1={n_with}/{N} ({pct(n_with,N)}) total_tags={sum(lens)} unique={len(vals)} avg={sum(lens)/N:.2f} max={max(lens)}')
for k,c in vals.most_common(30): print(f'    {c:>4d}  {k[:90]}')
print(f'  singleton tags (appear once)={sum(1 for v in vals.values() if v==1)}')

print('\n## institution values (raw free text)')
inst=collections.Counter()
for r in recs:
    v=r.get('institution')
    if isinstance(v,str) and v.strip(): inst[v.strip()]+=1
print(f'  distinct={len(inst)}')
for k,c in inst.most_common(25): print(f'    {c:>5d}  {k[:70]}')
shenzhen=[k for k in inst if '深圳' in k]
print(f'  containing 深圳: {len(shenzhen)} distinct, entities={sum(inst[k] for k in shenzhen)}')

print('\n## name uniqueness / identity')
byname=collections.defaultdict(list)
for r in recs: byname[r.get('name')].append(r['object_id'])
dups={k:v for k,v in byname.items() if len(v)>1}
print(f'  distinct names={len(byname)} dup_groups={len(dups)} entities_in_dups={sum(len(v) for v in dups.values())}')
hon=collections.Counter()
for r in recs:
    nm=r.get('name') or ''
    if len(nm)==3 and re.match(r'^[\u4e00-\u9fff]+$',nm): hon[nm]+=1
print(f'  3-char Chinese names: distinct={len(hon)} total={sum(hon.values())} max_repeat={max(hon.values()) if hon else 0}')
for k,c in hon.most_common(10): print(f'    {c:>3d}  {k}')

print('\n## homepage URL quality')
proto=0; bare=0; dead=collections.Counter()
for r in recs:
    v=r.get('homepage')
    if not isinstance(v,str) or not v.strip(): continue
    s=v.strip()
    if s.lower().startswith('http'): proto+=1
    else: bare+=1; dead[s]+=1
print(f'  http(s)={proto}  non-url={bare}')
for k,c in dead.most_common(8): print(f'    {c:>4d}  {k[:70]}')

print('\n## email quality')
ok=0
vals2=collections.Counter()
for r in recs:
    v=r.get('email')
    if isinstance(v,str) and '@' in v and '.' in v.split('@')[-1]: ok+=1
    else: vals2[str(v)[:60]]+=1
print(f'  plausible emails={ok}/{N}')
for k,c in vals2.most_common(8): print(f'    {c:>5d}  {k}')

print('\n## metric coverage')
for f in ['paper_count','citation_count','h_index']:
    good=sum(1 for r in recs if isinstance(r.get(f),int))
    print(f'  {f}: {good}/{N} ({pct(good,N)})')

print('\n## title values')
t=collections.Counter()
for r in recs:
    v=r.get('title'); 
    if isinstance(v,str) and v.strip(): t[v.strip()]+=1
print(f'  distinct={len(t)}')
for k,c in t.most_common(20): print(f'    {c:>5d}  {k[:60]}')

print('\n## aliases / patent_ids (expected empty?)')
print('  aliases non-empty:', sum(1 for r in recs if is_filled(r.get('aliases'))))
print('  patent_ids non-empty:', sum(1 for r in recs if is_filled(r.get('patent_ids'))))
