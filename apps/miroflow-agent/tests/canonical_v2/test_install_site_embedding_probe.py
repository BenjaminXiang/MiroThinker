"""安装器的嵌入探针：端点/模型/维度**全部取自随包 bundle**，一个都不写死。

为什么值得一条行为级测试（而不是读代码）：探针写死模型 id 时，v2 站点（第三方网关、
`qwen3.7-text-embedding-flash`）会拿 v1 的 `Qwen/Qwen3-Embedding-8B` 去打 ⇒ 网关 404 /
维度 0 ⇒ 交付件在**明明配好了**的现场报黄灯（`[warn] 嵌入端点探针未过`），最费支持成本。

测试做法：起一个本地假嵌入端点（记录收到的请求体），给它一份"模型 id 与维度都不是 v1 值"的
随包 bundle，然后跑 `install-site.sh --dry-run`（dry-run 不落地任何东西），断言：
① 探针请求里的 `model` == bundle 的 `model_id`；② 判定用的维度来自 bundle（不是 4096 的硬编码）。

红能力：`MIROTHINKER_TEST_INSTALLER_PATH` 可以指到另一份 `install-site.sh`（mutation/回归对照）——
指到修前的版本时本文件会红。
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import threading
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_INSTALLER = Path(
    os.environ.get(
        "MIROTHINKER_TEST_INSTALLER_PATH",
        str(_REPO_ROOT / "deploy" / "docker" / "install-site.sh"),
    )
)

# 刻意都不是 v1 的值：模型 id 只要被写死就必然对不上。
_BUNDLE_MODEL = "fake-vendor/embedding-xyz-1024"
_BUNDLE_DIMENSION = 3
_BUNDLE_KEY = "sk-fake-installer-probe-0000"


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server 的接口名
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {"raw": raw.decode("utf-8", "replace")}
        type(self).requests.append(
            {
                "path": self.path,
                "authorization_present": bool(self.headers.get("Authorization")),
                "body": body,
            }
        )
        payload = json.dumps(
            {"data": [{"embedding": [0.0] * _BUNDLE_DIMENSION}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:  # 静音
        return


@pytest.fixture()
def fake_embedding_endpoint() -> tuple[str, list[dict[str, object]]]:
    _RecordingHandler.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _RecordingHandler.requests
    finally:
        server.shutdown()
        server.server_close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _scratch_bundle(tmp_path: Path, base_url: str) -> Path:
    bundle = tmp_path / "bundle"
    (bundle / "bundles").mkdir(parents=True)
    (bundle / "secrets").mkdir()
    (bundle / "bundles" / "qwen-embedding-bundle-v1.json").write_text(
        json.dumps(
            {
                "base_url": base_url,
                "dimension": _BUNDLE_DIMENSION,
                "model_id": _BUNDLE_MODEL,
                "api_key_source": "local_api_key",
            }
        ),
        encoding="utf-8",
    )
    key_file = bundle / "secrets" / ".sglang_api_key"
    key_file.write_text(_BUNDLE_KEY, encoding="utf-8")
    key_file.chmod(0o600)
    # step 0 只要求这几个文件"存在"；dry-run 不校验也不解包。
    for name in (
        "mirothinker-serving-v1.1.tar.gz",
        "serving-data-v1.1.tar.gz",
        "compose.yaml",
        "checksums.sha256",
    ):
        (bundle / name).write_text("", encoding="utf-8")
    return bundle


def test_installer_probe_uses_the_bundle_model_and_dimension(
    tmp_path: Path, fake_embedding_endpoint: tuple[str, list[dict[str, object]]]
) -> None:
    base_url, recorded = fake_embedding_endpoint
    bundle = _scratch_bundle(tmp_path, base_url)

    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "MIROTHINKER_SITE_ROOT": str(tmp_path / "site-root"),
        "MIROTHINKER_SITE_PORT": str(_free_port()),
    }
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        [
            "bash",
            str(_INSTALLER),
            "--dry-run",
            "--port",
            env["MIROTHINKER_SITE_PORT"],
            "--bundle-dir",
            str(bundle),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    # 探针跑在 step 1；scratch 包后面必然在 step 2（校验文件）按约定失败 —— 只要求不是用法错。
    assert result.returncode not in (2, 10), result.stdout + result.stderr
    assert recorded, f"探针没有发出请求：\n{result.stdout}"
    body = recorded[0]["body"]
    assert isinstance(body, dict)
    assert body.get("model") == _BUNDLE_MODEL, (
        "探针请求没有用随包 bundle 的 model_id（又写死了？）"
    )
    assert recorded[0]["authorization_present"] is True
    # 维度也来自 bundle：假端点只回 3 维，硬编码 4096 的话这里会是黄灯。
    assert f"维度 {_BUNDLE_DIMENSION}（期望 {_BUNDLE_DIMENSION}）" in result.stdout
    assert "嵌入端点探针未过" not in result.stdout


def test_probe_is_skipped_instead_of_guessing_a_model(
    tmp_path: Path, fake_embedding_endpoint: tuple[str, list[dict[str, object]]]
) -> None:
    """bundle 里没有 model_id ⇒ 跳过并说明，不拿任何猜的模型 id 去打。"""

    base_url, recorded = fake_embedding_endpoint
    bundle = _scratch_bundle(tmp_path, base_url)
    (bundle / "bundles" / "qwen-embedding-bundle-v1.json").write_text(
        json.dumps({"base_url": base_url, "dimension": _BUNDLE_DIMENSION}),
        encoding="utf-8",
    )

    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "MIROTHINKER_SITE_ROOT": str(tmp_path / "site-root"),
    }
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        [
            "bash",
            str(_INSTALLER),
            "--dry-run",
            "--port",
            str(_free_port()),
            "--bundle-dir",
            str(bundle),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode not in (2, 10), result.stdout + result.stderr
    assert not recorded, "bundle 缺 model_id 时不该发探针请求"
    assert "缺 base_url/dimension/model_id" in result.stdout
