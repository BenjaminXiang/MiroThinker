#!/usr/bin/env python3
"""G2 viewer: print selected sections of g2-run14-identity-audit.json compactly."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else (
    "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series/out/g2-run14-identity-audit.json"
)
what = sys.argv[2] if len(sys.argv) > 2 else "clusters"
with open(path, encoding="utf-8") as fh:
    r = json.load(fh)

if what == "clusters":
    print("# all stem clusters")
    for c in r["conflicts"]["stem"]["clusters_all"]:
        ms = "; ".join(f"{m['name']} [{m['family']}] {m['cid']}" for m in c["members"])
        print(f"- {c['cluster']} (size={c['size']}, conflict_fields={c['conflicting_fields']}): {ms}")
    print()
    print("# core clusters")
    for c in r["conflicts"]["core"]["clusters_all"]:
        ms = "; ".join(f"{m['name']} [{m['family']}]" for m in c["members"])
        print(f"- {c['cluster']} (size={c['size']}, conflict_fields={c['conflicting_fields']}): {ms}")
elif what == "prof":
    print("# professor name clusters")
    for c in r["professor_name_samples"]:
        ms = "; ".join(f"{m['name']} [{m['family']}]" for m in c["members"])
        print(f"- {c['key']} (size={c['size']}): {ms}")
elif what == "paper":
    print("# paper title clusters")
    for c in r["paper_title_samples"]:
        ms = "; ".join(f"{m['name']} [{m['family']}]" for m in c["members"])
        print(f"- {c['key'][:80]} (size={c['size']}): {ms}")
elif what == "examples":
    for f, exs in r["conflicts"]["stem"]["field_examples"].items():
        print(f"== {f} ==")
        for e in exs:
            print(f"  [{e['cluster']}] " + " || ".join(e["values"]))
elif what == "placeholders":
    print(json.dumps(r["conflicts"]["placeholder_docs_by_field_family"], indent=2, ensure_ascii=False))
elif what == "top":
    for c in r["conflicts"]["stem"]["clusters_all"][:25]:
        ms = "; ".join(f"{m['name']}" for m in c["members"])
        print(f"- {c['cluster']} size={c['size']} conf={c['conflicting_fields']}: {ms}")
