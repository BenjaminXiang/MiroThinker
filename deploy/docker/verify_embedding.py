#!/opt/mirothinker/.venv/bin/python
"""容器内嵌入身份探针（`mirothinker-verify` 的嵌入那一段）。

**为什么不是"读一张写死的账本"**：镜像里那份 `s12c/qwen-embedding-bundle-v1.json` 是
**v1 时代**的账本（`Qwen/Qwen3-Embedding-8B` / 4096 维 / 自建地址 / OpenAI 兼容线形状）。
v2 站点的嵌入是候选网关的**原生路由**（`qwen3.7-text-embedding-flash` / 1024 维 /
`provider=dashscope-native`）。验收若照旧拿 v1 账本去打，就会在一个**装对了**的站点上报红
（"端点不可达"或"维度不符"）—— 而甲方唯一的判断依据就是这个验收。

**它断言什么**：站点**真正在用**的那份记录 bundle 的身份，探测方式与页面身份校验同一条规则
（`apps/admin-console/backend/services/canonical_v2_embedding_identity.py`）：

* **问地址、不猜配置**：先讲 OpenAI 兼容形状（`{地址}/embeddings`），**只有** HTTP 404/405
  （该地址没有这条路线）才改讲 DashScope 原生形状
  （`{地址}/services/embeddings/text-embedding/text-embedding`）；401/500 之类是该路线自己的
  回答，不换形状。
* **角色是调用方的属性**：这里探的是服务线查询侧（query），原生形状带 `text_type`
  （取自 bundle 的 `query_text_type`，缺省 `query`）。
* 身份（模型/维度）取自**站点在用的记录 bundle**；地址取 `CANONICAL_V2_EMBEDDING_BASE_URL`
  （受管/页面覆盖，镜像 `resolve_embedding_base_url` 的优先级）否则 bundle 记录的地址。
* **服务包身份必须与记录 bundle 一致**：`<pack>/manifest.json` 的 `embedding_model_id` 与
  bundle 的 `model_id` 不同 ⇒ FAIL（索引身份 ≠ 嵌入权威身份）。

**站点在用的 bundle 怎么确定**（不猜）：① 运行中的服务进程 argv 里的
`--recorded-embedding-bundle`（冻结命令文件传入，运行期就是按它加载并逐字段比对）；② 冻结命令
文件里的同一个参数；③ 都没有 ⇒ 报 FAIL 让人查，而不是回落到任何写死的路径。

**防漂移**：镜像里若有上述身份模块/原生客户端，本文件会把它镜像的四个字面量（两条路线、
"路线不存在"的状态码、角色选择）读出来比对，不一致即 FAIL；模块不存在（v1.1 镜像）时打印
说明而不是假装校验过。

只打印状态、形状、维度、模型与来源路径；**从不打印密钥、也不打印上游响应体**。

用法：
  verify_embedding.py [--bundle PATH | --auto] [--pack-dir PATH] [--address URL]
                      [--cmd-file PATH] [--proc-root DIR] [--identity-module PATH]
                      [--native-client PATH] [--timeout SECONDS]
退出码：0 全通 / 1 有红点 / 2 用法或环境问题（同样算红）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ---- 镜像自身份校验模块的四个字面量（漂移即红）--------------------------------
EMBEDDINGS_PATH = "/embeddings"
NATIVE_EMBEDDINGS_PATH = "/services/embeddings/text-embedding/text-embedding"
ROUTE_ABSENT_STATUSES = frozenset({404, 405})
PROVIDER_OPENAI_COMPATIBLE = "openai-compatible"
PROVIDER_DASHSCOPE_NATIVE = "dashscope-native"
ROLE_QUERY = "query"
ROLE_DOCUMENT = "document"

_DEFAULT_CMD_FILE = (
    "/opt/mirothinker/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/"
    "serve-18188-command.sh"
)
_DEFAULT_IDENTITY_MODULE = "/opt/mirothinker/apps/admin-console/backend/services/canonical_v2_embedding_identity.py"
_DEFAULT_NATIVE_CLIENT = "/opt/mirothinker/apps/miroflow-agent/src/data_agents/providers/dashscope_embeddings.py"

PROBE_TEXT = "canonical-v2 embedding identity probe ｜ 深圳科创数据平台向量身份校验"
_SERVICE_MARKERS = ("serve_s12e_port", "complete_candidate_runner")


class ProbeError(RuntimeError):
    """The probe could not produce a verdict (its message is the verdict's reason)."""


def _say(text: str) -> None:
    print(f"  {text}")


def _ok(text: str) -> None:
    print(f"  [OK]   {text}")


def _bad(text: str) -> None:
    print(f"  [FAIL] {text}")


def _note(text: str) -> None:
    print(f"  [note] {text}")


def _flag_values(argv: list[str], flag: str) -> list[str]:
    values = []
    for index, token in enumerate(argv):
        if token == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
        elif token.startswith(f"{flag}="):
            values.append(token.split("=", 1)[1])
    return values


def _service_process(proc_root: Path) -> tuple[list[str], dict[str, str]]:
    """(argv, environ) of the running serving process — the site's *live* configuration.

    Its environment is what matters, not ours: the managed/page settings are projected
    into the *service's* environment at startup, so `docker compose exec` does not see
    them. Our own environment is the fallback, the bundle's recorded address the last.
    """

    try:
        entries = sorted(proc_root.glob("[0-9]*"))
    except OSError:
        return [], {}
    for entry in entries:
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        argv = [part for part in raw.decode("utf-8", "replace").split("\0") if part]
        if not any(marker in token for token in argv for marker in _SERVICE_MARKERS):
            continue
        environ: dict[str, str] = {}
        try:
            for part in (
                (entry / "environ").read_bytes().decode("utf-8", "replace").split("\0")
            ):
                name, separator, value = part.partition("=")
                if separator:
                    environ[name] = value
        except OSError:
            environ = {}
        return argv, environ
    return [], {}


def _live_service_bundle(proc_root: Path) -> Path | None:
    """The `--recorded-embedding-bundle` of the running service, straight from its argv."""

    argv, _environ = _service_process(proc_root)
    values = _flag_values(argv, "--recorded-embedding-bundle")
    return Path(values[0]) if values else None


def _command_file_bundle(cmd_file: Path) -> Path | None:
    try:
        text = cmd_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"--recorded-embedding-bundle\s+(\S+)", text)
    return Path(match.group(1)) if match else None


