"""容器命令文件（`serve-command-*.sh`）的产线与校验：宿主草案 ≠ 容器命令文件。

背景（2026-09-22，v2 出包）：宿主的裸机切换命令草案与容器命令文件是两种东西，中间常年只有
一句"换个包名 token"的转换，**最容易漏**、后果是**容器起不来**：宿主草案里的 launcher、
`PYTHONPATH` 钉法、候选 bundle 路径、密钥取值在镜像里全都不成立。

`deploy/docker/serve-command-container.py` 的两条规则（本文件逐条锁住）：

* `check`：① 每个**运行期会读**的绝对路径必须在镜像里存在（数据面路径由挂载提供、只看挂载点；
  惰性路径只提示）；② 禁止宿主构造（`PYTHONPATH=`、`$(…)`、`*_API_KEY=`）；③ 禁止未解析的
  `__STEPn_…__`；④ identity 旗标齐全、两个 sha 是 64-hex、端口钉死 18188；
* `convert`：从宿主草案出发，只替换显式映射的路径/命令参数，identity 旗标逐字保留、占位符必须
  解析成具体值，且容器那份**嵌入 bundle 的身份必须与宿主候选一致**（构建与服务同一向量空间）。

测试全部用 `--probe-root` 指向一棵解开的假镜像树：不用 docker、不碰真镜像、无网络。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TOOL = _REPO_ROOT / "deploy" / "docker" / "serve-command-container.py"

_DATA_ROOTS = ("/var/tmp/mirothinker-data-v2", "/var/tmp/mirothinker-canonical-v2-s12f")
_LAUNCHER = (
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/serve_s12e_port.py"
)
_DECISION_BUNDLE = (
    "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/recorded-decision-bundle-v1.json"
)
_EMBEDDING_LEDGER = (
    "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/qwen-embedding-bundle-v1.json"
)
_SERVING_BUNDLE = (
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serving-bundle-run16.json"
)
_HOST_TREE = "/home/longxiang/MiroThinker/.worktrees/embedding-switch-line"
_HOST_PYTHON = "/home/longxiang/MiroThinker/.venv/bin/python"
_HOST_EMBEDDING_BUNDLE = f"{_HOST_TREE}/.agents/runs/embedding-model-switch-v2/qwen3.7-embedding-bundle-v1.json"
_HOST_SERVING_BUNDLE = f"{_HOST_TREE}/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serving-bundle-fembed.json"
_HOST_LAUNCHER = (
    f"{_HOST_TREE}/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/serve_s12e_port.py"
)

_MARKER_SHA = "b6f78a3b1e28c280860a4210bfad286ef65090e758de5b876d7f639eefaa8373"
_MANIFEST_SHA = "a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d"
_SERVING_SHA = "0a09aecde903584efb28ccc4f3851062b52891081f0b3b44e6ce5971c55115c4"
_CANDIDATE_IDENTITY = {
    "model_id": "qwen3.7-text-embedding-flash",
    "dimension": 1024,
    "provider": "dashscope-native",
    "base_url": "https://example.invalid/api/v1",
}
_V1_IDENTITY = {
    "model_id": "Qwen/Qwen3-Embedding-8B",
    "dimension": 4096,
    "provider": "openai-compatible",
    "base_url": "http://100.64.0.27:18005/v1",
}
#: 记录 serving bundle 的自述字段（运行期 `load_recorded_serving_inputs` 逐条与旗标比对）。
_SERVING_DOC = {
    "content_sha256": _SERVING_SHA,
    "release_id": "candidate-v2-20260922-r1",
    "database_name": "miroflow_candidate_v2_20260922_r1",
    "database_target_kind": "disposable",
    "index_target_id": "index:candidate-v2-20260922-r1",
    "index_root": f"{_DATA_ROOTS[0]}/index-v4-v2",
    "envelope_path": (
        "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
        "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json"
    ),
    "embedding_model_id": _CANDIDATE_IDENTITY["model_id"],
}


def _container_module() -> ModuleType:
    if not _TOOL.is_file():
        pytest.skip(f"工具不在这个 checkout 里：{_TOOL}")
    spec = importlib.util.spec_from_file_location("_serve_command_container", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _container_command() -> str:
    """一份形状正确的容器命令文件（同 v1.1 交付件）。"""

    flags = (
        "18188 "
        "--candidate-release-id candidate-v2-20260922-r1 "
        "--run-id fembed-build-20260922-v1 "
        f"--index-root {_DATA_ROOTS[0]}/index-v4-v2 "
        f"--index-marker-sha256 {_MARKER_SHA} "
        f"--source-manifest-sha256 {_MANIFEST_SHA} "
        f"--recorded-decision-bundle {_DECISION_BUNDLE} "
        f"--recorded-embedding-bundle {_EMBEDDING_LEDGER} "
        f"--recorded-serving-bundle {_SERVING_BUNDLE} "
        f"--recorded-serving-bundle-sha256 {_SERVING_SHA} "
        "--expected-database miroflow_candidate_v2_20260922_r1 "
        f"--serving-pack {_DATA_ROOTS[0]}/serving-pack-fembed-v1 "
        "--serve --serve-existing"
    )
    env = (
        f"CANONICAL_V2_ACCESS_LOG_DB={_DATA_ROOTS[1]}/access-logs.sqlite3 "
        f"CANONICAL_V2_CORRECTIONS_DB={_DATA_ROOTS[1]}/corrections.sqlite3 "
        f"CANONICAL_V2_MANUAL_RECALL_DIR={_DATA_ROOTS[0]}/manual-recall-v1 "
        "CHAT_CONTEXTUAL_INTERPRETATION=on "
    )
    return env + "uv run python " + _LAUNCHER + " " + flags + "\n"


def _host_draft(embedding_bundle: str = _HOST_EMBEDDING_BUNDLE) -> str:
    """宿主（裸机）草案的形状：宿主 launcher/python、PYTHONPATH、密钥取值、占位符。"""

    flags = (
        "18188 "
        "--candidate-release-id candidate-v2-20260922-r1 "
        "--run-id fembed-build-20260922-v1 "
        f"--index-root {_DATA_ROOTS[0]}/index-v4-v2 "
        "--index-marker-sha256 __STEP7_INDEX_MARKER_SHA256__ "
        f"--source-manifest-sha256 {_MANIFEST_SHA} "
        f"--recorded-decision-bundle {_DECISION_BUNDLE} "
        f"--recorded-embedding-bundle {embedding_bundle} "
        f"--recorded-serving-bundle {_HOST_SERVING_BUNDLE} "
        "--recorded-serving-bundle-sha256 __STEP10_SERVING_BUNDLE_SHA256__ "
        "--expected-database miroflow_candidate_v2_20260922_r1 "
        f"--serving-pack {_DATA_ROOTS[0]}/serving-pack-fembed-v1 "
        "--serve --serve-existing"
    )
    env = (
        f"CANONICAL_V2_ACCESS_LOG_DB={_DATA_ROOTS[1]}/access-logs.sqlite3 "
        'CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)" '
        f"PYTHONPATH={_HOST_TREE}/apps/miroflow-agent "
    )
    return env + f"{_HOST_PYTHON} {_HOST_LAUNCHER} " + flags + "\n"


def _image_tree(
    root: Path,
    *,
    skip: tuple[str, ...] = (),
    bundle: dict | None = None,
    serving: dict | None = None,
) -> Path:
    """解开的假镜像树：两个数据面挂载点 + 运行期会读的那几个文件。"""

    for mount in _DATA_ROOTS:
        (root / mount.lstrip("/")).mkdir(parents=True, exist_ok=True)
    for path in (_LAUNCHER, _DECISION_BUNDLE, _EMBEDDING_LEDGER, _SERVING_BUNDLE):
        if path in skip:
            continue
        if path == _EMBEDDING_LEDGER and bundle is not None:
            text = json.dumps(bundle)
        elif path == _SERVING_BUNDLE and serving is not None:
            text = json.dumps(serving)
        else:
            text = "{}"
        _write(root / path.lstrip("/"), text)
    return root


def _check(capsys: pytest.CaptureFixture[str], command: Path, root: Path) -> tuple[int, str]:
    module = _container_module()
    rc = module.main(
        ["check", "--image", "probe-root", "--command", str(command), "--probe-root", str(root)]
    )
    return rc, capsys.readouterr().out


def _convert(
    capsys: pytest.CaptureFixture[str],
    *,
    host_command: Path,
    out: Path,
    root: Path,
    mapping: list[str],
    host_bundle: Path | None = None,
) -> tuple[int, str]:
    module = _container_module()
    argv = [
        "convert",
        "--host-command", str(host_command),
        "--image", "probe-root",
        "--out", str(out),
        "--probe-root", str(root),
    ]
    for item in mapping:
        argv += ["--map", item]
    if host_bundle is not None:
        argv += ["--host-embedding-bundle", str(host_bundle)]
    return module.main(argv), capsys.readouterr().out


def test_a_fake_path_is_red(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """launcher 不在（宿主路径原样进容器）⇒ 判红，并指名道姓。"""

    root = _image_tree(tmp_path / "root", skip=(_LAUNCHER,))
    command = _write(tmp_path / "serve-command.sh", _container_command())

    rc, out = _check(capsys, command, root)

    assert rc == 1
    assert f"镜像内不存在（运行期会读）：{_LAUNCHER}" in out


def test_a_fully_present_tree_is_green(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """运行期会读的 4 个镜像内路径都在 ⇒ 绿；数据面只提供挂载点（挂载点之外不要求存在）。"""

    root = _image_tree(tmp_path / "root", serving=_SERVING_DOC)
    command = _write(tmp_path / "serve-command.sh", _container_command())

    rc, out = _check(capsys, command, root)

    assert rc == 0
    assert "[OK]   运行期会读的镜像内路径 4 个（缺 0）" in out
    assert "记录的 serving bundle 与 identity 旗标自洽" in out
    assert not (root / f"{_DATA_ROOTS[0]}/serving-pack-fembed-v1".lstrip("/")).exists()


def test_a_missing_data_plane_mount_point_is_red(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """数据面文件可以不在（由挂载提供），但挂载点必须在镜像里。"""

    root = _image_tree(tmp_path / "root")
    (root / _DATA_ROOTS[0].lstrip("/")).rmdir()
    command = _write(tmp_path / "serve-command.sh", _container_command())

    rc, out = _check(capsys, command, root)

    assert rc == 1
    assert f"数据面挂载点不存在于镜像：{_DATA_ROOTS[0]}" in out


def test_host_constructs_and_unresolved_placeholders_are_red(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """宿主草案直接当容器命令文件用：PYTHONPATH / 命令替换 / 密钥赋值 / 占位符 / 宿主路径全红。"""

    root = _image_tree(tmp_path / "root")
    command = _write(tmp_path / "serve-18188-command-fembed.DRAFT.sh", _host_draft())

    rc, out = _check(capsys, command, root)

    assert rc == 1
    assert "出现 PYTHONPATH=" in out
    assert "出现命令替换 $(…)/反引号" in out
    assert "出现密钥赋值 CANONICAL_V2_EMBEDDING_API_KEY=…" in out
    assert "未解析的占位符 __STEP7_INDEX_MARKER_SHA256__" in out
    assert f"镜像内不存在（运行期会读）：{_HOST_LAUNCHER}" in out
    assert f"镜像内不存在（运行期会读）：{_HOST_PYTHON}" in out
    # 只报名字，不复述宿主那条密钥取值（也不回显它的取值文件路径）
    assert "$(cat" not in out
    assert "/var/tmp/mirothinker-qianwen-api-key" not in out


def test_convert_keeps_identity_and_only_replaces_mapped_tokens(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """convert：identity 逐字保留、占位符解析成具体值、宿主构造消失、路径换成容器那份。"""

    root = _image_tree(tmp_path / "root", bundle=_CANDIDATE_IDENTITY, serving=_SERVING_DOC)
    host_bundle = _write(tmp_path / "qwen3.7-embedding-bundle-v1.json", json.dumps(_CANDIDATE_IDENTITY))
    draft = _write(tmp_path / "draft.sh", _host_draft(str(host_bundle)))
    out = tmp_path / "serve-command-fembed.sh"

    rc, log = _convert(
        capsys,
        host_command=draft,
        out=out,
        root=root,
        host_bundle=host_bundle,
        mapping=[
            f"{_HOST_LAUNCHER}={_LAUNCHER}",
            f"{_HOST_PYTHON}=uv run python",
            f"{host_bundle}={_EMBEDDING_LEDGER}",
            f"{_HOST_SERVING_BUNDLE}={_SERVING_BUNDLE}",
            "__STEP7_INDEX_MARKER_SHA256__=" + _MARKER_SHA,
            "__STEP10_SERVING_BUNDLE_SHA256__=" + _SERVING_SHA,
        ],
    )

    assert rc == 0, log
    assert "宿主候选 bundle 与容器账本逐字段一致" in log
    text = out.read_text(encoding="utf-8")
    for fragment in (
        "uv run python " + _LAUNCHER,
        "--candidate-release-id candidate-v2-20260922-r1",
        "--run-id fembed-build-20260922-v1",
        f"--source-manifest-sha256 {_MANIFEST_SHA}",
        f"--index-marker-sha256 {_MARKER_SHA}",
        f"--recorded-serving-bundle-sha256 {_SERVING_SHA}",
        f"--recorded-embedding-bundle {_EMBEDDING_LEDGER}",
        f"--recorded-serving-bundle {_SERVING_BUNDLE}",
    ):
        assert fragment in text
    for forbidden in ("PYTHONPATH", "API_KEY", "$(", '")"', "__STEP"):
        assert forbidden not in text


def test_convert_is_red_when_the_container_bundle_is_another_identity(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """容器那份嵌入 bundle 与宿主候选不是同一身份（= 另一个向量空间）⇒ 判红，四字段都在。"""

    root = _image_tree(tmp_path / "root", bundle=_V1_IDENTITY, serving=_SERVING_DOC)
    host_bundle = _write(tmp_path / "qwen3.7-embedding-bundle-v1.json", json.dumps(_CANDIDATE_IDENTITY))
    draft = _write(tmp_path / "draft.sh", _host_draft(str(host_bundle)))
    out = tmp_path / "serve-command-fembed.sh"

    rc, log = _convert(
        capsys,
        host_command=draft,
        out=out,
        root=root,
        host_bundle=host_bundle,
        mapping=[
            f"{_HOST_LAUNCHER}={_LAUNCHER}",
            f"{_HOST_PYTHON}=uv run python",
            f"{host_bundle}={_EMBEDDING_LEDGER}",
            f"{_HOST_SERVING_BUNDLE}={_SERVING_BUNDLE}",
            "__STEP7_INDEX_MARKER_SHA256__=" + _MARKER_SHA,
            "__STEP10_SERVING_BUNDLE_SHA256__=" + _SERVING_SHA,
        ],
    )

    assert rc == 1
    assert "宿主候选 bundle 与容器账本不是同一份内容" in log
    assert "'dimension'" in log and "'1024'" in log and "'4096'" in log
    assert "dashscope-native" in log


def test_convert_is_red_when_the_container_bundle_is_the_other_role_twin(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """同名候选 bundle 的"另一个角色"（查询侧 vs 文档侧）⇒ 判红。

    实测（2026-09-22）：同一份 `qwen3.7-…-embedding-bundle-v1.json` 在 5 棵 worktree 里有 **3 种内容**
    —— 差别不在 model/dimension/provider/base_url，而在 `query_instruct`/`query_text_type`/`batch_size`。
    只比四个身份字段会放它过去；这条锁住"逐字段比全文"。
    """

    host_doc = {**_CANDIDATE_IDENTITY, "query_text_type": "query", "query_instruct": "…", "batch_size": 20}
    container_doc = {k: v for k, v in host_doc.items() if k not in ("query_text_type", "query_instruct")}
    container_doc["batch_size"] = 32
    root = _image_tree(tmp_path / "root", bundle=container_doc, serving=_SERVING_DOC)
    host_bundle = _write(tmp_path / "qwen3.7-embedding-bundle-v1.json", json.dumps(host_doc))
    draft = _write(tmp_path / "draft.sh", _host_draft(str(host_bundle)))
    out = tmp_path / "serve-command-fembed.sh"

    rc, log = _convert(
        capsys,
        host_command=draft,
        out=out,
        root=root,
        host_bundle=host_bundle,
        mapping=[
            f"{_HOST_LAUNCHER}={_LAUNCHER}",
            f"{_HOST_PYTHON}=uv run python",
            f"{host_bundle}={_EMBEDDING_LEDGER}",
            f"{_HOST_SERVING_BUNDLE}={_SERVING_BUNDLE}",
            "__STEP7_INDEX_MARKER_SHA256__=" + _MARKER_SHA,
            "__STEP10_SERVING_BUNDLE_SHA256__=" + _SERVING_SHA,
        ],
    )

    assert rc == 1
    assert "宿主候选 bundle 与容器账本不是同一份内容" in log
    assert "'query_text_type'" in log and "'batch_size'" in log
    assert "'model_id'" not in log  # 四个身份字段是一样的：红的理由是内容不同，不是身份不同


def test_a_serving_bundle_from_another_release_is_red(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """记录 serving bundle 是另一个发布（identity 旗标一个没变也照样起不来）⇒ 判红。

    这正是最容易漏的一类：命令文件里的 identity 全是 v2 的，镜像账本却是上一版封的包
    —— 到容器里才由 `load_recorded_serving_inputs` 抛 `serving bundle release differs`。
    """

    stale = {"release_id": "candidate-v2-20260916-r1", "index_target_id": "index:candidate-v2-20260916-r1"}
    root = _image_tree(
        tmp_path / "root",
        bundle=_CANDIDATE_IDENTITY,
        serving={**_SERVING_DOC, **stale},
    )
    host_bundle = _write(tmp_path / "qwen3.7-embedding-bundle-v1.json", json.dumps(_CANDIDATE_IDENTITY))
    draft = _write(tmp_path / "draft.sh", _host_draft(str(host_bundle)))
    out = tmp_path / "serve-command-fembed.sh"

    rc, log = _convert(
        capsys,
        host_command=draft,
        out=out,
        root=root,
        host_bundle=host_bundle,
        mapping=[
            f"{_HOST_LAUNCHER}={_LAUNCHER}",
            f"{_HOST_PYTHON}=uv run python",
            f"{host_bundle}={_EMBEDDING_LEDGER}",
            f"{_HOST_SERVING_BUNDLE}={_SERVING_BUNDLE}",
            "__STEP7_INDEX_MARKER_SHA256__=" + _MARKER_SHA,
            "__STEP10_SERVING_BUNDLE_SHA256__=" + _SERVING_SHA,
        ],
    )

    assert rc == 1
    assert "--candidate-release-id 与 bundle 自述的 release_id 不符" in log
    assert "candidate-v2-20260916-r1" in log


def test_convert_is_red_when_the_candidate_bundle_is_not_mapped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """候选 bundle 没被映射到容器路径 ⇒ 红（账本模式要求 COPY 同一份内容进去）。"""

    root = _image_tree(tmp_path / "root", bundle=_CANDIDATE_IDENTITY)
    host_bundle = _write(tmp_path / "qwen3.7-embedding-bundle-v1.json", json.dumps(_CANDIDATE_IDENTITY))
    draft = _write(tmp_path / "draft.sh", _host_draft(str(host_bundle)))
    out = tmp_path / "serve-command-fembed.sh"

    rc, log = _convert(
        capsys,
        host_command=draft,
        out=out,
        root=root,
        host_bundle=host_bundle,
        mapping=[
            f"{_HOST_LAUNCHER}={_LAUNCHER}",
            f"{_HOST_PYTHON}=uv run python",
            f"{_HOST_SERVING_BUNDLE}={_SERVING_BUNDLE}",
            "__STEP7_INDEX_MARKER_SHA256__=" + _MARKER_SHA,
            "__STEP10_SERVING_BUNDLE_SHA256__=" + _SERVING_SHA,
        ],
    )

    assert rc == 1
    assert "没有被映射到容器路径" in log
