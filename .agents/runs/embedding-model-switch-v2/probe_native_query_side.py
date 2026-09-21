#!/usr/bin/env python3
"""Live probe: the native route's query-side treatment (option B).

One run answers four questions against the real gateway:

1. does the native route accept the **declared** batch (20), and reject 21?
2. does it accept ``text_type`` / ``instruct`` at all?
3. do those parameters *change the answer* — is query-role ≠ document-role?
4. is the query-role lane as stable as the document lane (repeat noise)?

The credential is read from ``CANONICAL_V2_EMBEDDING_API_KEY`` and is never
printed; answer bodies are never echoed either — only status codes, row counts,
dimensions, latencies and cosines.

    CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)" \
      python3 probe_native_query_side.py
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get(
    "PROBE_BASE_URL", "https://maas.qianwenaiapi.com/api/v1"
).rstrip("/")
EMBEDDINGS_PATH = "/services/embeddings/text-embedding/text-embedding"
MODEL = os.environ.get("PROBE_MODEL", "qwen3.7-text-embedding-flash")
DECLARED_BATCH = 20
QUERY_INSTRUCT = (
    "Given a Chinese-language query about Shenzhen technology companies, "
    "professors, research papers or patents, retrieve the relevant records"
)
OUTPUT = Path(
    os.environ.get(
        "PROBE_OUT",
        str(Path(__file__).with_name("native-query-side-probe.json")),
    )
)
KEY = os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY", "").strip()


def call(
    texts: list[str],
    *,
    text_type: str | None = None,
    instruct: str | None = None,
    timeout: float = 90.0,
) -> dict[str, object]:
    """One native call; the response is reduced to numbers before it is returned."""

    payload: dict[str, object] = {"model": MODEL, "input": {"texts": list(texts)}}
    if text_type is not None:
        payload["text_type"] = text_type
    if instruct is not None:
        payload["instruct"] = instruct
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
    request = urllib.request.Request(
        f"{BASE_URL}{EMBEDDINGS_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    status: int
    detail: str | None = None
    rows: list[list[float]] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            document = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read() or b"{}"
        try:
            detail = json.dumps(json.loads(body))[:300]
        except json.JSONDecodeError:
            detail = body[:300].decode("utf-8", "replace")
        document = None
    latency = time.perf_counter() - started
    if document:
        raw_rows = (document.get("output") or {}).get("embeddings") or []
        rows = [
            [float(value) for value in row.get("embedding") or []]
            for row in raw_rows
            if isinstance(row, dict)
        ]
    return {
        "status": status,
        "detail": detail,
        "latency_s": round(latency, 3),
        "rows": len(rows),
        "dims": len(rows[0]) if rows else None,
        "vectors": rows,
    }


def _fact(result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in result.items() if key != "vectors"}


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("a probe vector has a zero norm")
    return dot / (left_norm * right_norm)


def main() -> int:
    if not KEY:
        raise SystemExit("CANONICAL_V2_EMBEDDING_API_KEY is not set")
    batch = [f"深圳合成生物学教授批量探针 {index} — batch probe" for index in range(DECLARED_BATCH)]
    report: dict[str, object] = {
        "base_url": BASE_URL,
        "path": EMBEDDINGS_PATH,
        "model": MODEL,
        "declared_batch": DECLARED_BATCH,
        "query_instruct_chars": len(QUERY_INSTRUCT),
    }

    report["declared_batch_document_role"] = _fact(call(batch))
    report["over_declared_batch"] = _fact(call([*batch, "one more"]))
    report["declared_batch_query_role"] = _fact(
        call(batch, text_type="query", instruct=QUERY_INSTRUCT)
    )
    report["declared_batch_explicit_document"] = _fact(
        call(batch, text_type="document")
    )

    probe_text = "深圳有哪些研究合成生物学的教授？"
    as_document = call([probe_text])
    as_query = call([probe_text], text_type="query", instruct=QUERY_INSTRUCT)
    as_query_again = call([probe_text], text_type="query", instruct=QUERY_INSTRUCT)
    as_explicit_document = call([probe_text], text_type="document")
    report["single_document_role"] = _fact(as_document)
    report["single_query_role"] = _fact(as_query)
    report["single_query_role_repeat"] = _fact(as_query_again)
    report["single_explicit_document_role"] = _fact(as_explicit_document)

    cosines: dict[str, object] = {}
    for name, left, right in (
        ("query_role_vs_document_role", as_query, as_document),
        ("query_role_vs_its_own_repeat", as_query, as_query_again),
        ("document_role_vs_explicit_document", as_document, as_explicit_document),
    ):
        left_vectors = left["vectors"]
        right_vectors = right["vectors"]
        if left_vectors and right_vectors:
            cosines[name] = round(cosine(left_vectors[0], right_vectors[0]), 6)
    report["cosines"] = cosines

    stable = cosines.get("query_role_vs_its_own_repeat")
    different = cosines.get("query_role_vs_document_role")
    if different is None:
        report["verdict"] = "inconclusive: the route did not answer both roles"
    elif different >= 0.996:
        report["verdict"] = (
            "the route ignores the query treatment: query and document roles answer "
            f"within the measured repeat noise (cosine {different}); option B buys "
            "nothing on this route"
        )
    elif isinstance(stable, float) and different <= stable - 0.01:
        report["verdict"] = (
            f"the treatment is real: query vs document {different} is far outside "
            f"the query lane's own repeat noise ({stable})"
        )
    else:
        report["verdict"] = (
            f"ambiguous: query vs document {different} against repeat {stable}"
        )

    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
