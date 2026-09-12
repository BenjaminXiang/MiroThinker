"""AQ-S7 probe v2 — guarded name-form index built from entry display_terms.

v1 findings (aq-s7-name-index-probe.json):
  * building forms by re-validating every projection costs 80s — the
    production design must derive forms from `_PublicLookupEntry.display_terms`
    (already normalized name surfaces; identifiers never enter them);
  * unguarded forms collide with category vocabulary: 机器人 x 23 entities,
    送餐机器人 x 1, plus junk-alias forms 公司/深圳 — category queries would
    link entities (g2 regression);
  * the brief's two-tier derivation (legal suffix + city prefix) does NOT
    reproduce the pinned 大疆 anchor: 深圳市大疆创新科技有限公司 yields
    大疆创新科技, never 大疆创新 — the prototype must have stripped one
    trailing industry word as a third tier (优必选 "长/短形都命中" requires
    both 优必选科技 and 优必选, i.e. iterative stripping).

v2 candidate design:
  forms per name value = {full} + {strip one legal suffix} + {then strip one
  trailing industry word} + {strip legal->industry on the city-stripped
  variants}, city prefixes stripped from every variant, >=2 chars, spaces
  stripped, normalized via knowledge_read_isolated._normalize.
  Guards at build time: a form equal to (casefolded) a packaged anchoring
  declaration term, a category-recall stop phrase, or a city root never
  enters the index; a form shared by > FANOUT entities is dropped.
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
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        dest = sqlite3.connect(target)
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
OUT = Path(__file__).with_name("aq-s7-name-index-probe-v2.json")

# --- candidate production design (ported verbatim into production later) ---

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
            *(_CITY_ROOTS),
            *(f"{root}市" for root in _CITY_ROOTS if root not in ("香港", "澳门")),
        },
        key=lambda value: (-len(value), value),
    )
)
_TRAILING_INDUSTRY_WORDS = (
    "科技", "技术", "电子", "智能", "信息", "机器人", "实业",
    "控股", "集团", "国际", "发展", "网络", "通信", "生物", "医疗", "新能源",
)
_FANOUT_CAP = 4

_CATEGORY_VOCABULARY = frozenset()  # placeholder, replaced below
PACKAGED_ANCHORING_DECLARATION_TERMS = tuple(
    term.term for term in iso.PACKAGED_ANCHORING_DECLARATION.terms
)
_CATEGORY_VOCABULARY = frozenset(
    term.casefold() for term in PACKAGED_ANCHORING_DECLARATION_TERMS
)
_STOP_PHRASES = frozenset(
    phrase.casefold() for phrase in iso._CATEGORY_RECALL_STOP_PHRASES
)
_CITY_ROOTS_FOLDED = frozenset(_CITY_ROOTS)


def _strip_one_legal_suffix(form: str) -> str:
    for suffix in iso._COMPANY_LEGAL_SUFFIXES:
        if form.endswith(suffix) and len(form) > len(suffix):
            return form[: -len(suffix)]
    return form


def _strip_one_industry_word(form: str) -> str:
    for word in _TRAILING_INDUSTRY_WORDS:
        if form.endswith(word) and len(form) > len(word):
            return form[: -len(word)]
    return form


def _strip_city_prefix(form: str) -> str:
    for prefix in _CITY_PREFIXES:
        if form.startswith(prefix) and len(form) > len(prefix):
            return form[len(prefix) :]
    return form


def _guarded(form: str) -> bool:
    return (
        len(form) >= 2
        and form not in _CATEGORY_VOCABULARY
        and form not in _STOP_PHRASES
        and form not in _CITY_ROOTS_FOLDED
    )


def _entity_name_forms(domain: str, display_terms: frozenset[str]) -> frozenset[str]:
    forms: set[str] = set()
    for term in display_terms:
        base = term.replace(" ", "")
        if len(base) < 2:
            continue
        variants = {base}
        if domain == "company":
            legal_stripped = _strip_one_legal_suffix(base)
            variants.add(legal_stripped)
            variants.add(_strip_one_industry_word(legal_stripped))
            variants.add(_strip_one_industry_word(base))
        for variant in tuple(variants):
            city_stripped = _strip_city_prefix(variant)
            if city_stripped != variant:
                variants.add(city_stripped)
        forms.update(variant for variant in variants if _guarded(variant))
    return frozenset(forms)


class _Index:
    def __init__(self, targets: dict[str, tuple[int, ...]], dropped_fanout: int) -> None:
        self.targets = targets
        self.forms_longest_first = tuple(
            sorted(targets, key=lambda form: (-len(form), form))
        )
        self.dropped_fanout = dropped_fanout


def _build_entity_name_index(entries) -> _Index:
    targets: dict[str, list[int]] = {}
    for position, entry in enumerate(entries):
        for form in _entity_name_forms(entry.document.domain, entry.display_terms):
            targets.setdefault(form, []).append(position)
    kept: dict[str, tuple[int, ...]] = {}
    dropped = 0
    for form, indexes in targets.items():
        if len(indexes) > _FANOUT_CAP:
            dropped += 1
            continue
        kept[form] = tuple(indexes)
    return _Index(kept, dropped)


def _entity_link_entry_indexes(index: _Index, query_text: str, cap: int = 8) -> tuple[int, ...]:
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
    return tuple(linked[:cap])


ANCHORS = (
    "大疆创新主要做什么",
    "优必选科技怎么样",
    "深南电路的主要产品",
    "开普勒机器人 怎么样",
    "普渡科技有哪些产品",
    "普渡有哪些产品",
)
CATEGORY_QUERIES = (
    "深圳有哪些做激光雷达的公司",
    "我想找PCB打板， 有哪些推荐",
    "中国有哪些成熟的酒店送餐机器人供应商",
    "深圳有哪些机器人公司",
    "机器人的发展前景怎么样",
    "深圳的历史",
    "公司注册流程是什么",
    "送餐机器人哪个品牌好",
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
    index = _build_entity_name_index(entries)
    build_s = time.monotonic() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _mark(
        f"index built: {len(index.targets)} forms in {build_s:.2f}s, "
        f"peak {peak/1e6:.1f}MB, fanout-dropped {index.dropped_fanout}"
    )

    per_domain_forms: dict[str, int] = {}
    form_domains: dict[str, set[str]] = {}
    for position, entry in enumerate(entries):
        domain = entry.document.domain
        for form in _entity_name_forms(domain, entry.display_terms):
            if form in index.targets:
                per_domain_forms[domain] = per_domain_forms.get(domain, 0) + 1
                form_domains.setdefault(form, set()).add(domain)
    company_forms = len(
        {form for form, domains in form_domains.items() if domains == {"company"}}
    )

    def describe(query: str) -> dict[str, object]:
        started_q = time.monotonic()
        linked = _entity_link_entry_indexes(index, query)
        ms = (time.monotonic() - started_q) * 1000
        return {
            "query": query,
            "ms": round(ms, 2),
            "hits": [
                f"{entries[p].display_name}({entries[p].document.domain})"
                for p in linked
            ],
        }

    anchors = [describe(query) for query in ANCHORS]
    categories = [describe(query) for query in CATEGORY_QUERIES]

    report = {
        "view_entries": len(entries),
        "view_build_seconds": round(view_build_s, 3),
        "index": {
            "forms": len(index.targets),
            "company_only_forms": company_forms,
            "per_domain_form_marks": per_domain_forms,
            "build_seconds": round(build_s, 3),
            "tracemalloc_peak_mb": round(peak / 1e6, 1),
            "fanout_dropped_forms": index.dropped_fanout,
            "guards": {
                "category_terms": len(PACKAGED_ANCHORING_DECLARATION_TERMS),
                "stop_phrases": len(_STOP_PHRASES),
                "city_roots": len(_CITY_ROOTS),
                "fanout_cap": _FANOUT_CAP,
            },
        },
        "anchors": anchors,
        "category_queries": categories,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    _mark(f"wrote {OUT.name}")
    print(json.dumps(report["index"], ensure_ascii=False, indent=1))
    for row in (*anchors, *categories):
        print("Q", row["query"], row["ms"], "ms ->", row["hits"])


if __name__ == "__main__":
    main()
