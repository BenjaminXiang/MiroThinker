#!/usr/bin/env python3
"""Extract compact per-domain records from the run15 sealed lookup pack. READ-ONLY.

Writes one gzipped JSONL per domain into .agents/runs/data-quality-assessment/data/
Big text fields are stored as {len, head} so downstream placeholder scans stay cheap.
"""
import sqlite3, json, gzip, os, sys

DB = 'file:/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/lookup.sqlite3?mode=ro&immutable=1'
OUT = '/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/data'
os.makedirs(OUT, exist_ok=True)

TEXT = 'text'      # {len, head}
FULL = 'full'      # verbatim (short strings / tag lists)
LIST = 'list'      # list: keep count + full values (bounded)
BIG = 'big'        # nested: count + keys only

SPEC = {
 'company': {
   'name':FULL,'normalized_name':FULL,'aliases':LIST,'industry':FULL,'industry_tags':LIST,
   'tech_tags':LIST,'geography':FULL,'founded_at':FULL,'key_personnel':BIG,
   'legal_representative':FULL,'website':FULL,'credit_code':FULL,'registered_capital':FULL,
   'registered_address':FULL,'patent_count':FULL,'products':BIG,'business_scenarios':BIG,
   'capabilities':BIG,'financing_events':BIG,'latest_public_updates':BIG,
   'personnel_education':BIG,'personnel_work_experience':BIG,
   'product_description':TEXT,'profile_summary':TEXT,'technology_route_summary':TEXT,
   'team_description':TEXT,'quality_status':FULL,'_supplementary':BIG,
 },
 'professor': {
   'name':FULL,'canonical_name_zh':FULL,'canonical_name_en':FULL,'institution':FULL,
   'department':FULL,'title':FULL,'email':FULL,'phone':FULL,'office':FULL,'homepage':FULL,
   'research_directions':LIST,'paper_count':FULL,'citation_count':FULL,'h_index':FULL,
   'patent_ids':LIST,'projects':BIG,'awards':BIG,'company_roles':BIG,'education_history':BIG,
   'work_history':BIG,'affiliation_history':BIG,'metric_snapshots':BIG,'contacts':BIG,
   'profile_summary':TEXT,'paper_summary':TEXT,'patent_summary':TEXT,
   'lifecycle_state':FULL,'quality_status':FULL,'manual_override':FULL,'_supplementary':BIG,
 },
 'paper': {
   'title':FULL,'title_zh':FULL,'authors':LIST,'venue':FULL,'year':FULL,'doi':FULL,
   'arxiv_id':FULL,'publication_date':FULL,'citation_count':FULL,'reference_count':FULL,
   'professor_ids':LIST,'fields_of_study':LIST,'keywords':LIST,'license':FULL,
   'oa_status':FULL,'pdf_path':FULL,'quality_status':FULL,
   'identifiers':BIG,'publications':BIG,'references':BIG,'full_texts':BIG,
   'enrichment_sources':BIG,'evidence':BIG,
   'abstract':TEXT,'summary_zh':TEXT,'summary_text':TEXT,'tldr':TEXT,
 },
 'patent': {
   'patent_number':FULL,'title':FULL,'title_en':FULL,'applicants':LIST,'inventors':LIST,
   'company_ids':LIST,'professor_ids':LIST,'ipc_codes':LIST,'filing_date':FULL,
   'grant_date':FULL,'publication_date':FULL,'patent_type':FULL,'quality_status':FULL,
   'technical_summaries':BIG,'milestones':BIG,
   'abstract':TEXT,'summary_text':TEXT,'technology_effect':TEXT,
 },
}

def preview_text(v, head=160):
    if v is None:
        return None
    if not isinstance(v, str):
        v = json.dumps(v, ensure_ascii=False)
    return {'len': len(v), 'head': v[:head]}

def is_ref(v):
    return isinstance(v, dict) and set(v.keys()) == {'reference_id', 'name'}

def pack(v, mode):
    if mode == TEXT:
        return preview_text(v)
    if mode == FULL:
        if is_ref(v):
            return {'label': v['name'], 'ref': v['reference_id']}
        return v
    if mode == LIST:
        if v is None: return None
        if isinstance(v, str): return {'_str': v[:4000]}
        if isinstance(v, list):
            if v and all(is_ref(x) for x in v):
                return {'n': len(v), 'v': [x['name'] for x in v],
                        'refs': [x['reference_id'] for x in v]}
            out = [x if isinstance(x, str) else (x.get('name') or json.dumps(x, ensure_ascii=False))
                   for x in v]
            return {'n': len(out), 'v': out[:60]}
        if is_ref(v):
            return {'n': 1, 'v': [v['name']], 'refs': [v['reference_id']]}
        return {'_other': json.dumps(v, ensure_ascii=False)[:4000]}
    if mode == BIG:
        if v is None: return None
        if isinstance(v, list):
            return {'kind': 'list', 'n': len(v), 'names': [x.get('name') for x in v if isinstance(x, dict)],
                    'sample': json.dumps(v[0], ensure_ascii=False)[:300] if v else None}
        if isinstance(v, dict):
            return {'kind': 'dict', 'keys': sorted(v.keys())[:40]}
        return {'kind': type(v).__name__}
    raise ValueError(mode)

def main():
    con = sqlite3.connect(DB, uri=True)
    limits = {}
    for dom, spec in SPEC.items():
        pid = f'lookup:exact-lookup:{dom}'
        path = os.path.join(OUT, f'{dom}.jsonl.gz')
        n = 0
        with gzip.open(path, 'wt', encoding='utf-8') as fh:
            for cid, dj in con.execute(
                    'select canonical_object_id, document_json from lookup_document where projection_id=?', (pid,)):
                d = json.loads(dj)
                lc = json.loads(d['lookup_content'])
                rec = {
                    'object_id': cid,
                    'identity_id': lc.get('canonical_identity_id'),
                    'entity_type': lc.get('entity_type'),
                    'eligibility_outcome': d.get('eligibility_outcome'),
                    'eligibility_limitations': d.get('eligibility_limitations'),
                    'source_evidence_ids_n': len(d.get('source_evidence_ids') or []),
                }
                for k, mode in spec.items():
                    if k in lc:
                        rec[k] = pack(lc[k], mode)
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
                n += 1
        limits[dom] = n
        print(f'{dom}: {n} records -> {path}')
    con.close()
    json.dump(limits, open(os.path.join(OUT, '_counts.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
