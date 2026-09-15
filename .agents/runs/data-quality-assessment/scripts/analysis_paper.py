#!/usr/bin/env python3
import sys, collections, re, json
sys.path.insert(0,'/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/scripts')
from dqlib import load, classify_str, is_filled, pct, true_str

recs=list(load('paper')); N=len(recs)
print(f'# paper  n={N}')
FIELDS=['title','title_zh','year','venue','doi','arxiv_id','authors','citation_count',
        'reference_count','professor_ids','fields_of_study','keywords','abstract','summary_zh',
        'summary_text','tldr','identifiers','publications','references','full_texts','license',
        'oa_status','pdf_path','publication_date','quality_status']
print('\n## fill / placeholder')
print(f'{"field":20s} {"filled":>7s} {"rate":>7s} {"empty":>7s} {"placeholder":>12s} families')
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
    print(f'{f:20s} {filled:>7d} {pct(filled,N):>7s} {empty:>7d} {tot:>12d} {dict(ph)}')

print('\n## year distribution')
y=collections.Counter()
for r in recs:
    v=r.get('year')
    if isinstance(v,int): y[v]+=1
print('  range', min(y), max(y))
for k in sorted(y): 
    if k>=2005: print(f'    {k}: {y[k]}')
print('  future years (>2026):', sum(v for k,v in y.items() if k>2026))
print('  pre-1990:', sum(v for k,v in y.items() if k<1990))

print('\n## venue top 20')
v=collections.Counter()
for r in recs:
    x=r.get('venue')
    if isinstance(x,dict) and 'label' in x: v[x['label']]+=1
print(f'  distinct venues={len(v)}')
for k,c in v.most_common(20): print(f'    {c:>5d}  {k[:80]}')

print('\n## DOI quality')
ok=dash=notdoi=dupe=0
d=collections.Counter()
bad=[]
for r in recs:
    x=r.get('doi')
    if not isinstance(x,str): continue
    s=x.strip(); d[s]+=1
    if re.match(r'^10\.\d{4,9}/\S+$', s): ok+=1
    else: bad.append(s)
print(f'  total={sum(d.values())} wellformed(10.NNNN/...)= {ok}  malformed={len(bad)}')
print('  sample malformed:', bad[:8])
print('  duplicate DOI values:', sum(1 for k,c in d.items() if c>1), 'rows involved:', sum(c for c in d.values() if c>1))
for k,c in d.most_common(5):
    if c>1: print(f'    {c:>3d}  {k[:70]}')

print('\n## title duplicate / shell check')
def tnorm(t):
    t=t.lower().strip()
    t=re.sub(r'[\s\u3000]+',' ',t)
    t=re.sub(r'[^\w\u4e00-\u9fff ]','',t)
    return t
tt=collections.Counter()
for r in recs:
    x=r.get('title')
    if isinstance(x,str): tt[tnorm(x)]+=1
d2={k:c for k,c in tt.items() if c>1}
print(f'  distinct normalized titles={len(tt)} groups with >1={len(d2)} rows in dup groups={sum(d2.values())}')
for k,c in sorted(d2.items(), key=lambda kv:-kv[1])[:10]: print(f'    {c:>3d}  {k[:70]}')

print('\n## authors stats')
cnt=collections.Counter(); tot=0; nauth=collections.Counter(); noname=0
for r in recs:
    a=r.get('authors')
    names = a.get('v') if isinstance(a,dict) and 'v' in a else []
    n = a.get('n') if isinstance(a,dict) else 0
    nauth[n]+=1; tot+=n
    for x in names:
        cnt[x]+=1
        if not x or not str(x).strip(): noname+=1
print(f'  papers={len(nauth)} author_rows={tot} avg={tot/N:.2f} distinct_names={len(cnt)}')
print(f'  top repeated names (ambiguity risk): {cnt.most_common(10)}')
print(f'  papers with 1 author: {nauth.get(1,0)}, >50 authors: {sum(v for k,v in nauth.items() if k>50)}')

print('\n## unanchored')
ua=sum(1 for r in recs if 'paper_unanchored' in (r.get('eligibility_limitations') or []))
print(f'  papers with paper_unanchored limitation: {ua}/{N} ({pct(ua,N)})')
