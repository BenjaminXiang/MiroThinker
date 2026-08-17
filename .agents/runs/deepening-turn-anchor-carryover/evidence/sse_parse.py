#!/usr/bin/env python3
"""Parse an SSE dump from /api/chat/stream.

Usage: sse_parse.py <file.sse>

Prints:
- event type counts
- concatenated answer_chunk text (streamed deltas)
- final `answer` event answer_text + answer_style
- whether the streamed text differs from the final answer (correction fired)
- error/done event presence
"""
import json
import sys


def parse(path: str) -> dict:
    events = []  # list of (event_name, data_str)
    event = None
    data_lines: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip())
            elif line == "":
                if event is not None or data_lines:
                    events.append((event or "message", "\n".join(data_lines)))
                event = None
                data_lines = []
    if event is not None or data_lines:
        events.append((event or "message", "\n".join(data_lines)))

    counts: dict[str, int] = {}
    chunks: list[str] = []
    answer_payload = None
    error_events = []
    done_seen = False
    plan_views = None
    web_items = None

    for name, data in events:
        counts[name] = counts.get(name, 0) + 1
        if name == "answer_chunk":
            try:
                chunks.append(json.loads(data).get("text", ""))
            except json.JSONDecodeError:
                chunks.append(data)
        elif name == "answer":
            try:
                answer_payload = json.loads(data)
            except json.JSONDecodeError:
                answer_payload = {"_raw": data}
        elif name == "error":
            error_events.append(data)
        elif name == "done":
            done_seen = True
        elif name == "plan_done":
            try:
                plan_views = json.loads(data).get("views")
            except json.JSONDecodeError:
                pass
        elif name == "retrieval_done":
            try:
                web_items = json.loads(data).get("web_items")
            except json.JSONDecodeError:
                pass

    streamed = "".join(chunks)
    final_text = (answer_payload or {}).get("answer_text", "")
    return {
        "counts": counts,
        "streamed_text": streamed,
        "final_text": final_text,
        "answer_style": (answer_payload or {}).get("answer_style"),
        "query_type": (answer_payload or {}).get("query_type"),
        "clarification": (answer_payload or {}).get("clarification"),
        "correction_fired": bool(final_text) and streamed != final_text,
        "error_events": error_events,
        "done_seen": done_seen,
        "plan_views": plan_views,
        "web_items_titles": [it.get("title") for it in (web_items or [])],
    }


def main() -> None:
    path = sys.argv[1]
    r = parse(path)
    print(f"== {path}")
    print(f"event counts: {r['counts']}")
    print(f"plan views: {r['plan_views']}")
    print(f"answer_style: {r['answer_style']}  query_type: {r['query_type']}")
    print(f"clarification: {r['clarification']}")
    print(f"done event: {r['done_seen']}  error events: {r['error_events']}")
    print(f"streamed chars: {len(r['streamed_text'])}  final chars: {len(r['final_text'])}")
    print(f"CORRECTION FIRED (streamed != final): {r['correction_fired']}")
    if r["correction_fired"]:
        s, f = r["streamed_text"], r["final_text"]
        # find first divergence
        i = 0
        while i < min(len(s), len(f)) and s[i] == f[i]:
            i += 1
        print(f"first divergence at char {i}")
        print(f"streamed[{max(0, i - 30)}:{i + 80}]: {s[max(0, i - 30):i + 80]!r}")
        print(f"final  [{max(0, i - 30)}:{i + 80}]: {f[max(0, i - 30):i + 80]!r}")
    print("-- web_items titles --")
    for t in r["web_items_titles"]:
        print(f"  - {t}")
    print("-- final answer text --")
    print(r["final_text"])


if __name__ == "__main__":
    main()
