#!/usr/bin/env python3
import sys, collections, re, json
sys.path.insert(0,'/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/scripts')
from dqlib import load, classify_str, is_filled, pct, true_str

recs=list(load('patent')); N=len(recs)
print(f'# patent  n={N}')
FIELDS=['patent_number','title','title_en','applicants','inventors','company_ids','professor_ids',
        'ipc_codes','filing_date','grant_date','publication_date','patent_type','abstract',
        'summary_text','technology_effect','technical_summaries','milestones','quality_status']
print('\n## fill / placeholder')
print(f'{"field":22s} {"filled":>7s} {"rate":>7s} {"empty":>7s} {"placeholder":>12s} families')
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
    print(f'{f:22s} {filled:>7d} {pct(filled,N):>7s} {empty:>7d} {tot:>12d} {dict(ph)}')

print('\n## patent_number pattern')
pat=collections.Counter(); ex={}
for r in recs:
    v=r.get('patent_number')
    if not isinstance(v,str) or not v.strip(): pat['<empty>']+=1; continue
    s=v.strip()
    if re.match(r'^CN\d{9,13}(\.\d)?[A-Z]?$', s): k='CN + 9-13 digits (+./letter)'
    elif re.match(r'^CN', s): k='CN other'
    elif re.match(r'^[A-Z]{2}\d', s): k='other-country code'
    else: k='unrecognized'
    pat[k]+=1; ex.setdefault(k, s)
for k,c in pat.most_common(): print(f'  {c:>6d}  {k}   e.g. {ex.get(k)}')
dupnum=collections.Counter()
for r in recs:
    v=r.get('patent_number')
    if isinstance(v,str): dupnum[v.strip()]+=1
print(f'  distinct patent_number={len(dupnum)} duplicate_values={sum(1 for c in dupnum.values() if c>1)} rows_in_dups={sum(c for c in dupnum.values() if c>1)}')
for k,c in dupnum.most_common(5):
    if c>1: print(f'    {c:>3d}  {k}')

print('\n## dates')
years=collections.Counter(); pd=collections.Counter()
for r in recs:
    x=r.get('publication_date')
    if isinstance(x,str) and len(x)>=4: pd[x[:4]]+=1
print('  publication_date year dist (top):', pd.most_common(10))
print('  publication_date distinct-year count:', len(pd))
fd=[r.get('filing_date') for r in recs if isinstance(r.get('filing_date'),str)]
print(f'  filing_date filled={len(fd)}; sample={fd[:3]}')
# filing after publication?
badorder=0
for r in recs:
    f=r.get('filing_date'); p=r.get('publication_date')
    if isinstance(f,str) and isinstance(p,str) and f>p: badorder+=1
print(f'  filing_date > publication_date: {badorder}')

print('\n## patent_type values')
pt=collections.Counter()
for r in recs:
    v=r.get('patent_type')
    if isinstance(v,str): pt[v]+=1
for k,c in pt.most_common(20): print(f'  {c:>6d}  {k}')

print('\n## title stats')
t=collections.Counter(); lens=[]
for r in recs:
    v=r.get('title')
    if isinstance(v,str): t[v.strip()]+=1; lens.append(len(v))
print(f'  distinct titles={len(t)}')
d=[(k,c) for k,c in t.items() if c>1]
print(f'  duplicate title values={len(d)} rows_in_dups={sum(c for _,c in d)}')
for k,c in sorted(d,key=lambda x:-x[1])[:10]: print(f'    {c:>3d}  {k[:70]}')
print(f'  title char-len: min={min(lens)} max={max(lens)} avg={sum(lens)/len(lens):.1f}')

print('\n## company binding')
bound=0; unb=0
for r in recs:
    a=r.get('applicants')
    refs=a.get('refs') if isinstance(a,dict) else None
    # applicants were packed as json strings; fall back to raw scan
print('  (see applicants-authors.txt for binding detail)')
print('  company_ids filled:', sum(1 for r in recs if is_filled(r.get('company_ids'))))
print('  inventors filled:', sum(1 for r in recs if is_filled(r.get('inventors'))))

print('\n## summary/abstract content')
sl=[]; gl=0
for r in recs:
    v=r.get('summary_text')
    if isinstance(v,str): sl.append(len(v))
print(f'  summary_text len avg={sum(sl)/len(sl):.0f} min={min(sl)} max={max(sl)}')
lg=collections.Counter()
for r in recs:
    v=r.get('summary_text')
    if isinstance(v,str): lg[v[:20]]+=1
print('  most common summary_text prefixes:')
for k,c in lg.most_common(5): print(f'    {c:>5d}  {k!r}')