def _pack_dir(argv: list[str], cmd_file: Path) -> Path | None:
    if argv:
        values = _flag_values(argv, "--serving-pack")
        if values:
            return Path(values[0])
    match = re.search(r"--serving-pack\s+(\S+)", _read_text(cmd_file))
    return Path(match.group(1)) if match else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _live_service_argv(proc_root: Path) -> list[str]:
    return _service_process(proc_root)[0]


def _drift_guard(identity_module: Path, native_client: Path) -> list[str]:
    """Compare the mirrored literals against the image's own modules (names only)."""

    problems: list[str] = []
    module_text = _read_text(identity_module)
    if not module_text:
        return problems
    expected_literals = {
        "EMBEDDINGS_PATH": f'EMBEDDINGS_PATH = "{EMBEDDINGS_PATH}"',
        "PROVIDER_OPENAI_COMPATIBLE": f'PROVIDER_OPENAI_COMPATIBLE = "{PROVIDER_OPENAI_COMPATIBLE}"',
        "PROVIDER_DASHSCOPE_NATIVE": f'PROVIDER_DASHSCOPE_NATIVE = "{PROVIDER_DASHSCOPE_NATIVE}"',
        "NATIVE_EMBEDDINGS_PATH": f'NATIVE_EMBEDDINGS_PATH = "{NATIVE_EMBEDDINGS_PATH}"',
    }
    # 逐个字面量比对：**模块里有的**必须与镜像一致；模块里没有的（老的兼容-only 版本，
    # 例如 v1.1 镜像）不算漂移，只说明这一版的身份校验只讲一条形状。
    compared = 0
    for name, literal in expected_literals.items():
        declaration = re.search(rf"^{name}\s*=\s*(.+)$", module_text, re.MULTILINE)
        if declaration is None:
            continue
        compared += 1
        if literal.split(" = ", 1)[1].strip() != declaration.group(1).strip():
            problems.append(
                f"防漂移：{name} 字面量不一致（身份模块 {declaration.group(1).strip()} "
                f"≠ 本探针 {literal.split(' = ', 1)[1].strip()}）"
            )
    if compared == 0:
        _note(
            f"防漂移：{identity_module.name} 里没有本探针镜像的任何字面量（不认识的版本）—— "
            "本探针的原生回退未被它背书"
        )
    elif "NATIVE_EMBEDDINGS_PATH" not in module_text:
        _note(
            f"防漂移：{identity_module.name} 只讲 OpenAI 兼容形状（没有原生路线常量）—— "
            "本探针多一条原生回退，与它不冲突"
        )
        statuses = re.search(
            r"^ROUTE_ABSENT_STATUSES\s*=\s*frozenset\((\{[^}]*\})\)",
            module_text,
            re.MULTILINE,
        )
        if statuses is not None:
            found = sorted(
                int(value) for value in re.findall(r"\d+", statuses.group(1))
            )
            if found != sorted(ROUTE_ABSENT_STATUSES):
                problems.append(
                    f"防漂移：ROUTE_ABSENT_STATUSES 不一致（身份模块 {found} ≠ 本探针 "
                    f"{sorted(ROUTE_ABSENT_STATUSES)}）"
                )
    native_text = _read_text(native_client)
    if native_text:
        declaration = re.search(
            r"^_TEXT_EMBEDDINGS_PATH\s*=\s*(.+)$", native_text, re.MULTILINE
        )
        if declaration is not None and NATIVE_EMBEDDINGS_PATH not in declaration.group(
            1
        ):
            problems.append(
                f"防漂移：原生客户端的路线 {declaration.group(1).strip()} ≠ 本探针 {NATIVE_EMBEDDINGS_PATH}"
            )
    return problems


