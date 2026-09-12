"""AQ-S7 pre-implementation probe — entity name-form index on the sealed pack.

Question (slice AQ-S7, change-log 2026-09-12): a question-style entity query
(大疆创新主要做什么) hits zero local lanes because exact requires the whole
normalized query to equal a display term. The prototype (main context) built
a name-form index over the 7,089 company names (legal-suffix + city-prefix
stripped, >=2 chars, 45,219 forms) and resolved the five anchor queries.

This probe measures the CANDIDATE production design on the sealed run14 pack
BEFORE any production code lands:

  * which name values each domain contributes (company name/aliases,
    professor name/canonical_name_zh/aliases, paper title/title_zh,
    patent title/title_en) — identifiers never enter;
  * form derivation: full + legal-suffix-stripped + city-prefix-stripped +
    both (company only; other domains keep full name forms), >=2 chars,
    normalized with knowledge_read_isolated._normalize, spaces stripped;
  * build wall time and tracemalloc peak for the index build;
  * form census: total, per-domain, length histogram, multi-entity forms,
    2-char forms, collisions with the category stop vocabulary / city names
    / a small common-word watch list;
  * matcher: longest-form-first containment with overlap-span dedupe,
    per-query wall time on the anchors;
  * anchor resolution: the five prototype anchors plus category queries
    (must produce NO link) plus generic-word queries when the pack carries
    such forms.

Offline: no network, no LLM, no serving inputs; Milvus Lite is opened on a
WAL-consistent byte copy (18188 holds the live lock) exactly as in
aq_s2d_window_probe.py. Writes only this directory's JSON output.
"""

from __future__ import annotations

import faulthandler
import json
import sys
import time
import tracemalloc
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

warnings.filterwarnings("ignore")
faulthandler.dump_traceback_later(300, repeat=True)


def _mark(stage: str) -> None:
    print(f"[probe] {stage}", flush=True)


from src.data_agents.canonical_v2 import index_projection_isolated as ipi  # noqa: E402
from src.data_agents.canonical_v2 import knowledge_read_isolated as iso  # noqa: E402
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402

_orig_open_milvus_client = ipi._open_milvus_client
_milvus_copies: dict[str, Path] = {}


def _open_milvus_copy(path: Path) -> object:
    import sqlite3

    source_path = str(Path(path))
    if source_path not in _milvus_copies:
        scratch_dir = Path("/var/tmp/s7-probe-index") / Path(path).parent.name
        scratch_dir.mkdir(parents=True, exist_ok=True)
        target = scratch_dir / Path(path).name
        import sqlite3 as _sqlite3

        source = _sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        dest = _sqlite3.connect(target)
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
        _milvus_copies[source_path] = target
    return _orig_open_milvus_client(_milvus_copies[source_path])


ipi._open_milvus_client = _open_milvus_copy

PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed")
RELEASE_ID = "candidate-v2-20260819-r1"
INDEX_MARKER_SHA = (
    "8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
)
OUT = Path(__file__).with_name("aq-s7-name-index-probe.json")

# --- candidate production design (ported verbatim into production later) ---

_LEGAL_SUFFIXES = ("有限责任公司", "股份有限公司", "有限公司", "公司")
# Mirror of knowledge_serving_isolated._CITY_NAMES (read cannot import
# serving); the serving-suite pin test asserts the roots stay aligned.
_CITY_ROOTS = (
    "北京", "上海", "天津", "重庆", "深圳", "广州", "杭州", "南京",
    "苏州", "成都", "武汉", "西安", "长沙", "郑州", "青岛", "宁波",
    "厦门", "福州", "济南", "合肥", "南昌", "昆明", "贵阳", "南宁",
    "海口", "石家庄", "太原", "沈阳", "长春", "哈尔滨", "呼和浩特",
    "兰州", "西宁", "银川", "乌鲁木齐", "香港", "澳门",
)
_CITY_PREFIXES = tuple(
    sorted(
        {
            *(root for root in _CITY_ROOTS),
            *(
                f"{root}市"
                for root in _CITY_ROOTS
                if root not in ("香港", "澳门")
            ),
        },
        key=lambda value: (-len(value), value),
    )
)


