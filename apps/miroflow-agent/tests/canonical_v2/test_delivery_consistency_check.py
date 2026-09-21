"""出包自检（`check-delivery-consistency.py`）的钉子。

它守两条：

* **硬**（exit 1）：交付预置不许钉 `extraction_endpoints.embedding_base_url` / `embedding_model`
  —— 地址那条会覆盖随包 bundle 记录的地址（见 `test_delivery_preset_embedding_endpoint.py`），
  模型那条会误导页面；两者都不该由预置替操作者决定。
* **软**（只报）：文档/脚本里的嵌入端点、"维度 N"、模型 id、服务包名与**随包 bundle/清单**
  不一致时逐条列出（file:line）。它只做"同包内自洽"，不判断 v1/v2 —— 所以 v1.1 包里
  文档写 4096、bundle 也是 4096 时**不该**报（这正是它正确的表现）。

本文件用合成包把这三件事钉住：硬规则会红、不一致会报、自洽时不报。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CHECKER = _REPO_ROOT / "deploy" / "docker" / "check-delivery-consistency.py"
_PACKER = _REPO_ROOT / "deploy" / "docker" / "build-site-bundle.sh"


def _checker() -> ModuleType:
    if not _CHECKER.is_file():
        pytest.skip(f"自检脚本不在这个 checkout 里：{_CHECKER}")
    spec = importlib.util.spec_from_file_location("_delivery_consistency", _CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pack(tmp_path: Path, *, preset: dict, bundle: dict, guide: str, pack: str) -> Path:
    out = tmp_path / "bundle"
    (out / "bundles").mkdir(parents=True)
    (out / "state" / "config-managed").mkdir(parents=True)
    (out / "bundles" / "vendor-embedding-bundle-v1.json").write_text(
        json.dumps(bundle), encoding="utf-8"
    )
    (out / "state" / "config-managed" / "settings.json").write_text(
        json.dumps(preset), encoding="utf-8"
    )
    (out / "CONFIG-GUIDE.md").write_text(guide, encoding="utf-8")
    (out / "checksums.sha256").write_text(
        f"{'a' * 64}  /var/tmp/mirothinker-data-v2/{pack}/manifest.json\n",
        encoding="utf-8",
    )
    return out


_V1_BUNDLE = {
    "base_url": "http://100.64.0.27:18005/v1",
    "dimension": 4096,
    "model_id": "Qwen/Qwen3-Embedding-8B",
}
_V2_BUNDLE = {
    "base_url": "https://maas.qianwenaiapi.com/api/v1",
    "dimension": 1024,
    "model_id": "qwen3.7-text-embedding-flash",
}
_CLEAN_PRESET = {
    "schema_version": 1,
    "extraction_endpoints": {"llm_base_url": "https://api.deepseek.com"},
}


def test_packer_runs_the_checker() -> None:
    """自检必须挂在出包脚本里（不是摆在旁边没人跑）。"""

    packer = _PACKER.read_text(encoding="utf-8")

    assert "check-delivery-consistency.py" in packer


def test_preset_that_pins_the_embedding_endpoint_is_a_hard_error(
    tmp_path: Path,
) -> None:
    out = _pack(
        tmp_path,
        preset={
            "schema_version": 1,
            "extraction_endpoints": {
                "embedding_base_url": "http://100.64.0.27:18005/v1",
                "embedding_model": "Qwen/Qwen3-Embedding-8B",
            },
        },
        bundle=_V2_BUNDLE,
        guide="嵌入端点（默认 https://maas.qianwenaiapi.com/api/v1）\n",
        pack="serving-pack-fembed-v1",
    )

    result = _checker().main(["check", str(out)])

    assert result == 1, "预置钉住嵌入地址/模型时，出包必须停"


def test_docs_disagreeing_with_the_shipped_bundle_are_reported(tmp_path: Path) -> None:
    """v2 的 bundle + v1 的数字/名字 ⇒ 逐条报出来（只报不拦）。"""

    out = _pack(
        tmp_path,
        preset=_CLEAN_PRESET,
        bundle=_V2_BUNDLE,
        guide=(
            "嵌入端点是 http://100.64.0.27:18005/v1（维度 4096）\n"
            "模型 Qwen/Qwen3-Embedding-8B 由发布包冻结\n"
            "服务包 serving-pack-run16-v11 随包\n"
        ),
        pack="serving-pack-fembed-v1",
    )

    result = _checker().main(["check", str(out)])

    assert result == 0
    errors, warnings = _checker().check(out)
    text = "\n".join(message for _priority, message in warnings)
    assert not errors
    assert "100.64.0.27:18005" in text  # 端点与随包 bundle 不同
    assert "维度 4096" in text  # 维度不同
    assert "Qwen/Qwen3-Embedding-8B" in text  # 模型 id 不同
    assert "serving-pack-run16-v11" in text  # 包名不同


def test_a_self_consistent_package_reports_nothing(tmp_path: Path) -> None:
    """同包内自洽（文档写的就是随包 bundle 的值）⇒ 不报。"""

    out = _pack(
        tmp_path,
        preset=_CLEAN_PRESET,
        bundle=_V1_BUNDLE,
        guide=(
            "嵌入端点 http://100.64.0.27:18005/v1（维度 4096）\n"
            "模型 Qwen/Qwen3-Embedding-8B\n"
            "服务包 serving-pack-run16-v11\n"
        ),
        pack="serving-pack-run16-v11",
    )

    errors, warnings = _checker().check(out)

    assert errors == []
    assert warnings == []
    assert _checker().main(["check", str(out)]) == 0
