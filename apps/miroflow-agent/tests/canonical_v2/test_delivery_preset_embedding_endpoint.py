"""交付预置不许把 v1 时代的嵌入端点/模型钉在服务路线上。

背景（2026-09-22 复核，带行号）：

* 受管字段 → 环境变量：``managed_config._FIELD_ENV_VARS`` 里
  ``extraction_endpoints.embedding_base_url → CANONICAL_V2_EMBEDDING_BASE_URL``、
  ``extraction_endpoints.embedding_model → CANONICAL_V2_EMBEDDING_MODEL``；
  启动时由 ``managed_runtime.apply_managed_runtime_config`` 投影（env > file）。
* **地址那条会被消费**：候选/自有两条嵌入权威的适配器构造都走
  ``knowledge_build_isolated.resolve_embedding_base_url(recorded)``（F2 的规则：
  ``override or recorded``），所以受管地址会**覆盖** bundle 记录的网关地址。
* **模型那条没有读者**：``CANONICAL_V2_EMBEDDING_MODEL`` 在整个源码里只出现在
  ``managed_config.py`` 的映射里（`grep -rn CANONICAL_V2_EMBEDDING_MODEL apps libs` 只有映射
  命中）；候选适配器的模型来自 bundle：``knowledge_build_isolated.py`` 里
  ``model_id=document["model_id"]``。⇒ 预置里的旧模型 id 只会显示在页面上，不会进请求。

所以交付预置里这两个键必须**缺席**：地址由冻结 bundle 记录（网关地址）决定，身份（模型+维度）
由发布包封印；要自建/改地址的操作者去管理页写（那时它才成为"操作者的决定"）。

出包路径：``deploy/docker/build-site-bundle.sh`` 把本文件复制成
``<交付包>/state/config-managed/settings.json``（安装器只在文件不存在时落位）。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRESET = _REPO_ROOT / "deploy" / "docker" / "site-config" / "managed-settings.json"
_PACKER = _REPO_ROOT / "deploy" / "docker" / "build-site-bundle.sh"

_ADDRESS_FIELD = "extraction_endpoints.embedding_base_url"
_MODEL_FIELD = "extraction_endpoints.embedding_model"
_ADDRESS_ENV = "CANONICAL_V2_EMBEDDING_BASE_URL"
_MODEL_ENV = "CANONICAL_V2_EMBEDDING_MODEL"

# v1.1 预置里那两个值（本轮要拿掉的就是它们）。
_V1_ADDRESS = "http://100.64.0.27:18005/v1"
_V1_MODEL = "Qwen/Qwen3-Embedding-8B"

# 候选（网关）bundle 记录的地址：embedding-model-switch-v2/qwen3.7-text-embedding-flash-
# embedding-bundle-v1.json 的 "base_url"（本分支没有那个 bundle，按值钉住）。
_CANDIDATE_RECORDED = "https://maas.qianwenaiapi.com/api/v1"


def _preset_document() -> dict:
    return json.loads(_PRESET.read_text(encoding="utf-8"))


def _store(tmp_path: Path) -> ManagedSettingsStore:
    """The preset, loaded through the real store (no live managed directory)."""

    target = tmp_path / "managed" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_PRESET.read_text(encoding="utf-8"), encoding="utf-8")
    return ManagedSettingsStore(path=target, environ={})


def _project(tmp_path: Path) -> dict[str, object]:
    target: dict[str, str] = {"HOME": str(tmp_path)}
    empty_secrets = tmp_path / "managed" / "secrets.json"
    return apply_managed_runtime_config(
        environ=target,
        settings_store=_store(tmp_path),
        secrets_store=ManagedSecretsStore(
            path=empty_secrets, environ={}, key_file_roots=()
        ),
    )


def test_the_packer_ships_this_exact_preset_file() -> None:
    """改的必须是出包脚本真正复制的那份源文件，不是某个已生成的副本。"""

    packer = _PACKER.read_text(encoding="utf-8")

    assert "site-config/managed-settings.json" in packer, (
        "build-site-bundle.sh 不再引用 site-config/managed-settings.json —— "
        "本文件不再是交付预置的源"
    )
    assert (
        "${OUT_DIR}/state/config-managed/settings.json" in packer
    ), "出包脚本没有把它落成 <交付包>/state/config-managed/settings.json"


def test_preset_omits_the_v1_embedding_address_and_model() -> None:
    endpoints = _preset_document()["extraction_endpoints"]

    assert _ADDRESS_FIELD.split(".", 1)[1] not in endpoints, (
        "预置里又出现了 embedding_base_url：它会覆盖候选 bundle 记录的网关地址"
    )
    assert _MODEL_FIELD.split(".", 1)[1] not in endpoints, (
        "预置里又出现了 embedding_model：它是 v1 时代（4096 维）的模型 id"
    )
    dumped = json.dumps(_preset_document(), ensure_ascii=False)
    assert _V1_ADDRESS not in dumped
    assert _V1_MODEL not in dumped


def test_preset_projection_leaves_the_embedding_endpoint_to_the_bundle(
    tmp_path: Path,
) -> None:
    """预置投影后：嵌入两个环境变量都不该出现；其余（采集/档位）照旧被投影。"""

    target: dict[str, str] = {"HOME": str(tmp_path)}
    receipt = apply_managed_runtime_config(
        environ=target,
        settings_store=_store(tmp_path),
        secrets_store=ManagedSecretsStore(
            path=tmp_path / "managed" / "secrets.json", environ={}, key_file_roots=()
        ),
    )

    assert _ADDRESS_ENV not in target
    assert _MODEL_ENV not in target
    assert _ADDRESS_FIELD not in receipt["settings_applied"]
    assert _MODEL_FIELD not in receipt["settings_applied"]
    # 预置该做的事照旧：采集端点的 LLM 与问答档位仍被投影（"只填 key"的前提）。
    assert target["LOCAL_LLM_BASE_URL"] == "https://api.deepseek.com"
    assert target["CHAT_LLM_PROFILE"] == "deepseekv4flash"
    assert "paths.serving_pack_dir" in receipt["settings_applied"]


def test_effective_view_reports_the_embedding_fields_as_unset(tmp_path: Path) -> None:
    """页面读到的应是"默认/未设置"，而不是"文件里写着自建端点"。"""

    settings, fields = _store(tmp_path).effective()
    by_path = {field.path: field for field in fields}

    assert settings.extraction_endpoints.embedding_base_url is None
    assert settings.extraction_endpoints.embedding_model is None
    assert by_path[_ADDRESS_FIELD].source != "file"
    assert by_path[_MODEL_FIELD].source != "file"


def test_candidate_bundle_address_wins_once_the_v2_line_is_merged(tmp_path: Path) -> None:
    """v2 合并后这条才真正生效：生效地址 == bundle 记录的网关地址。

    本分支还没有 ``knowledge_build_isolated.resolve_embedding_base_url``（F2 的
    ``override or recorded``），所以这里按"缺席即跳过"处理，并在跳过的理由里点明
    留给 v2 的那一条；合并之后它会变成真正的断言。
    """

    module = importlib.import_module(
        "src.data_agents.canonical_v2.knowledge_build_isolated"
    )
    resolve = getattr(module, "resolve_embedding_base_url", None)
    if resolve is None:
        pytest.skip(
            "v2 合并后生效：knowledge_build_isolated.resolve_embedding_base_url "
            "还不在本分支（判据见 .agents/runs/docker-embedding-slot-symmetry-20260922/03-*）"
        )

    target: dict[str, str] = {"HOME": str(tmp_path)}
    apply_managed_runtime_config(
        environ=target,
        settings_store=_store(tmp_path),
        secrets_store=ManagedSecretsStore(
            path=tmp_path / "managed" / "secrets.json", environ={}, key_file_roots=()
        ),
    )
    module.os.environ.update({key: value for key, value in target.items() if "EMBEDDING" in key})

    assert resolve(_CANDIDATE_RECORDED) == _CANDIDATE_RECORDED