def _strip_legal_suffix(form: str) -> str:
    for suffix in _LEGAL_SUFFIXES:
        if form.endswith(suffix) and len(form) > len(suffix):
            return form[: -len(suffix)]
    return form


def _strip_city_prefix(form: str) -> str:
    for prefix in _CITY_PREFIXES:
        if form.startswith(prefix) and len(form) > len(prefix):
            return form[len(prefix) :]
    return form


def _name_values(entry) -> tuple[str, ...]:
    """Per-domain name fields (brief AQ-S7); identifiers never enter."""
    projection = iso._validated_public_projection(entry.document)
    if entry.document.domain == "company":
        return (projection.name, *projection.aliases)
    if entry.document.domain == "professor":
        return (
            projection.name,
            projection.canonical_name_zh,
            *projection.aliases,
        )
    if entry.document.domain == "paper":
        return (projection.title, projection.title_zh)
    if entry.document.domain == "patent":
        return (projection.title, projection.title_en)
    return ()


def _forms_for_entry(entry) -> frozenset[str]:
    forms: set[str] = set()
    for value in _name_values(entry):
        if not value:
            continue
        normalized = iso._normalize(value).replace(" ", "")
        if len(normalized) < 2:
            continue
        forms.add(normalized)
        if entry.document.domain != "company":
            continue
        stem = _strip_legal_suffix(normalized)
        forms.add(stem)
        for variant in {normalized, stem}:
            city_stripped = _strip_city_prefix(variant)
            if len(city_stripped) >= 2:
                forms.add(city_stripped)
    return frozenset(form for form in forms if len(form) >= 2)


class _Index:
    def __init__(self, targets: dict[str, tuple[int, ...]]) -> None:
        self.targets = targets
        self.forms_longest_first = tuple(
            sorted(targets, key=lambda form: (-len(form), form))
        )


def _build_index(entries) -> _Index:
    targets: dict[str, list[int]] = {}
    for position, entry in enumerate(entries):
        for form in _forms_for_entry(entry):
            targets.setdefault(form, []).append(position)
    return _Index({form: tuple(indexes) for form, indexes in targets.items()})


def _match(index: _Index, query_text: str, cap: int = 8) -> tuple[tuple[str, int], ...]:
    needle = iso._normalize(query_text).replace(" ", "")
    if len(needle) < 2:
        return ()
    accepted: list[tuple[int, int, str]] = []
    for form in index.forms_longest_first:
        start = needle.find(form)
        if start < 0:
            continue
        end = start + len(form)
        if any(start < kept_end and kept_start < end for kept_start, kept_end, _ in accepted):
            continue
        accepted.append((start, end, form))
    linked: list[int] = []
    for _start, _end, form in sorted(accepted):
        for position in index.targets[form]:
            if position not in linked:
                linked.append(position)
    return tuple((form, position) for _s, _e, form in sorted(accepted) for position in index.targets[form])[:cap]


ANCHORS = (
    ("大疆创新主要做什么", ("深圳市大疆创新科技有限公司",)),
    ("优必选科技怎么样", ("深圳市优必选科技股份有限公司",)),
    ("深南电路的主要产品", ("深南电路股份有限公司",)),
    ("开普勒机器人 怎么样", ("上海开普勒机器人有限公司",)),
    ("普渡科技有哪些产品", ("普渡",)),  # expect 2 candidates, ambiguity's job
)
CATEGORY_QUERIES = (
    "深圳有哪些做激光雷达的公司",
    "我想找PCB打板， 有哪些推荐",
    "中国有哪些成熟的酒店送餐机器人供应商",
)
COMMON_WORD_WATCH = (
    "机器人", "科技", "电子", "智能", "发展", "集团", "国际", "投资",
    "实业", "控股", "长城", "平安", "时代", "未来", "先锋", "世纪",
    "天下", "中国", "深圳", "创新", "精工", "制造", "工业", "技术",
)


