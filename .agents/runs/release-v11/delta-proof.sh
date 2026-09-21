#!/usr/bin/env bash
# Delta proof: v1.1 re-seal vs the pack the live service mounts.
#
# Answers one question with bytes: what did the re-seal change?
# Everything here is read-only against both packs.
#
# Usage: bash .agents/runs/release-v11/delta-proof.sh [A] [B]
set -euo pipefail

A=${1:-/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound}
B=${2:-/var/tmp/mirothinker-data-v2/serving-pack-run16-v11}

echo "== files (size + sha256) =="
for pack in "$A" "$B"; do
  echo "-- $pack"
  ( cd "$pack" && find . -maxdepth 1 -type f -printf '%f\n' | sort | while read -r f; do
      printf '%12d  %s  %s\n' "$(stat -c %s "$f")" "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
    done )
done

echo
echo "== per-file verdict =="
( cd "$A" && find . -maxdepth 1 -type f -printf '%f\n' | sort ) > /tmp/dp_a_files.txt
( cd "$B" && find . -maxdepth 1 -type f -printf '%f\n' | sort ) > /tmp/dp_b_files.txt
diff /tmp/dp_a_files.txt /tmp/dp_b_files.txt > /dev/null \
  && echo "file set: identical" || { echo "file set DIFFERS:"; diff /tmp/dp_a_files.txt /tmp/dp_b_files.txt; }
while read -r f; do
  ha=$(sha256sum "$A/$f" | cut -d' ' -f1)
  hb=$(sha256sum "$B/$f" | cut -d' ' -f1)
  if [ "$ha" = "$hb" ]; then echo "same      $f"; else echo "CHANGED   $f"; fi
done < /tmp/dp_a_files.txt

echo
echo "== manifest field diff, and the data-file hashes the manifest records =="
python3 - "$A" "$B" <<'PY'
import json, sys
a, b = (json.load(open(f"{p}/manifest.json")) for p in sys.argv[1:3])
for key in sorted(set(a) | set(b)):
    if a.get(key) != b.get(key):
        print(f"field differs: {key}")
        if key == "files":
            for name in sorted(set(a.get(key, {})) | set(b.get(key, {}))):
                ha, hb = a[key].get(name), b[key].get(name)
                print(f"   recorded hash  {'same' if ha == hb else 'CHANGED'}  {name}"
                      + ("" if ha == hb else f"  {ha} -> {hb}"))
        elif key in ("generated_at", "generator_run_id", "reader_contract_sha256"):
            print(f"   {a.get(key)} -> {b.get(key)}")
print("unchanged fields:", sorted(k for k in set(a) | set(b) if a.get(k) == b.get(k)))
print("recorded reader_contract_sha256:", b.get("reader_contract_sha256"))
PY
