#!/usr/bin/env python3
"""Probe: union of field keys per domain + type/length stats. READ-ONLY."""
import sqlite3, json, collections, sys

DB = 'file:/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/lookup.sqlite3?mode=ro&immutable=1'

def main():
    con = sqlite3.connect(DB, uri=True)
    domains = {}
    for dom in ['company', 'professor', 'paper', 'patent']:
        pid = f'lookup:exact-lookup:{dom}'
        keys = collections.Counter()
        top_keys = collections.Counter()
        n = 0
        cur = con.execute('select document_json from lookup_document where projection_id=?', (pid,))
        for (dj,) in cur:
            d = json.loads(dj)
            for k in d:
                top_keys[k] += 1
            lc = json.loads(d['lookup_content'])
            for k in lc:
                keys[k] += 1
            n += 1
        domains[dom] = (n, top_keys, keys)
        print('=' * 30, dom, f'n={n}')
        print('  -- outer doc keys --')
        for k, c in top_keys.most_common():
            print(f'    {c:>7}/{n}  {k}')
        print('  -- lookup_content keys --')
        for k, c in keys.most_common():
            print(f'    {c:>7}/{n}  {k}')
    con.close()

if __name__ == '__main__':
    main()
