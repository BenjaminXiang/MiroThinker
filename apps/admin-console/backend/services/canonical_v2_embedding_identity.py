"""Is the embedding endpoint the operator is about to switch to the same space?

Why this exists: a customer-site operator points the embedding address at
another host. Every transport-level check passes — the endpoint answers 200,
it returns 4096 floats, the model name in the response is a string — and the
vector lane then ranks the whole index through a *different* vector space, i.e.
silently wrong answers. Nothing in the serving line compares the endpoint
against the space the index was built in (the check that would have caught it is
disabled: ``knowledge_read_isolated._validate_release_bound_vector_evidence``,
2026-08-30 — see ``openspec/changes/embedding-endpoint-configurable-and-lane-fail-open``).

So the comparison happens where the operator stands: the embedding card's
connection test. The probe is an *identity* check, never a ranking check:

* **Arm ``reference``** — embed one fixed probe string twice, against the
  address the embedding bundle records (mirrored by
  ``company/vectorizer.py:_DEFAULT_EMBEDDING_URL``, the same literal
  ``resolve_embedding`` falls back to) and against the configured one; cosine
  ≥ :data:`REFERENCE_COSINE_FLOOR` means the two answers live in one space.
* **Arm ``index``** — fallback when the recorded endpoint is unreachable (a
  customer box that has left the school network): take one document's verbatim
  ``embedded_content`` out of the serving pack's ``index_point`` table, embed it
  with the configured endpoint, and compare against the vector the index already
  stored for that document in ``vector_matrix.npz``; cosine
  ≥ :data:`INDEX_COSINE_FLOOR` means the endpoint reproduces the index's own
  vectors. A bounded nearest-neighbour sample is read as well, so "the document
  is its own nearest neighbour" is checked, not assumed.

Both arms are read-only, never touch the bundle (adding a field there would
change ``content_sha256`` and force a re-seal) and never echo the credential or
an upstream body.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
import urllib.error
import urllib.request

EMBEDDINGS_PATH = "/embeddings"

#: One fixed string, used for both arms. Mixed script and a rare token so a
#: tokenizer difference shifts the vector instead of hiding in a near-duplicate.
PROBE_TEXT = (
    "canonical-v2 embedding identity probe ｜ 深圳科创数据平台向量身份校验 "
    "｜ probe-0123456789abcdef"
)

#: Reference arm. Two addresses of one model are expected to answer with the
#: same vector — but the candidate gateway is stochastic, so "the same vector"
#: needs a floor with room: measured 2026-09-21 (30 repeats per text, same route
#: and address), answers are bimodal (identical or ~0.998) with a pooled minimum
#: of 0.998004 over 1305 pairs and 0.997556 in an earlier run, the noisy mode
#: moving ~0.0013 between runs. With the operator's setting unset both probe
#: calls go to the *same* address, so that repeat noise is what this arm
#: compares. 0.999 sat 0.00014 above the noise floor (a coin-flip failure on a
#: healthy endpoint); 0.99 keeps 0.0076 below the lowest repeat ever measured
#: while staying 0.06 above the highest wrong-answer measurement (a sibling
#: route of the same model: 0.860–0.933) and far above another space (≈ −0.03).
REFERENCE_COSINE_FLOOR = 0.99
#: Index arm. Calibrated on the live release: the endpoint reproduces the stored
#: vector of a document it embedded at build time to ≥0.9999, while an endpoint
#: in another space lands near 0 (measured — see verification.md). It carries
#: ~0.9 % of headroom against the gateway's measured repeat noise, so it stays
#: where it was; it now equals the reference floor, one rule for both arms.
INDEX_COSINE_FLOOR = 0.99
#: Rows read for the nearest-neighbour check (stride over the persisted matrix,
#: ~26MB instead of the full 1.7GB: this runs inside the serving process).
INDEX_SAMPLE_STRIDE = 64

_SERVING_PACK_ENV = "CANONICAL_V2_SERVING_PACK"
_LOOKUP_FILENAME = "lookup.sqlite3"
_MATRIX_FILENAME = "vector_matrix.npz"
_INDEX_MARKER_FILENAME = ".canonical-v2-isolated-index-target.json"
_MATRIX_MEMBER = "matrix.npy"
_POINT_IDS_MEMBER = "point_ids.npy"

_HEADER_READERS: dict[int, str] = {
    1: "read_array_header_1_0",
    2: "read_array_header_2_0",
}


def _read_matrix_header(handle: Any) -> tuple[tuple[int, ...], Any, int]:
    """(shape, dtype, data offset) of a ``.npy`` stream, without reading its body."""

    import numpy as np

    version = np.lib.format.read_magic(handle)
    reader = getattr(np.lib.format, _HEADER_READERS.get(int(version[0]), ""), None)
    if reader is None:
        raise EmbeddingIdentityUnavailable("不支持的 .npy 版本")
    shape, _fortran, dtype = reader(handle)
    return tuple(shape), dtype, int(handle.tell())


DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class EmbeddingIdentityReport:
    """What the operator needs to decide: arm, cosine, verdict, next action."""

    arm: str | None
    passed: bool | None
    cosine: float | None
    detail: str
    threshold: float | None = None
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "passed": self.passed,
            "cosine": self.cosine,
            "threshold": self.threshold,
            "detail": self.detail,
            "checks": self.checks,
        }


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("embedding vector has a zero norm")
    return dot / (left_norm * right_norm)


def _post_embeddings(
    base_url: str, text: str, *, api_key: str, model: str, timeout: float
) -> tuple[float, ...]:
    """One bounded POST. The body is parsed here and never returned to a caller."""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{EMBEDDINGS_PATH}",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        exc.read()
        raise EmbeddingIdentityUnavailable(f"端点返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise EmbeddingIdentityUnavailable(
            f"端点不可达（{type(exc).__name__}）"
        ) from exc
    try:
        document = json.loads(raw)
        rows = sorted(document["data"], key=lambda item: item["index"])
        vector = tuple(float(value) for value in rows[0]["embedding"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise EmbeddingIdentityUnavailable(
            "端点返回体不是 OpenAI 兼容的嵌入响应"
        ) from exc
    if not vector or any(not math.isfinite(value) for value in vector):
        raise EmbeddingIdentityUnavailable("端点返回的向量为空或含非有限值")
    return vector


class EmbeddingIdentityUnavailable(RuntimeError):
    """One arm could not produce a measurement (never a verdict)."""


def _embed(
    embedder: Callable[..., tuple[float, ...]] | None,
    base_url: str,
    text: str,
    *,
    api_key: str,
    model: str,
    timeout: float,
) -> tuple[float, ...]:
    caller = embedder or _post_embeddings
    return caller(base_url, text, api_key=api_key, model=model, timeout=timeout)


def _recorded_base_url() -> str:
    """The address the embedding bundle records (the serving fallback)."""

    from src.data_agents.company.vectorizer import EmbeddingClient

    return EmbeddingClient().base_url


def _pack_dir(pack_dir: Path | None) -> Path | None:
    if pack_dir is not None:
        return pack_dir
    value = os.environ.get(_SERVING_PACK_ENV, "").strip()
    return Path(value) if value else None


def _index_assets(pack_dir: Path | None) -> tuple[Path, Path]:
    """(lookup database, vector matrix) of the mounted serving pack.

    The index root comes from the pack's own index-target marker — the same file
    the serving mount reads — so the probe cannot be pointed at a second index.
    """

    root = _pack_dir(pack_dir)
    if root is None:
        raise EmbeddingIdentityUnavailable(
            f"未配置服务包目录（{_SERVING_PACK_ENV}），无法做索引比对"
        )
    marker = root / _INDEX_MARKER_FILENAME
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
        index_root = Path(str(document["root"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EmbeddingIdentityUnavailable(
            f"服务包索引标记不可读（{marker.name}）"
        ) from exc
    lookup = root / _LOOKUP_FILENAME
    matrix = index_root / _MATRIX_FILENAME
    if not lookup.is_file() or not matrix.is_file():
        raise EmbeddingIdentityUnavailable(
            "服务包缺少 lookup.sqlite3 或 vector_matrix.npz"
        )
    return lookup, matrix


def _probe_document(lookup_path: Path) -> tuple[str, str]:
    """(point id, verbatim embedded content) of one deterministic index document."""

    query = (
        "SELECT point_id, json_extract(point_json, '$.embedded_content') AS content"
        " FROM index_point"
        " WHERE content IS NOT NULL"
        " AND length(content) BETWEEN 200 AND 1200"
        " ORDER BY point_id LIMIT 1"
    )
    try:
        with sqlite3.connect(f"file:{lookup_path}?mode=ro", uri=True) as connection:
            row = connection.execute(query).fetchone()
    except sqlite3.Error as exc:
        raise EmbeddingIdentityUnavailable("索引点表不可读") from exc
    if row is None or not str(row[0]).strip() or not str(row[1]).strip():
        raise EmbeddingIdentityUnavailable("索引里没有可用于比对的文档")
    return str(row[0]), str(row[1])


def _matrix_reader(path: Path) -> tuple[tuple[str, ...], Any]:
    """(point ids, row reader) without materializing the 1.7GB matrix.

    ``vector_matrix.npz`` members are uncompressed, so a row can be read by
    seeking to its offset in ``matrix.npy`` — the same numbers the serving
    process scores against, at a bounded cost per click.
    """

    import numpy as np
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open(_POINT_IDS_MEMBER) as handle:
                point_ids = tuple(
                    str(value) for value in np.load(handle, allow_pickle=True).tolist()
                )
            with archive.open(_MATRIX_MEMBER) as handle:
                shape, dtype, _offset = _read_matrix_header(handle)
    except EmbeddingIdentityUnavailable:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        raise EmbeddingIdentityUnavailable("持久化向量矩阵不可读") from exc
    if len(shape) != 2 or len(point_ids) != shape[0]:
        raise EmbeddingIdentityUnavailable("持久化向量矩阵与索引点表不一致")
    row_bytes = dtype.itemsize * shape[1]

    def read_row(index: int) -> Any:
        if index < 0 or index >= shape[0]:
            raise EmbeddingIdentityUnavailable("持久化向量矩阵行号越界")
        with zipfile.ZipFile(path) as archive:
            with archive.open(_MATRIX_MEMBER) as handle:
                _shape, _dtype, offset = _read_matrix_header(handle)
                # The member stream starts at the .npy magic; the array body
                # starts after the header, so the row offset is header + i*row.
                handle.seek(offset + row_bytes * index)
                return np.frombuffer(handle.read(row_bytes), dtype=dtype)

    return point_ids, read_row


def _index_arm(
    *,
    configured_base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    embedder: Callable[..., tuple[float, ...]] | None,
    pack_dir: Path | None,
) -> EmbeddingIdentityReport:
    lookup_path, matrix_path = _index_assets(pack_dir)
    point_id, content = _probe_document(lookup_path)
    point_ids, read_row = _matrix_reader(matrix_path)
    if point_id not in point_ids:
        raise EmbeddingIdentityUnavailable("比对文档不在持久化向量矩阵里")
    target_index = point_ids.index(point_id)

    vector = _embed(
        embedder,
        configured_base_url,
        content,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    if len(vector) != len(read_row(target_index)):
        raise EmbeddingIdentityUnavailable("端点向量维度与索引矩阵不一致")

    target_row = read_row(target_index)
    cosine = _cosine(vector, tuple(float(value) for value in target_row))
    sample_rows = 0
    sample_max = cosine
    for index in range(0, len(point_ids), INDEX_SAMPLE_STRIDE):
        if index == target_index:
            continue
        sample_rows += 1
        sample_max = max(
            sample_max,
            _cosine(vector, tuple(float(value) for value in read_row(index))),
        )
    checks = {
        "point_id": point_id,
        "dimension": len(vector),
        "sample_rows": sample_rows,
        "sample_max_cosine": round(sample_max, 6),
        "document_chars": len(content),
    }
    if cosine < INDEX_COSINE_FLOOR:
        return EmbeddingIdentityReport(
            arm="index",
            passed=False,
            cosine=round(cosine, 6),
            threshold=INDEX_COSINE_FLOOR,
            checks=checks,
            detail=(
                "该端点与索引不在同一嵌入空间（索引文档自比 cos="
                f"{cosine:.4f} < {INDEX_COSINE_FLOOR}）：不要切换到这个端点，"
                "请换回与索引同源的模型，或重建向量后再说"
            ),
        )
    if sample_max > cosine + 1e-6:
        return EmbeddingIdentityReport(
            arm="index",
            passed=False,
            cosine=round(cosine, 6),
            threshold=INDEX_COSINE_FLOOR,
            checks=checks,
            detail=(
                "索引文档不是自己的最近邻（最高 cos="
                f"{sample_max:.4f}，本文档 {cosine:.4f}）：该端点的空间与索引不一致，"
                "不要切换"
            ),
        )
    return EmbeddingIdentityReport(
        arm="index",
        passed=True,
        cosine=round(cosine, 6),
        threshold=INDEX_COSINE_FLOOR,
        checks=checks,
        detail=(
            f"与索引同源：索引文档自比 cos={cosine:.4f}（阈值 {INDEX_COSINE_FLOOR}，"
            f"抽样 {sample_rows} 行最近邻亦为本文档）"
        ),
    )


def _reference_arm(
    *,
    configured_base_url: str,
    recorded_base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    embedder: Callable[..., tuple[float, ...]] | None,
) -> EmbeddingIdentityReport:
    reference = _embed(
        embedder,
        recorded_base_url,
        PROBE_TEXT,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    configured = _embed(
        embedder,
        configured_base_url,
        PROBE_TEXT,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    if len(reference) != len(configured):
        raise EmbeddingIdentityUnavailable(
            f"两个端点的向量维度不同（{len(reference)} vs {len(configured)}）"
        )
    cosine = _cosine(reference, configured)
    checks = {
        "reference_base_url": recorded_base_url,
        "dimension": len(configured),
    }
    if cosine < REFERENCE_COSINE_FLOOR:
        return EmbeddingIdentityReport(
            arm="reference",
            passed=False,
            cosine=round(cosine, 6),
            threshold=REFERENCE_COSINE_FLOOR,
            checks=checks,
            detail=(
                "该端点与索引记录的端点不在同一嵌入空间（固定探针 cos="
                f"{cosine:.4f} < {REFERENCE_COSINE_FLOOR}）：不要切换到这个端点，"
                "换来的排序会整体失真"
            ),
        )
    return EmbeddingIdentityReport(
        arm="reference",
        passed=True,
        cosine=round(cosine, 6),
        threshold=REFERENCE_COSINE_FLOOR,
        checks=checks,
        detail=(
            f"与索引记录的端点同源：固定探针 cos={cosine:.4f}"
            f"（阈值 {REFERENCE_COSINE_FLOOR}）"
        ),
    )


def verify_embedding_identity(
    *,
    configured_base_url: str | None,
    api_key: str = "",
    model: str | None = None,
    recorded_base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    embedder: Callable[..., tuple[float, ...]] | None = None,
    pack_dir: Path | None = None,
) -> EmbeddingIdentityReport:
    """Which arm can run, and does the configured endpoint pass it?

    Never raises: an arm that cannot be measured yields ``passed=None`` with the
    reason, so a connection test can always report something actionable.
    """

    if not configured_base_url:
        return EmbeddingIdentityReport(
            arm=None,
            passed=None,
            cosine=None,
            detail="端点未配置：无法做向量身份校验",
        )
    from src.data_agents.company.vectorizer import _DEFAULT_MODEL

    selected_model = (model or "").strip() or _DEFAULT_MODEL
    try:
        recorded = (recorded_base_url or _recorded_base_url()).rstrip("/")
    except Exception:  # noqa: BLE001 - resolution must not break the test
        recorded = ""
    configured = configured_base_url.rstrip("/")
    started = time.monotonic()
    reference_error: str | None = None
    if recorded and recorded != configured:
        try:
            report = _reference_arm(
                configured_base_url=configured,
                recorded_base_url=recorded,
                api_key=api_key,
                model=selected_model,
                timeout=timeout,
                embedder=embedder,
            )
        except EmbeddingIdentityUnavailable as exc:
            reference_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            reference_error = f"{type(exc).__name__}"
        else:
            return _with_latency(report, started)
    try:
        report = _index_arm(
            configured_base_url=configured,
            api_key=api_key,
            model=selected_model,
            timeout=timeout,
            embedder=embedder,
            pack_dir=pack_dir,
        )
    except EmbeddingIdentityUnavailable as exc:
        reason = str(exc)
        detail = (
            f"未校验：{reason}"
            if reference_error is None
            else f"未校验：记录端点不可用（{reference_error}）且 {reason}"
        )
        return EmbeddingIdentityReport(
            arm=None,
            passed=None,
            cosine=None,
            detail=detail,
            checks={"reference_error": reference_error},
        )
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return EmbeddingIdentityReport(
            arm=None,
            passed=None,
            cosine=None,
            detail=f"未校验：索引比对失败（{type(exc).__name__}）",
        )
    return _with_latency(report, started)


def _with_latency(
    report: EmbeddingIdentityReport, started: float
) -> EmbeddingIdentityReport:
    checks = dict(report.checks)
    checks["latency_ms"] = int((time.monotonic() - started) * 1000)
    return EmbeddingIdentityReport(
        arm=report.arm,
        passed=report.passed,
        cosine=report.cosine,
        detail=report.detail,
        threshold=report.threshold,
        checks=checks,
    )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "INDEX_COSINE_FLOOR",
    "INDEX_SAMPLE_STRIDE",
    "PROBE_TEXT",
    "REFERENCE_COSINE_FLOOR",
    "EmbeddingIdentityReport",
    "EmbeddingIdentityUnavailable",
    "verify_embedding_identity",
]
