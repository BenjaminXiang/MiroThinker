"""Run16 cutover probes: two verbatim turns + TTFT, against the live 18188."""

from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:18188"


def probe(query: str, timeout: int = 240) -> dict:
    jar = http.cookiejar.CookieJar()
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    t0 = time.time()
    first = None
    raw = b""
    with opener.open(req, timeout=timeout) as resp:
        for chunk in resp:
            if first is None:
                first = time.time() - t0
            raw += chunk
    total = time.time() - t0
    text = raw.decode("utf-8", errors="replace")
    events: list[str] = []
    answer = None
    current = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current = line[7:].strip()
            events.append(current)
        elif line.startswith("data: {") and current == "answer":
            try:
                answer = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return {
        "query": query,
        "first_chunk_s": None if first is None else round(first, 2),
        "total_s": round(total, 2),
        "events": events,
        "answer": answer,
    }


def main() -> int:
    queries = sys.argv[1:] or ["字节跳动", "优必选有哪些专利"]
    for query in queries:
        try:
            result = probe(query)
        except Exception as exc:  # noqa: BLE001
            print(f"== {query}\nPROBE FAILED: {type(exc).__name__}: {exc}")
            continue
        answer = result["answer"] or {}
        text = str(answer.get("answer_text") or answer.get("text") or "")
        citations = answer.get("citations") or []
        print(f"===== {query}")
        print(
            f"TTFT(first_chunk)={result['first_chunk_s']}s total={result['total_s']}s "
            f"events={len(result['events'])}"
        )
        print("answer:", text.replace("\n", " ")[:420])
        print("keys:", sorted(answer.keys())[:14])
        for cite in citations[:10]:
            print(
                "  cite:",
                cite.get("type"),
                "|",
                str(cite.get("label"))[:48],
                "|",
                str(cite.get("url"))[:70],
            )
        print(f"citations_total={len(citations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
