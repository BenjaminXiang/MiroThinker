#!/usr/bin/env python3
"""判红演示：**旧** verify 的嵌入断言会在一个（v2 风格的）正确站点上报红，**新**探针不会。

场景：本地假"候选网关"（兼容形状 404、原生形状 200/1024 维）。
* 旧断言（HEAD 版 `verify.sh` 里的那段 python，逐字提取）：读**镜像里那份 v1 账本**
  （`Qwen/Qwen3-Embedding-8B` / 4096 维 / OpenAI 兼容形状）⇒ 拿 4096 比 1024 ⇒ `[FAIL]`。
* 新探针（`deploy/docker/verify_embedding.py`）：身份取自站点在用的记录 bundle（假站点里就是
  候选身份），先兼容、404 才换原生 ⇒ `[OK]`，并报出形状与角色。

只监听 127.0.0.1，不碰真站点/真端点；账本用真 v1 内容，只把地址换成本地假网关。
"""

from __future__ import annotations

import http.server
import json
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
NEW_PROBE = REPO / "deploy" / "docker" / "verify_embedding.py"
LEDGER = REPO / "deploy" / "docker" / "ledger" / "s12c" / "qwen-embedding-bundle-v1.json"

CANDIDATE = {
    "schema_version": "canonical-v2-dashscope-native-embedding-bundle-v1",
    "provider": "dashscope-native",
    "model_id": "qwen3.7-text-embedding-flash",
    "dimension": 1024,
    "base_url": "",
    "query_text_type": "query",
    "api_key_source": "env:CANONICAL_V2_EMBEDDING_API_KEY",
}


class Gateway(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if not self.path.endswith("/services/embeddings/text-embedding/text-embedding"):
            self._answer(404, {"error": {"message": "no compatible route at this prefix"}})
            return
        self._answer(
            200, {"output": {"embeddings": [{"text_index": 0, "embedding": [0.1] * 1024}]}}
        )

    def _answer(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def _old_assertion_source() -> str:
    """HEAD 版 verify.sh 的嵌入断言（逐字提取；只用于判红演示）。"""

    head = subprocess.run(
        ["git", "show", "HEAD:deploy/docker/verify.sh"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    match = re.search(r"if \"\$PY\" - \"\$EMBEDDING_BUNDLE\" <<'PY'\n(.*?)\nPY\n", head, re.S)
    assert match, "没能在 HEAD 版 verify.sh 里找到嵌入断言"
    source = match.group(1)
    # 逐字保留断言逻辑；只把"容器内解释器路径"那两行指到本仓（在宿主机上跑得起来）。
    source = source.replace(
        'sys.path.insert(0, "/opt/mirothinker/apps/miroflow-agent")',
        f'sys.path.insert(0, "{REPO / "apps" / "miroflow-agent"}")',
    )
    return source


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    address = f"http://127.0.0.1:{server.server_port}/api/v1"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = tmp_path / "candidate-embedding-bundle.json"
            bundle.write_text(
                json.dumps({**CANDIDATE, "base_url": address}), encoding="utf-8"
            )
            pack = tmp_path / "pack"
            pack.mkdir()
            (pack / "manifest.json").write_text(
                json.dumps({"embedding_model_id": CANDIDATE["model_id"]}), encoding="utf-8"
            )
            key_file = tmp_path / ".sglang_api_key"
            key_file.write_text("sk-fake-red-demo-0000", encoding="utf-8")
            legacy = json.loads(LEDGER.read_text(encoding="utf-8"))
            legacy["base_url"] = address  # 只换地址，身份保持真 v1 账本
            legacy_bundle = tmp_path / "v1-ledger-local-address.json"
            legacy_bundle.write_text(json.dumps(legacy), encoding="utf-8")
            old_script = tmp_path / "old-embedding-assert.py"
            old_script.write_text(_old_assertion_source(), encoding="utf-8")

            print("== 场景：一个 v2 风格的站点（候选网关，1024 维，原生形状）==")
            print(f"   假网关 {address}（兼容形状 404 / 原生形状 200 · 1024 维）")
            print(
                f"   真 v1 账本身份：model={legacy['model_id']} dimension={legacy['dimension']}"
                f" provider={legacy['provider']}"
            )
            print()

            print("== A. 旧 verify 的嵌入断言（期望身份 = v1 账本）==")
            old = subprocess.run(
                [sys.executable, str(old_script), str(legacy_bundle)],
                capture_output=True,
                text=True,
                # 只给假密钥：旧块走 load_local_api_key()，环境变量优先级最高，
                # 因此绝不会去读仓库里的真 key。
                env={"PATH": "/usr/bin:/bin", "SGLANG_API_KEY": "sk-fake-red-demo-0000"},
            )
            print(old.stdout.rstrip() or old.stderr.rstrip())
            print(f"   exit={old.returncode}（非 0 ⇒ 旧验收会判红）")
            print()

            print("== B. 新探针（期望身份 = 站点在用的记录 bundle）==")
            new = subprocess.run(
                [
                    sys.executable,
                    str(NEW_PROBE),
                    "--bundle",
                    str(bundle),
                    "--pack-dir",
                    str(pack),
                    "--address",
                    address,
                    "--key-file",
                    str(key_file),
                    "--proc-root",
                    str(tmp_path / "no-proc"),
                    "--identity-module",
                    str(tmp_path / "no-module.py"),
                    "--native-client",
                    str(tmp_path / "no-client.py"),
                ],
                capture_output=True,
                text=True,
            )
            print(new.stdout.rstrip() or new.stderr.rstrip())
            print(f"   exit={new.returncode}（0 ⇒ 新验收判过）")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
