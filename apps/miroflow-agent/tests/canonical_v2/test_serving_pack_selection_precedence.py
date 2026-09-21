"""包选择优先级：`--serving-pack`（CLI）赢过 `CANONICAL_V2_SERVING_PACK`（受管预置）。

事实（**交付代码**，`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`
237-246，镜像内同文件同逻辑）：

```python
serving_pack = namespace.serving_pack                 # --serving-pack
if serving_pack is None:
    environment_pack = os.environ.get("CANONICAL_V2_SERVING_PACK", "").strip()
    if environment_pack:
        ...
        serving_pack = environment_path
```

⇒ 受管设置 `paths.serving_pack_dir`（→ 这个环境变量）**只对没有 CLI 参数的进程**有意义；
而交付的冻结命令文件结尾永远是 `--serve --serve-existing --serving-pack <包名>`
（`deploy/docker/serve-command-v11.sh` / 其覆盖件），容器里跑的服务进程命令行也确认带着它。
⇒ 预置里的包路径**改不了服务加载哪个包**（只可能让"没有 runtime manifest 的页面/探针"显示错目录）。

这条测试用**真的参数解析器**钉住该优先级（把 CLI 与 env 指到两个不同的包）：
谁把优先级改了、或谁把 CLI 参数从交付命令里去掉，这里都会红。
"""

from __future__ import annotations

import importlib.util
import sys
import os
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNNER = Path(
    os.environ.get(
        "MIROTHINKER_TEST_RUNNER_PATH",
        str(
            _REPO_ROOT
            / ".agents"
            / "runs"
            / "rebuild-canonical-v2-knowledge-platform"
            / "s12a"
            / "complete_candidate_runner.py"
        ),
    )
)
_SERVING_PACK_ENV = "CANONICAL_V2_SERVING_PACK"
_CLI_PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run16-v11"
_ENV_PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound"
_SHA = "a" * 64


def _runner() -> ModuleType:
    if not _RUNNER.is_file():
        pytest.skip(f"冻结的 runner 不在这个 checkout 里：{_RUNNER}")
    name = "_frozen_candidate_runner"
    spec = importlib.util.spec_from_file_location(name, _RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses 在解析字符串注解时会查 sys.modules[cls.__module__]，先登记再执行。
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _argv(tmp_path: Path, *, serving_pack: str | None) -> list[str]:
    """A valid runner argv (fake identities, real shapes) with an optional --serving-pack."""

    release_id = "candidate-v2-precedence-r1"
    gate = tmp_path / "gate"
    envelope = gate / "s12a" / "complete-candidate-build-envelope.json"
    envelope.parent.mkdir(parents=True, exist_ok=True)
    envelope.write_text("{}", encoding="utf-8")
    staging = tmp_path / "staging"
    index = tmp_path / "index"
    for directory in (staging, index):
        directory.mkdir()
    files: dict[str, Path] = {}
    for name in (
        "source-manifest.json",
        "decision-bundle.json",
        "embedding-bundle.json",
        "serving-bundle.json",
        "milvus.db",
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        files[name] = path

    argv = [
        "--database-url",
        "postgresql://runner@127.0.0.1:1/fake",
        "--expected-database",
        "miroflow_" + release_id.replace("-", "_"),
        "--database-target-kind",
        "disposable",
        "--accepted-backup-gate-root",
        str(gate),
        "--source-manifest",
        str(files["source-manifest.json"]),
        "--source-manifest-sha256",
        _SHA,
        "--candidate-staging-root",
        str(staging),
        "--index-root",
        str(index),
        "--index-marker-sha256",
        _SHA,
        "--candidate-release-id",
        release_id,
        "--run-id",
        "run-precedence",
        "--source-batch-id",
        "batch-1",
        "--parser-version",
        "parser=v1",
        "--policy-version",
        "policy=v1",
        "--model-version",
        "embedding=whatever",
        "--recorded-decision-bundle",
        str(files["decision-bundle.json"]),
        "--recorded-embedding-bundle",
        str(files["embedding-bundle.json"]),
        "--recorded-serving-bundle",
        str(files["serving-bundle.json"]),
        "--recorded-serving-bundle-sha256",
        _SHA,
        "--envelope-output",
        str(envelope),
        "--accepted-original-milvus-path",
        str(files["milvus.db"]),
        "--accepted-original-milvus-sha256",
        _SHA,
        "--accepted-original-milvus-record-sha256",
        _SHA,
        "--serve",
        "--serve-existing",
    ]
    if serving_pack is not None:
        argv += ["--serving-pack", serving_pack]
    return argv


def test_cli_pack_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """交付的冻结命令永远带 `--serving-pack` ⇒ 预置里的包路径改不了它加载哪个包。"""

    monkeypatch.setenv(_SERVING_PACK_ENV, _ENV_PACK)
    config = _runner()._parse_args(_argv(tmp_path, serving_pack=_CLI_PACK))

    assert config.serving_pack == Path(_CLI_PACK), (
        "CLI --serving-pack 不再优先：受管预置（CANONICAL_V2_SERVING_PACK）可能把服务指到别的包"
    )


def test_environment_still_names_the_pack_when_the_cli_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """没有 CLI 参数时（独立探针/无 runtime manifest 的页面）环境变量照旧生效。"""

    monkeypatch.setenv(_SERVING_PACK_ENV, _ENV_PACK)
    config = _runner()._parse_args(_argv(tmp_path, serving_pack=None))

    assert config.serving_pack == Path(_ENV_PACK)


def test_no_pack_is_not_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两个都没有 ⇒ 不猜（由后续逻辑决定是报错还是走构建信封）。"""

    monkeypatch.delenv(_SERVING_PACK_ENV, raising=False)
    config = _runner()._parse_args(_argv(tmp_path, serving_pack=None))

    assert config.serving_pack is None
    assert os.environ.get(_SERVING_PACK_ENV) is None
