"""`mirothinker-verify` 的嵌入那一半：断言**站点真正在用**的身份（不是一张写死的账本）。

背景（2026-09-22）：镜像里烘着一份 v1 时代的账本（`Qwen/Qwen3-Embedding-8B` / 4096 维 /
自建地址 / OpenAI 兼容形状），而 v2 站点的嵌入是候选网关的**原生路由**
（`qwen3.7-text-embedding-flash` / 1024 维 / `dashscope-native`）。验收若照旧拿 v1 账本去打，
就会在一个**装对了**的站点上报红（"端点不可达"或"维度不符"），而甲方唯一的判断依据就是它。

`deploy/docker/verify_embedding.py` 的规则（与页面身份校验 `canonical_v2_embedding_identity.py`
同一条，不发明第二套）：

* 身份取自**站点在用的记录 bundle**（运行中服务 argv 的 `--recorded-embedding-bundle`，
  退一步取冻结命令文件里的同一参数）；地址取服务进程环境的
  `CANONICAL_V2_EMBEDDING_BASE_URL`（受管/页面覆盖）否则 bundle 记录的地址；
* 形状**问地址、不猜配置**：先讲 OpenAI 兼容形状，**只有** 404/405 才改讲 DashScope 原生形状；
* 服务包 manifest 的 `embedding_model_id` 必须等于记录 bundle 的 `model_id`（索引身份 == 嵌入权威身份）；
* 镜像里若已有身份模块/原生客户端，镜像的字面量漂移即红。

测试全部用本地假端点 + 假 bundle/命令文件/进程树：无网络、不碰真站点。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import http.server
import pytest
import threading

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PROBE = _REPO_ROOT / "deploy" / "docker" / "verify_embedding.py"

_MODEL = "fake-vendor/embedding-xyz-1024"
_OTHER_MODEL = "fake-vendor/embedding-other-256"
_DIMENSION = 5
_FAKE_KEY = "sk-fake-verify-probe-0000"


def _probe_module() -> ModuleType:
    if not _PROBE.is_file():
        pytest.skip(f"探针不在这个 checkout 里：{_PROBE}")
    spec = importlib.util.spec_from_file_location("_verify_embedding", _PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Endpoint(http.server.BaseHTTPRequestHandler):
    """Records requests; answers by route."""

    requests: list[dict[str, object]] = []
    compatible_status = 200
    native_status = 200
    dimension = _DIMENSION

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        type(self).requests.append(
            {
                "path": self.path,
                "body": body,
                "authorization_present": bool(self.headers.get("Authorization")),
            }
        )
        if self.path.endswith("/services/embeddings/text-embedding/text-embedding"):
            if type(self).native_status != 200:
                self._answer(type(self).native_status, {})
                return
            self._answer(
                200,
                {
                    "output": {
                        "embeddings": [
                            {"text_index": 0, "embedding": [0.1] * type(self).dimension}
                        ]
                    }
                },
            )
            return
        if type(self).compatible_status != 200:
            self._answer(type(self).compatible_status, {"error": {"message": "nope"}})
            return
        self._answer(
            200, {"data": [{"index": 0, "embedding": [0.2] * type(self).dimension}]}
        )

    def _answer(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture()
def endpoint() -> tuple[str, list[dict[str, object]]]:
    _Endpoint.requests = []
    _Endpoint.compatible_status = 200
    _Endpoint.native_status = 200
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Endpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1", _Endpoint.requests
    finally:
        server.shutdown()
        server.server_close()


def _site(
    tmp_path: Path,
    *,
    address: str,
    model: str = _MODEL,
    dimension: int = _DIMENSION,
    served_model: str | None = None,
) -> tuple[Path, Path]:
    """A scratch site: recorded bundle + frozen command file + served pack manifest."""

    bundle = tmp_path / "ledger" / "qwen-embedding-bundle-v1.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "canonical-v2-openai-compatible-embedding-bundle-v1",
                "provider": "dashscope-native",
                "model_id": model,
                "dimension": dimension,
                "base_url": address,
                "api_key_source": "env:CANONICAL_V2_EMBEDDING_API_KEY",
            }
        ),
        encoding="utf-8",
    )
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        json.dumps({"embedding_model_id": served_model or model}), encoding="utf-8"
    )
    cmd_file = tmp_path / "serve-command.sh"
    cmd_file.write_text(
        f"python serve.py 18188 --serve --serve-existing "
        f"--serving-pack {pack} --recorded-embedding-bundle {bundle}\n",
        encoding="utf-8",
    )
    key_file = tmp_path / "secrets" / ".sglang_api_key"
    key_file.parent.mkdir()
    key_file.write_text(_FAKE_KEY, encoding="utf-8")
    return bundle, cmd_file


def _run_probe(
    tmp_path: Path,
    *,
    cmd_file: Path,
    proc_root: Path | None = None,
    env_file: Path | None = None,
    identity_module: Path | None = None,
    native_client: Path | None = None,
) -> int:
    argv = [
        "--cmd-file",
        str(cmd_file),
        "--proc-root",
        str(proc_root or (tmp_path / "empty-proc")),
        "--identity-module",
        str(identity_module or (tmp_path / "absent-module.py")),
        "--native-client",
        str(native_client or (tmp_path / "absent-client.py")),
    ]
    if env_file is not None:
        argv += ["--environ", str(env_file)]
    argv += ["--key-file", str(tmp_path / "secrets" / ".sglang_api_key")]
    return _probe_module().main(argv)


def test_probe_follows_the_sites_own_bundle(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """期望身份来自站点在用的 bundle：模型/维度都不是 v1 值也应全通。"""

    address, recorded = endpoint
    _bundle, cmd_file = _site(tmp_path, address=address)

    assert _run_probe(tmp_path, cmd_file=cmd_file) == 0
    output = capsys.readouterr().out
    assert f"model={_MODEL}" in output
    assert f"维度 {_DIMENSION}" in output
    assert "openai-compatible" in output
    assert recorded and recorded[0]["body"]["model"] == _MODEL
    assert recorded[0]["authorization_present"] is True


def test_native_route_is_spoken_only_after_a_404(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """原生站点：兼容形状 404 ⇒ 改讲 DashScope 原生形状（角色/维度一起报）。"""

    address, recorded = endpoint
    _Endpoint.compatible_status = 404
    _bundle, cmd_file = _site(tmp_path, address=address)

    assert _run_probe(tmp_path, cmd_file=cmd_file) == 0
    output = capsys.readouterr().out
    assert "dashscope-native" in output
    assert any(
        str(request["path"]).endswith(
            "/services/embeddings/text-embedding/text-embedding"
        )
        for request in recorded
    )
    native = [
        request for request in recorded if "services/embeddings" in str(request["path"])
    ][0]
    assert native["body"]["text_type"] == "query"  # 服务线查询侧


def test_a_401_does_not_switch_the_wire_shape(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """401 是这条路线自己的回答 ⇒ 不换形状、如实报红（不是"没验证"）。"""

    address, recorded = endpoint
    _Endpoint.compatible_status = 401
    _bundle, cmd_file = _site(tmp_path, address=address)

    assert _run_probe(tmp_path, cmd_file=cmd_file) == 1
    output = capsys.readouterr().out
    assert "HTTP 401" in output
    assert not any(
        "services/embeddings" in str(request["path"]) for request in recorded
    )


def test_pack_identity_must_match_the_recorded_bundle(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """索引身份（服务包 manifest）≠ 嵌入权威身份（记录 bundle）⇒ 必须红。"""

    address, _recorded = endpoint
    _bundle, cmd_file = _site(tmp_path, address=address, served_model=_OTHER_MODEL)

    assert _run_probe(tmp_path, cmd_file=cmd_file) == 1
    output = capsys.readouterr().out
    assert "身份不一致" in output
    assert _OTHER_MODEL in output and _MODEL in output


def test_dimension_mismatch_is_red(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """维度不符（bundle 说 5，端点答 3）⇒ 红，并报出期望值。"""

    address, _recorded = endpoint
    _Endpoint.dimension = _DIMENSION - 2
    try:
        _bundle, cmd_file = _site(tmp_path, address=address)
        assert _run_probe(tmp_path, cmd_file=cmd_file) == 1
    finally:
        _Endpoint.dimension = _DIMENSION
    assert "维度不符" in capsys.readouterr().out


def test_the_service_environment_wins_over_the_bundle_address(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """受管/页面覆盖写在**服务进程**环境里 ⇒ 探针要按它探（不是 bundle 记录的地址）。"""

    address, recorded = endpoint
    bundle, cmd_file = _site(tmp_path, address="http://127.0.0.1:9/never")
    proc_root = tmp_path / "proc"
    (proc_root / "4242").mkdir(parents=True)
    (proc_root / "4242" / "cmdline").write_bytes(
        f"python\0serve_s12e_port\0--serving-pack\0{tmp_path / 'pack'}\0"
        f"--recorded-embedding-bundle\0{bundle}\0".encode()
    )
    (proc_root / "4242" / "environ").write_bytes(
        f"CANONICAL_V2_EMBEDDING_BASE_URL={address}\0".encode()
    )

    assert _run_probe(tmp_path, cmd_file=cmd_file, proc_root=proc_root) == 0
    output = capsys.readouterr().out
    assert "受管/环境覆盖" in output
    assert recorded and str(recorded[0]["path"]).endswith("/embeddings")


def test_drift_in_the_mirrored_literals_is_red(
    tmp_path: Path,
    endpoint: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """镜像里的身份模块换了原生路线字面量 ⇒ 探针的镜像失效，必须红。"""

    address, _recorded = endpoint
    _bundle, cmd_file = _site(tmp_path, address=address)
    identity_module = tmp_path / "identity.py"
    identity_module.write_text(
        'EMBEDDINGS_PATH = "/embeddings"\n'
        'PROVIDER_DASHSCOPE_NATIVE = "dashscope-native"\n'
        'NATIVE_EMBEDDINGS_PATH = "/services/embeddings/text-embedding/something-else"\n'
        "ROUTE_ABSENT_STATUSES = frozenset({404, 405})\n",
        encoding="utf-8",
    )

    assert _run_probe(tmp_path, cmd_file=cmd_file, identity_module=identity_module) == 1
    assert "防漂移" in capsys.readouterr().out