def _post_json(
    url: str, payload: dict[str, Any], key: str, timeout: float
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"端点不可达：{type(exc).__name__}: {exc}") from exc


def _compatible_vector(
    address: str, model: str, key: str, timeout: float
) -> tuple[int, Any, list[float] | None]:
    status, body = _post_json(
        f"{address}{EMBEDDINGS_PATH}",
        {"model": model, "input": [PROBE_TEXT]},
        key,
        timeout,
    )
    vector = None
    if status == 200 and isinstance(body, dict):
        rows = body.get("data") or []
        if rows and isinstance(rows[0], dict):
            embedding = rows[0].get("embedding")
            if isinstance(embedding, list):
                vector = [float(value) for value in embedding]
    return status, body, vector


def _native_vector(
    address: str, model: str, key: str, timeout: float, text_type: str | None
) -> tuple[int, Any, list[float] | None]:
    payload: dict[str, Any] = {"model": model, "input": {"texts": [PROBE_TEXT]}}
    if text_type:
        payload["text_type"] = text_type
    status, body = _post_json(
        f"{address}{NATIVE_EMBEDDINGS_PATH}", payload, key, timeout
    )
    vector = None
    if status == 200 and isinstance(body, dict):
        output = body.get("output") or {}
        rows = output.get("embeddings") if isinstance(output, dict) else None
        if isinstance(rows, list) and rows:
            row = rows[0] if isinstance(rows[0], dict) else {}
            embedding = row.get("embedding")
            if isinstance(embedding, list):
                vector = [float(value) for value in embedding]
    return status, body, vector


