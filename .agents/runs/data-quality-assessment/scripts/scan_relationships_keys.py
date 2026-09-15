#!/usr/bin/env python3
"""Stream relationships.json once, reporting top-level keys + value byte spans (no full load)."""
import os, json, sys

PATH = '/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/relationships.json'

def scan():
    depth = 0
    in_str = False
    esc = False
    keys = []          # (key, value_start_offset_after_colon)
    cur_key = []
    reading_key = False
    expect_key = False
    f = open(PATH, 'rb')
    off = 0
    CH = 1 << 22
    pending = b''
    while True:
        buf = f.read(CH)
        if not buf:
            break
        if in_str:
            # fast path: still inside a string that started in a previous chunk
            i = 0
            while i < len(buf):
                c = buf[i:i+1]
                if esc: esc = False
                elif c == b'\\': esc = True
                elif c == b'"':
                    in_str = False
                    if reading_key and depth == 1:
                        keys.append((''.join(cur_key), off + i + 1))
                    reading_key = False
                    i += 1
                    break
                elif reading_key and c >= b' ':
                    cur_key.append(c.decode('utf-8', 'replace'))
                i += 1
            buf = buf[i:]
            off += i
            if not buf:
                continue
        start = off
        for i, ch in enumerate(buf):
            c = bytes([ch])
            if in_str:
                if esc: esc = False
                elif c == b'\\': esc = True
                elif c == b'"':
                    in_str = False
                    reading_key = False
                    if depth == 1:
                        keys.append((''.join(cur_key), off + i + 1))
            elif c == b'"':
                in_str = True
                if depth == 1:
                    reading_key = True
                    cur_key = []
            elif c in b'{[':
                depth += 1
            elif c in b'}])' :
                depth -= 1
            elif c == b':' and depth == 1:
                reading_key = False
        off += len(buf)
        if off % (1 << 28) < CH:
            print(f'  ..{off/1e9:.2f} GB', file=sys.stderr)
    f.close()
    return keys

if __name__ == '__main__':
    ks = scan()
    print(json.dumps(ks, ensure_ascii=False, indent=1)[:4000])