def main() -> None:
    _mark("open authority start")
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=PACK_DIR,
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=INDEX_MARKER_SHA,
        expected_forbidden_milvus_path=Path(
            "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
        ),
    )
    _mark("authority open")
    started = time.monotonic()
    view = iso._create_audited_lookup_view(authority.release_bundle)
    view_build_s = time.monotonic() - started
    entries = view.public_entries
    _mark(f"view built: {len(entries)} entries in {view_build_s:.2f}s")

    tracemalloc.start()
    started = time.monotonic()
    index = _build_index(entries)
    build_s = time.monotonic() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _mark(f"index built: {len(index.targets)} forms in {build_s:.2f}s, peak {peak/1e6:.1f}MB")

    domain_of = {position: entry.document.domain for position, entry in enumerate(entries)}
    per_domain: dict[str, int] = {}
    for entry in entries:
        per_domain[entry.document.domain] = per_domain.get(entry.document.domain, 0) + 1
    length_hist: dict[int, int] = {}
    for form in index.targets:
        length_hist[len(form)] = length_hist.get(len(form), 0) + 1
    multi = {form: ix for form, ix in index.targets.items() if len(ix) > 1}
    two_char = sorted(form for form in index.targets if len(form) == 2)
    stop_hits = sorted(
        form for form in index.targets if form in iso._CATEGORY_RECALL_STOP_PHRASES
    )
    city_hits = sorted(form for form in index.targets if form in _CITY_ROOTS)
    watch_hits = {
        word: len(index.targets[word]) for word in COMMON_WORD_WATCH if word in index.targets
    }

    anchor_rows = []
    for query, expected in ANCHORS:
        started = time.monotonic()
        hits = _match(index, query)
        match_ms = (time.monotonic() - started) * 1000
        names = [
            f"{form} -> {entries[position].display_name}({domain_of[position]})"
            for form, position in hits
        ]
        anchor_rows.append(
            {"query": query, "expected_hint": list(expected), "ms": round(match_ms, 2), "hits": names}
        )
    category_rows = []
    for query in CATEGORY_QUERIES:
        hits = _match(index, query)
        category_rows.append(
            {
                "query": query,
                "hits": [
                    f"{form} -> {entries[position].display_name}" for form, position in hits
                ],
            }
        )
    two_char_samples = []
    for form in two_char:
        for position in index.targets[form]:
            two_char_samples.append(f"{form} -> {entries[position].display_name}")

    report = {
        "pack": str(PACK_DIR),
        "view_entries": len(entries),
        "view_build_seconds": round(view_build_s, 3),
        "per_domain_entries": per_domain,
        "index": {
            "forms": len(index.targets),
            "build_seconds": round(build_s, 3),
            "tracemalloc_peak_mb": round(peak / 1e6, 1),
            "length_histogram": {str(k): length_hist[k] for k in sorted(length_hist)},
            "multi_entity_forms": len(multi),
            "multi_entity_samples": {
                form: [entries[p].display_name for p in ix]
                for form, ix in sorted(multi.items())[:15]
            },
            "two_char_form_count": len(two_char),
            "two_char_form_samples": two_char_samples[:40],
            "stop_phrase_collisions": stop_hits,
            "city_name_collisions": city_hits,
            "common_word_watch_hits": watch_hits,
        },
        "anchors": anchor_rows,
        "category_queries": category_rows,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    _mark(f"wrote {OUT.name}")
    print(json.dumps(report["index"], ensure_ascii=False, indent=1))
    for row in anchor_rows:
        print("ANCHOR", row["query"], row["ms"], "ms")
        for hit in row["hits"]:
            print("   ", hit)
    for row in category_rows:
        print("CATEGORY", row["query"], "hits:", row["hits"])


if __name__ == "__main__":
    main()