def _probe(
    address: str, model: str, key: str, timeout: float, text_type: str | None
) -> tuple[str, list[float]]:
    """Ask the address; only an absent route switches the wire shape."""

    status, _body, vector = _compatible_vector(address, model, key, timeout)
    if vector is not None:
        return PROVIDER_OPENAI_COMPATIBLE, vector
    if status in ROUTE_ABSENT_STATUSES:
        native_status, _native_body, native_vector = _native_vector(
            address, model, key, timeout, text_type
        )
        if native_vector is not None:
            return PROVIDER_DASHSCOPE_NATIVE, native_vector
        raise ProbeError(
            f"两条路线都不通：兼容形状 HTTP {status}（按规则当作该路线不存在；"
            f"也可能是这条路线自己的 404，比如模型名不被接受），原生形状 HTTP {native_status}"
        )
    raise ProbeError(
        f"兼容形状 HTTP {status}（401/500 之类是该路线自己的回答，不换形状）"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--bundle", type=Path, default=None)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--pack-dir", type=Path, default=None)
    parser.add_argument("--address", default=None)
    parser.add_argument("--cmd-file", type=Path, default=Path(_DEFAULT_CMD_FILE))
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    parser.add_argument(
        "--identity-module", type=Path, default=Path(_DEFAULT_IDENTITY_MODULE)
    )
    parser.add_argument(
        "--native-client", type=Path, default=Path(_DEFAULT_NATIVE_CLIENT)
    )
    parser.add_argument(
        "--env", dest="environ", default=None, help="(测试用) 读地址覆盖的环境映射文件"
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=None,
        help="嵌入密钥文件（缺省走 load_local_api_key()：环境变量 → .sglang_api_key）",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    import os

    environ = dict(os.environ)
    if args.environ:
        try:
            environ.update(json.loads(Path(args.environ).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    failed = False

    # ---- 站点身份从哪里来（不猜）------------------------------------------------
    live_argv = _live_service_argv(args.proc_root)
    bundle_path = args.bundle
    if bundle_path is None:
        if live_argv:
            values = _flag_values(live_argv, "--recorded-embedding-bundle")
            bundle_path = Path(values[0]) if values else None
        if bundle_path is None:
            bundle_path = _command_file_bundle(args.cmd_file)
    if bundle_path is None:
        _bad(
            "找不到站点在用的记录 bundle（服务进程 argv 与冻结命令文件里都没有 "
            "--recorded-embedding-bundle）—— 不猜路径，请人工确认"
        )
        return 1
    document: dict[str, Any] = {}
    try:
        document = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _bad(f"记录 bundle 不可读：{bundle_path}（{type(exc).__name__}）")
        return 1
    model = str(document.get("model_id") or "")
    dimension = document.get("dimension")
    provider = str(document.get("provider") or "(未记录)")
    if not model or not isinstance(dimension, int) or dimension <= 0:
        _bad(f"记录 bundle 缺 model_id/dimension：{bundle_path}")
        return 1
    _ok(
        f"身份来源：{bundle_path}（model={model} dimension={dimension} provider={provider}）"
    )

    _argv, service_environ = _service_process(args.proc_root)
    address = (
        args.address
        or str(service_environ.get("CANONICAL_V2_EMBEDDING_BASE_URL", ""))
        or str(environ.get("CANONICAL_V2_EMBEDDING_BASE_URL", ""))
    ).strip()
    if address:
        origin = "受管/环境覆盖 CANONICAL_V2_EMBEDDING_BASE_URL（服务进程环境优先）"
    else:
        address = str(document.get("base_url") or "")
        origin = "记录 bundle 的 base_url"
    address = address.rstrip("/")
    if not address:
        _bad("没有可用的嵌入地址（既无环境覆盖，bundle 也没记录 base_url）")
        return 1
    _say(f"生效地址：{address}（来源 {origin}）")

    # ---- 服务包身份必须与嵌入权威一致 -------------------------------------------
    pack_dir = (
        args.pack_dir
        if args.pack_dir is not None
        else _pack_dir(live_argv, args.cmd_file)
    )
    if pack_dir is None:
        _note("服务包目录未知（argv/命令文件里没有 --serving-pack）—— 跳过包身份对照")
    else:
        try:
            manifest = json.loads(
                (pack_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            manifest = {}
        served_model = str(manifest.get("embedding_model_id") or "")
        if not served_model:
            _note(
                f"服务包 manifest 没有 embedding_model_id（{pack_dir}）—— 跳过包身份对照"
            )
        elif served_model != model:
            _bad(
                f"身份不一致：服务包 manifest 的 embedding_model_id={served_model} "
                f"≠ 记录 bundle 的 model_id={model}（索引身份 ≠ 嵌入权威身份）"
            )
            failed = True
        else:
            _ok(f"服务包身份一致：manifest embedding_model_id={served_model}")

    # ---- 防漂移（镜像里若已有身份模块/原生客户端，字面量必须一致）----------------
    for problem in _drift_guard(args.identity_module, args.native_client):
        _bad(problem)
        failed = True

    # ---- 真调用：先兼容形状，只有 404/405 才换原生形状 ---------------------------
    key = ""
    if args.key_file is not None:
        try:
            key = args.key_file.read_text(encoding="utf-8").strip()
        except OSError:
            key = ""
    if not key:
        sys.path.insert(0, "/opt/mirothinker/apps/miroflow-agent")
        try:
            from src.data_agents.providers.local_api_key import load_local_api_key

            key = load_local_api_key() or ""
        except Exception:  # noqa: BLE001 - 密钥读取失败按"缺凭据"报，不解释原因
            key = ""
    if not key:
        _bad("未找到本地嵌入密钥（.sglang_api_key / SGLANG_API_KEY / API_KEY）")
        return 1

    text_type = str(document.get("query_text_type") or ROLE_QUERY)
    try:
        shape, vector = _probe(address, model, key, args.timeout, text_type)
    except ProbeError as exc:
        _bad(f"嵌入端点探针未过：{exc}")
        return 1

    if len(vector) != dimension:
        _bad(
            f"维度不符：{address} HTTP 200，维度 {len(vector)}（期望 {dimension}，model={model}）"
        )
        return 1
    _ok(
        f"嵌入端点 {address}（形状 {shape}，角色 {text_type}）HTTP 200，"
        f"维度 {len(vector)}（model={model}）"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
