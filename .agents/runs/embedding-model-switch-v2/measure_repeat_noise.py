#!/usr/bin/env python3
"""Measure the candidate gateway's repeat noise, per route, against real texts.

Why: two calibrated cosine floors (``REFERENCE_COSINE_FLOOR`` in the admin
identity check, ``_MIN_VECTOR_COSINE_SIMILARITY`` on the rebuild path) sit
~0.00014 above a *single* observed same-route repeat (0.99914). A floor has to be
derived from a distribution, not one sample, so this script measures the
distribution per text: 25 repeats through the OpenAI-compatible route, a
cross-route control against the DashScope-native route, a different-text control,
and an informational ``dimensions: 512`` run.

Secret handling: the key is read from a file whose path is given on the command
line and is never printed, logged, or written into the JSON evidence — only the
fact that it was loaded and its length.

Usage (from the repository's venv):
    python measure_repeat_noise.py [--repeats 25] [--key-file PATH]
                                   [--out repeats.json]
No bundle, index, or service is touched: this only makes HTTP calls.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

REPO_APP_DIR = Path(__file__).resolve().parents[3] / "apps/miroflow-agent"
sys.path.insert(0, str(REPO_APP_DIR))

from src.data_agents.company.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.dashscope_embeddings import (  # noqa: E402
    DashScopeTextEmbeddingClient,
)

DEFAULT_KEY_FILE = Path("/var/tmp/mirothinker-qianwen-api-key")
COMPATIBLE_BASE_URL = "https://maas.qianwenaiapi.com/compatible-mode/v1"
NATIVE_BASE_URL = "https://maas.qianwenaiapi.com/api/v1"
MODEL = "qwen3.7-text-embedding-flash"

#: Text shapes the rebuild will actually embed: two short lines (Chinese/English),
#: two medium document fragments, and one full document-length block (the shape
#: of ``IndexProjectionPoint.embedded_content``).
TEXTS: dict[str, str] = {
    "zh-short": "深圳具身智能机器人企业，专注人形机器人本体与灵巧手研发。",
    "en-short": "Thin-film lithium niobate photonic chips for high-speed optical interconnects.",
    "zh-medium": (
        "深圳市南山区某半导体设备企业，主营晶圆缺陷检测装备。"
        "产品覆盖明场/暗场光学检测与电子束复检，客户为国内头部晶圆厂。"
        "团队来自海外设备厂商与国内高校，2025 年完成 B 轮融资。"
    ),
    "en-medium": (
        "A photonic integrated circuit platform for 800G and 1.6T optical "
        "interconnects, combining thin-film lithium niobate modulators with "
        "silicon photonic waveguides and co-packaged optics for data-centre "
        "switches; the team targets volume manufacturing with wafer-level "
        "packaging and automated optical alignment."
    ),
    "zh-document": (
        "深圳市示例科技有限公司，南山区，人工智能\n"
        "公司聚焦具身智能与人形机器人整机，覆盖本体结构、灵巧手与运动控制算法。"
        "核心产品包括双足人形机器人平台与轮式协作机械臂，面向工业巡检与仓储搬运场景。"
        "团队来自国内高校机器人实验室，已完成天使轮融资。"
        "最近动态：2026-03 发布第二代灵巧手，2026-06 获得新一轮融资。"
    ),
}


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors have different dimensions")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("vector has zero norm")
    return dot / (left_norm * right_norm)


def percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    count = len(ordered)

    def at(fraction: float) -> float:
        if count == 1:
            return ordered[0]
        position = fraction * (count - 1)
        lower = int(position)
        upper = min(lower + 1, count - 1)
        weight = position - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    return {
        "count": float(count),
        "min": ordered[0],
        "p1": at(0.01),
        "p5": at(0.05),
        "p25": at(0.25),
        "median": at(0.5),
        "p75": at(0.75),
        "p95": at(0.95),
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
        "stdev": statistics.stdev(ordered) if count > 1 else 0.0,
    }


def pairwise(vectors: list[list[float]]) -> list[float]:
    values: list[float] = []
    for index, left in enumerate(vectors):
        for right in vectors[index + 1 :]:
            values.append(cosine(left, right))
    return values


def embed_compatible(
    client: EmbeddingClient,
    text: str,
    *,
    dimensions: int | None = None,
) -> tuple[list[float], float, dict[str, Any]]:
    """One compatible-route call. ``dimensions`` is informational only."""

    started = time.monotonic()
    if dimensions is None:
        vectors = client.embed_batch([text], model=MODEL)
    else:
        import httpx

        with httpx.Client(trust_env=False, timeout=client.timeout) as raw:
            response = raw.post(
                f"{client.base_url}/embeddings",
                json={"input": [text], "model": MODEL, "dimensions": dimensions},
                headers={"Authorization": f"Bearer {client.api_key}"},
            )
        response.raise_for_status()
        payload = response.json()
        vectors = [row["embedding"] for row in payload["data"]]
    elapsed = time.monotonic() - started
    return vectors[0], elapsed, {"dimensions": dimensions}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=25)
    parser.add_argument("--native-repeats", type=int, default=3)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    try:
        api_key = args.key_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"key file unreadable: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    if not api_key:
        print("key file is empty", file=sys.stderr)
        return 2
    print(f"key loaded from {args.key_file} ({len(api_key)} chars, value never printed)")

    compatible = EmbeddingClient(
        base_url=COMPATIBLE_BASE_URL,
        api_key=api_key,
        timeout=60.0,
    )
    native = DashScopeTextEmbeddingClient(
        base_url=NATIVE_BASE_URL,
        api_key=api_key,
        timeout=60.0,
    )

    report: dict[str, Any] = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "compatible_base_url": COMPATIBLE_BASE_URL,
        "native_base_url": NATIVE_BASE_URL,
        "repeats": args.repeats,
        "native_repeats": args.native_repeats,
        "texts": {
            name: {
                "char_len": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text": text,
            }
            for name, text in TEXTS.items()
        },
        "per_text": {},
        "errors": [],
    }

    compatible_vectors: dict[str, list[list[float]]] = {}
    native_vectors: dict[str, list[list[float]]] = {}
    latencies: dict[str, list[float]] = {}

    for name, text in TEXTS.items():
        vectors: list[list[float]] = []
        elapsed: list[float] = []
        for attempt in range(args.repeats):
            try:
                vector, seconds, _ = embed_compatible(compatible, text)
            except Exception as exc:  # noqa: BLE001 - record and keep measuring
                report["errors"].append(
                    {"text": name, "route": "compatible", "attempt": attempt, "error": str(exc)[:200]}
                )
                continue
            vectors.append(vector)
            elapsed.append(seconds)
        compatible_vectors[name] = vectors
        latencies[name] = elapsed
        dims = sorted({len(vector) for vector in vectors})
        noise = pairwise(vectors)
        report["per_text"][name] = {
            "dimensions": dims,
            "calls_ok": len(vectors),
            "latency_s": percentiles(elapsed) if elapsed else None,
            "repeat_cosine": percentiles(noise) if noise else None,
            "repeat_pairs": [round(value, 9) for value in noise],
            "pairs_below": {
                str(floor): sum(1 for value in noise if value < floor)
                for floor in (0.999, 0.998, 0.997, 0.995, 0.99, 0.98)
            },
        }
        print(
            f"[{name}] dims={dims} calls={len(vectors)} "
            f"repeat cosine min={min(noise):.6f} p1={report['per_text'][name]['repeat_cosine']['p1']:.6f} "
            f"p5={report['per_text'][name]['repeat_cosine']['p5']:.6f} "
            f"median={report['per_text'][name]['repeat_cosine']['median']:.6f} max={max(noise):.6f}"
            if noise
            else f"[{name}] no successful calls"
        )

    # Control 1: the same texts through the native route, compared to each
    # compatible repeat (route difference).
    report["cross_route"] = {}
    for name, text in TEXTS.items():
        native_batch: list[list[float]] = []
        for attempt in range(args.native_repeats):
            try:
                raw = native.embed_batch([text], model=MODEL)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(
                    {"text": name, "route": "native", "attempt": attempt, "error": str(exc)[:200]}
                )
                continue
            native_batch.append([float(value) for value in raw[0]])
        native_vectors[name] = native_batch
        values = [
            cosine(left, right)
            for left in native_batch
            for right in compatible_vectors.get(name, [])
        ]
        report["cross_route"][name] = {
            "native_calls_ok": len(native_batch),
            "native_dimensions": sorted({len(vector) for vector in native_batch}),
            "cosine_vs_compatible": percentiles(values) if values else None,
        }
        if values:
            print(
                f"[{name}] cross-route cosine (native vs compatible) "
                f"min={min(values):.6f} median={statistics.fmean(values):.6f} max={max(values):.6f}"
            )
        else:
            print(
                f"[{name}] cross-route: no comparable native calls "
                f"({report['errors'][-1]['error'] if report['errors'] else 'unknown'})"
            )

    # Control 2: two different texts must be far apart.
    names = [name for name in TEXTS if compatible_vectors.get(name)]
    if len(names) >= 2:
        left_name, right_name = names[0], names[1]
        values = [
            cosine(left, right)
            for left in compatible_vectors[left_name]
            for right in compatible_vectors[right_name]
        ]
        report["different_texts"] = {
            "left": left_name,
            "right": right_name,
            "cosine": percentiles(values),
        }
        print(
            f"[different texts: {left_name} vs {right_name}] cosine "
            f"min={min(values):.6f} median={report['different_texts']['cosine']['median']:.6f} "
            f"max={max(values):.6f}"
        )

    # Informational: a smaller requested dimension, if the route supports it.
    report["dimensions_512"] = {}
    for name in names[:1]:
        vectors = []
        for attempt in range(3):
            try:
                vector, _, _ = embed_compatible(compatible, TEXTS[name], dimensions=512)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(
                    {"text": name, "route": "compatible", "attempt": attempt, "dimensions": 512, "error": str(exc)[:200]}
                )
                continue
            vectors.append(vector)
        noise = pairwise(vectors)
        report["dimensions_512"][name] = {
            "dimensions": sorted({len(vector) for vector in vectors}),
            "calls_ok": len(vectors),
            "repeat_cosine": percentiles(noise) if noise else None,
        }
        if noise:
            print(
                f"[{name} dimensions=512] dims={report['dimensions_512'][name]['dimensions']} "
                f"repeat cosine min={min(noise):.6f} median={percentiles(noise)['median']:.6f} max={max(noise):.6f}"
            )
        else:
            print(
                f"[{name} dimensions=512] no successful calls "
                f"({report['errors'][-1]['error'] if report['errors'] else 'unknown'})"
            )

    out_path = args.out or Path(__file__).with_name("repeat-noise-measurement.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out_path}")
    if report["errors"]:
        print(f"{len(report['errors'])} errors recorded (see JSON)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
