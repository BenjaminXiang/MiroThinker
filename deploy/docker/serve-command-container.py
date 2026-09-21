#!/usr/bin/env python3
"""宿主命令文件 → **容器命令文件**的产出与校验（容器交付线）。

**为什么需要它**：宿主（裸机）命令文件与容器命令文件是两种东西，形状上最容易漏的三处：

| 项 | 宿主草案 | 容器 |
|---|---|---|
| launcher | `<switch-line>/….s12e/serve_s12e_port.py` + 宿主 python | `/home/…/canonical-v2-s11-consolidation/….s12e/serve_s12e_port.py`
（`Dockerfile` 把 `canonical-v2-s11-consolidation` 符号链接到 `/opt/mirothinker`，即镜像自己那棵树） |
| `src` 树钉法 | **必须** `PYTHONPATH=<switch-line>/apps/miroflow-agent` | **不需要**：镜像 venv 的 editable `.pth` 指向 `/opt/mirothinker/apps/*`（`.dockerignore` 排除了宿主 `.venv`） |
| 账本/凭据 | `--recorded-embedding-bundle` 指候选 bundle；`CANONICAL_V2_EMBEDDING_API_KEY="$(cat …)"` | 指**镜像账本**（`deploy/docker/ledger/` → Dockerfile COPY）；密钥由挂载文件提供，命令文件里**不许**有 |

直接把宿主草案当容器命令文件用：`PYTHONPATH` 指向容器里不存在的路径、launcher 不存在 ⇒ **容器起不来或
import 错树**。所以这里做两件事：

* `convert`：按显式映射把宿主命令文件转成容器命令文件（默认丢掉 `PYTHONPATH` 与任何 `*_API_KEY=`），
  并**强制**：身份字段（release/run id、两个 sha、bundle 记录、端口…）与宿主逐字相同、与宿主不同的
  只能是被显式映射过的那几个路径参数；
* `check`：对任意一份"想当容器命令文件用"的文件做只读校验 ——
  ① 每个**镜像内**绝对路径都必须在镜像里存在（`docker run --rm … test -e`，或用 `--probe-root` 指向
     一份解开的镜像树）；② 数据面路径（`--data-root`）允许不存在，但其挂载点必须在镜像里；
  ③ 禁止宿主构造（`PYTHONPATH=`、`$(…)`/反引号、`*_API_KEY=`）；④ 禁止未解析的 `__STEPn_…__` 占位符；
  ⑤ 必需的 identity 旗标齐全且 sha 形如 64-hex；⑥ 记录的 serving bundle 自述字段（`content_sha256`/
  `release_id`/`database_name`/`index_root`/`envelope_path`/`embedding_model_id`）必须与对应旗标一致
  —— 这几条不符运行时直接 `ValueError`，服务起不来。

退出码：0 通过 / 1 有红点 / 2 用法错。只读，不改服务状态；**从不打印密钥**（遇到 `*_API_KEY=` 只报名字）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

#: 数据面：由 compose 挂载提供，镜像里只有挂载点本身。
DEFAULT_DATA_ROOTS = (
    "/var/tmp/mirothinker-data-v2",
    "/var/tmp/mirothinker-canonical-v2-s12f",
)

#: identity 旗标：容器命令文件必须带齐（缺一即红）。值形如 64-hex 的两个单独校验。
REQUIRED_FLAGS = (
    "--candidate-release-id",
    "--run-id",
    "--index-marker-sha256",
    "--source-manifest-sha256",
    "--recorded-decision-bundle",
    "--recorded-embedding-bundle",
    "--recorded-serving-bundle",
    "--recorded-serving-bundle-sha256",
    "--serving-pack",
    "--index-root",
)
SHA_FLAGS = ("--index-marker-sha256", "--source-manifest-sha256", "--recorded-serving-bundle-sha256")
#: 这些旗标的值是"路径"，允许在转换时被显式映射；其余旗标必须逐字相同。
PATH_FLAGS = (
    "--recorded-decision-bundle",
    "--recorded-embedding-bundle",
    "--recorded-serving-bundle",
    "--serving-pack",
    "--index-root",
    "--accepted-backup-gate-root",
    "--source-manifest",
    "--candidate-staging-root",
    "--envelope-output",
    "--accepted-original-milvus-path",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER_RE = re.compile(r"__STEP\d+_[A-Z0-9_]+__")
_KEY_ASSIGN_RE = re.compile(r"(?:^|\s)([A-Z0-9_]*API_KEY[A-Z0-9_]*)=([^\s]*)")
_FLAG_TOKEN_RE = re.compile(r"^--[a-z0-9-]+$")


def _fail(message: str) -> None:
    print(f"  [FAIL] {message}")


def _ok(message: str) -> None:
    print(f"  [OK]   {message}")


def _note(message: str) -> None:
    print(f"  [note] {message}")


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"\s+", text.strip()) if token]


def _flag_values(tokens: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _FLAG_TOKEN_RE.match(token) and index + 1 < len(tokens):
            values.setdefault(token, []).append(tokens[index + 1])
            index += 2
            continue
        if token.startswith("--") and "=" in token:
            name, _, value = token.partition("=")
            values.setdefault(name, []).append(value)
        index += 1
    return values


#: 运行期**真的会读**的路径（旗标 → 必须存在）。其余路径旗标只提示，不判红 ——
#: 例如 `--source-manifest`/`--envelope-output`/`--accepted-original-milvus-path` 在
#: `--serve --serve-existing` 模式下只被参数校验触碰、不被读取（v1.1 交付件即如此，
#: 且服务正常起——所以"每条绝对路径都必须存在"这个要求要按"读不读"分类）。
BOOT_READ_FLAGS = (
    "--recorded-decision-bundle",
    "--recorded-embedding-bundle",
    "--recorded-serving-bundle",
    "--serving-pack",
    "--index-root",
)
INERT_PATH_FLAGS = (
    "--source-manifest",
    "--envelope-output",
    "--accepted-original-milvus-path",
    "--candidate-staging-root",
    "--accepted-backup-gate-root",
)


def _path_values(tokens: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(boot-read paths, inert flag paths, launcher/positional paths)."""

    flags = _flag_values(tokens)
    boot = [
        value
        for flag in BOOT_READ_FLAGS
        for value in flags.get(flag, ())
        if value.startswith("/") and "$" not in value and "`" not in value
    ]
    inert = [
        value
        for flag in INERT_PATH_FLAGS
        for value in flags.get(flag, ())
        if value.startswith("/") and "$" not in value and "`" not in value
    ]
    positional = [
        token
        for token in tokens
        if token.startswith("/")
        and "://" not in token
        and not token.startswith("/dev/")
        and "$" not in token
        and "`" not in token
        and '"' not in token  # 带引号的是 shell 碎片（例如 `$(cat …)"` 的后半段），不是路径
    ]
    # 环境前缀里的宿主路径（NAME=/path）：也算"路径"，一并分类（数据面/镜像内）。
    for token in tokens:
        name, separator, value = token.partition("=")
        if (
            separator
            and name
            and value.startswith("/")
            and "://" not in value
            and "$" not in value
            and "`" not in value
        ):
            positional.append(value)
    seen: set[str] = set()
    result: tuple[list[str], list[str], list[str]] = ([], [], [])
    for bucket, values in zip(result, (boot, inert, positional)):
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            bucket.append(value)
    return result


def _image_file_text(image: str, path: str) -> str | None:
    """镜像里某个文件的内容（`/bin/cat`；不存在/没 docker 都返回 None）。"""

    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "/bin/cat", image, path],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _probe_image_paths(image: str, paths: list[str], probe_root: Path | None) -> list[str]:
    """Return the image-internal paths that do NOT exist (empty when everything is there)."""

    if not paths:
        return []
    if probe_root is not None:
        return [path for path in paths if not (probe_root / path.lstrip("/")).exists()]
    # 路径经 stdin 交给容器内循环：**不把文件里的 token 插进 shell**（命令文件里可能有
    # $(…) 之类；那条由 forbid 检查单独判红，这里不能因此执行或崩）。
    # 结尾必须 `exit 0`：循环里最后一条 `[ ! -e … ]` 失败会把整个脚本的退出码带成 1。
    script = 'while IFS= read -r p; do [ -n "$p" ] && [ ! -e "$p" ] && printf "%s\\n" "$p"; done; exit 0'
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "/bin/sh", image, "-c", script],
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"  [FAIL] 无法在镜像 {image} 里检查路径：{result.stderr.strip()[:200]}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_command(
    *,
    command: str,
    image: str,
    data_roots: tuple[str, ...],
    probe_root: Path | None,
    quiet: bool = False,
) -> int:
    tokens = _tokens(command)
    failures = 0

    # ① 宿主构造（容器里一定坏或不该出现）
    if "PYTHONPATH=" in command:
        _fail("出现 PYTHONPATH=：镜像 venv 的 editable .pth 已把 src 钉在 /opt/mirothinker/apps/*，"
              "容器命令文件不该带宿主那条钉法")
        failures += 1
    if "$(" in command or "`" in command:
        _fail("出现命令替换 $(…)/反引号：容器命令文件必须是静态的（密钥由挂载文件提供）")
        failures += 1
    for match in _KEY_ASSIGN_RE.finditer(command):
        _fail(f"出现密钥赋值 {match.group(1)}=…：容器里密钥由挂载文件提供（入口脚本负责投影），"
              "命令文件里不许有")
        failures += 1
    # ② 未解析占位符
    for placeholder in sorted(set(_PLACEHOLDER_RE.findall(command))):
        _fail(f"未解析的占位符 {placeholder}：容器命令文件必须在打包前把 identity 定死")
        failures += 1
    # ③ identity 旗标齐全 + sha 形状
    flags = _flag_values(tokens)
    for flag in REQUIRED_FLAGS:
        if flag not in flags:
            _fail(f"缺 identity 旗标 {flag}")
            failures += 1
    for flag in SHA_FLAGS:
        for value in flags.get(flag, ()):
            if not _SHA256_RE.match(value):
                _fail(f"{flag} 的值不是 64 位 hex：{value!r}" + ("（占位符未解析？）" if "__STEP" in value else ""))
                failures += 1
    if "18188" not in tokens:
        _fail("命令里没有固定端口 18188（冻结命令文件把端口钉死）")
        failures += 1

    # ④ 路径：运行期真的会读的必须在镜像里存在；数据面路径只要求挂载点在；惰性路径只提示
    boot_paths, inert_paths, positional = _path_values(tokens)
    def _split(values: list[str]) -> tuple[list[str], list[str]]:
        image_side, data_side = [], []
        for path in values:
            root = next((c for c in data_roots if path == c or path.startswith(c + "/")), None)
            (data_side if root else image_side).append(path)
        return image_side, data_side

    boot_image, boot_data = _split(boot_paths)
    launcher_image, launcher_data = _split(positional)
    inert_image, inert_data = _split(inert_paths)
    missing = _probe_image_paths(image, boot_image + launcher_image, probe_root)
    mount_points = sorted(
        {next(c for c in data_roots if p.startswith(c)) for p in boot_data + launcher_data}
    )
    missing_mounts = _probe_image_paths(image, mount_points, probe_root)
    for path in missing:
        _fail(f"镜像内不存在（运行期会读）：{path}")
        failures += 1
    for path in missing_mounts:
        _fail(f"数据面挂载点不存在于镜像：{path}")
        failures += 1
    if not quiet:
        checked = len(boot_image) + len(launcher_image)
        _ok(f"运行期会读的镜像内路径 {checked} 个（缺 {len(missing)}）")
        _ok(f"数据面路径 {len(boot_data) + len(launcher_data)} 个（挂载提供）：{'、'.join(mount_points) or '无'}")
        _note("容器里 src 树的钉法：镜像 venv 的 editable .pth → /opt/mirothinker/apps/*（无需 PYTHONPATH）")
        if inert_image:
            absent = _probe_image_paths(image, inert_image, probe_root)
            _note(
                f"惰性路径 {len(inert_image)} 个（运行期不读，只被参数校验触碰）："
                f"镜像里存在的 {len(inert_image) - len(absent)} 个，不在的 {len(absent)} 个"
                + ("（不在的是 " + "、".join(p.rsplit("/", 1)[-1] for p in absent) + "）" if absent else "")
            )
    # ⑤ 记录的 serving bundle 自述的 identity 必须与旗标一致（运行期会逐条比对，不符即起不来）
    failures += _bundle_agreement(flags, image=image, probe_root=probe_root)
    return 1 if failures else 0


def _identity_view(tokens: list[str]) -> dict[str, list[str]]:
    flags = _flag_values(tokens)
    return {flag: flags[flag] for flag in REQUIRED_FLAGS if flag in flags}


def _read_container_bundle(bundle: str, image: str, probe_root: Path | None) -> dict | None:
    """容器路径上的 bundle 内容。

    账本由 `Dockerfile` COPY 进镜像，宿主上**通常没有**镜像里的那个路径 —— 只看宿主机
    会漏掉身份比对。所以：`--probe-root` ⇒ 只认那棵树（测试路径，不碰 docker）；否则
    先**直接从镜像里读**（那才是容器里的真东西），读不到再退回宿主机同名文件。
    """

    if probe_root is not None:
        tree_path = probe_root / bundle.lstrip("/")
        return json.loads(tree_path.read_text(encoding="utf-8")) if tree_path.is_file() else None
    text = _image_file_text(image, bundle)
    try:
        if text is not None:
            return json.loads(text)
    except json.JSONDecodeError:
        return None
    if Path(bundle).is_file():
        return json.loads(Path(bundle).read_text(encoding="utf-8"))
    return None


def _first(flags: dict[str, list[str]], flag: str) -> str | None:
    values = flags.get(flag)
    return values[0] if values else None


def _short(value: object, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


#: 记录的 serving bundle 自述字段 ↔ 命令文件旗标。这些不是"建议"，而是**运行期的 ValueError**
#: （`load_recorded_serving_inputs`，`knowledge_serving_isolated.py:6578-6595`）：任一条不符，
#: 服务就起不来。所以容器出包时必须在本机先把它们对齐，而不是到容器里才发现。
BUNDLE_AGREEMENT = (
    ("--recorded-serving-bundle-sha256", "content_sha256"),
    ("--candidate-release-id", "release_id"),
    ("--expected-database", "database_name"),
    ("--index-root", "index_root"),
    ("--envelope-output", "envelope_path"),
)


def _bundle_agreement(flags: dict[str, list[str]], *, image: str, probe_root: Path | None) -> int:
    """Serving bundle 自述的 identity 必须与命令文件的旗标一致（运行期会逐条比对）。"""

    path = _first(flags, "--recorded-serving-bundle")
    if path is None or not path.startswith("/"):
        return 0
    doc = _read_container_bundle(path, image, probe_root)
    if not isinstance(doc, dict):
        _note(f"读不到记录的 serving bundle（{path}）：它与 identity 旗标的自洽这次没检查")
        return 0
    failures = 0
    compared = 0
    for flag, key in BUNDLE_AGREEMENT:
        value, declared = _first(flags, flag), doc.get(key)
        if value is None or declared is None:
            continue
        compared += 1
        if value != declared:
            _fail(
                f"{flag} 与 bundle 自述的 {key} 不符：{value!r} != {declared!r}"
                "（运行期 ValueError ⇒ 服务起不来）"
            )
            failures += 1
    release, target = doc.get("release_id"), doc.get("index_target_id")
    if release and target and target != f"index:{release}":
        _fail(f"bundle 自述的 index_target_id（{target}）与 release_id（{release}）不自洽")
        failures += 1
    kind = doc.get("database_target_kind")
    if kind is not None and kind != "disposable":
        _fail(f"bundle 自述的 database_target_kind={kind!r}：只有 disposable 目标能这样起服务")
        failures += 1
    embedding_path = _first(flags, "--recorded-embedding-bundle")
    embedding_doc = (
        _read_container_bundle(embedding_path, image, probe_root)
        if embedding_path and embedding_path.startswith("/")
        else None
    )
    if isinstance(embedding_doc, dict):
        served = doc.get("embedding_model_id")
        recorded = embedding_doc.get("model_id")
        if served is not None and recorded is not None:
            compared += 1
            if served != recorded:
                _fail(
                    f"嵌入 bundle 的 model_id（{recorded}）≠ serving bundle 的 embedding_model_id"
                    f"（{served}）（运行期 ValueError ⇒ 构建与服务不是同一向量空间）"
                )
                failures += 1
    if compared and not failures:
        _ok(f"记录的 serving bundle 与 identity 旗标自洽（{compared} 条：sha/发布/库/索引/信封/嵌入模型）")
    elif not compared:
        _note("serving bundle 自述字段不全（或 identity 旗标缺失）：自洽性这次没检查")
    return failures


def convert_command(
    *,
    host_command: str,
    image: str,
    out_path: Path,
    mapping: dict[str, str],
    data_roots: tuple[str, ...],
    probe_root: Path | None,
    host_embedding_bundle: Path | None,
) -> int:
    tokens = _tokens(host_command)
    converted = [mapping.get(token, token) for token in tokens]
    # 宿主环境前缀：PYTHONPATH 与任何 *_API_KEY= 一律丢（容器有更好的来源）
    kept: list[str] = []
    skip_next = False
    for token in converted:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("PYTHONPATH="):
            continue
        if _KEY_ASSIGN_RE.match(token):
            # `NAME="$(cat /path)"` 按空白切成两段：`NAME="$(cat` 与 `/path)"`。第二段是
            # 同一份赋值的碎片，留下会变成一条莫名其妙的命令（容器连启动都到不了）。
            value = token.partition("=")[2]
            if value.startswith('"') and not (len(value) > 1 and value.endswith('"')):
                skip_next = True
            continue
        kept.append(token)
    converted = kept
    text = " ".join(converted)

    print("== convert: 逐项核对 ==")
    failures = 0
    host_identity = _identity_view(tokens)
    new_identity = _identity_view(converted)
    for flag, values in host_identity.items():
        if flag in PATH_FLAGS or new_identity.get(flag) == values:
            continue
        # 占位符不是 identity 值，而是"待 step 7/step 10 填"的位置：转换时被解析成具体值
        # 是**目的**，不是违规（解析结果由 check 的 64-hex 规则兜住）。
        if all(_PLACEHOLDER_RE.fullmatch(value) for value in values):
            continue
        _fail(f"identity 旗标 {flag} 在转换后变了：{values} → {new_identity.get(flag)}")
        failures += 1
    mapped = {token: mapping[token] for token in mapping if token in tokens}
    if not mapped:
        _fail("没有任何路径被映射：宿主路径原样进容器会指向不存在的东西")
        failures += 1
    for host_path, container_path in mapped.items():
        if _PLACEHOLDER_RE.fullmatch(host_path):
            continue  # 占位符的值不是路径，按"解析成具体值"处理（见下）
        if not container_path.startswith("/"):
            # `uv run python` 这类"命令形式"是合法的替换（镜像里没有宿主 venv）；
            # 带 `/` 的相对路径才是错。
            if "/" in container_path:
                _fail(f"映射目标既不是绝对路径也不是命令：{host_path} → {container_path}")
                failures += 1
            continue
        if not any(container_path.startswith(root) for root in data_roots) and not Path(container_path).exists():
            _note(f"映射目标 {container_path} 不在容器数据面下（镜像内路径，交给 --image 检查）")
    _ok(f"映射 {len(mapped)} 条：identity 旗标逐字相同，仅路径参数被替换")
    resolved = sorted(token for token in mapped if _PLACEHOLDER_RE.fullmatch(token))
    if resolved:
        _ok(f"占位符 {len(resolved)} 个已解析为具体值：{'、'.join(resolved)}")

    if "PYTHONPATH=" in host_command:
        _note("宿主命令里的 PYTHONPATH 已丢弃：镜像 venv 的 editable .pth 指向 /opt/mirothinker/apps/*")
    if _KEY_ASSIGN_RE.search(host_command):
        _note("宿主命令里的 *_API_KEY= 已丢弃：容器里密钥由挂载文件 + 入口脚本投影提供")

    if host_embedding_bundle is not None:
        container_bundle = mapping.get(str(host_embedding_bundle))
        if container_bundle is None:
            _fail(f"宿主嵌入 bundle {host_embedding_bundle} 没有被映射到容器路径（账本模式要求 COPY 同一份内容）")
            failures += 1
        else:
            host_doc = json.loads(host_embedding_bundle.read_text(encoding="utf-8"))
            container_doc = _read_container_bundle(container_bundle, image, probe_root)
            if container_doc is None:
                _note(
                    f"读不到容器路径上的 bundle {container_bundle}（宿主/镜像里都没有）——"
                    "打包时必须由 Dockerfile COPY 进来，否则运行期读取即失败"
                )
            else:
                # 逐**字段**比全文，不只比四个身份字段：同名的候选 bundle 在几棵 worktree 里就有
                # 三份不同内容（`query_instruct`/`query_text_type`/`batch_size` 不同 = 查询侧 vs
                # 文档侧），只比身份字段认不出来。账本模式要求的就是"COPY 同一份内容"。
                diff = {
                    key: (_short(host_doc.get(key)), _short(container_doc.get(key)))
                    for key in sorted(set(host_doc) | set(container_doc))
                    if host_doc.get(key) != container_doc.get(key)
                }
                if diff:
                    _fail(f"宿主候选 bundle 与容器账本不是同一份内容（字段差异）：{diff}")
                    failures += 1
                else:
                    fields = "、".join(("model_id", "dimension", "provider", "base_url"))
                    _ok(f"宿主候选 bundle 与容器账本逐字段一致（{fields} … 全文，{len(host_doc)} 个字段）")

    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"== 写出容器命令文件：{out_path}（{len(text)} 字节）==")
    print()
    print("== check: 对刚刚写出的文件做容器校验 ==")
    check_rc = check_command(
        command=text, image=image, data_roots=data_roots, probe_root=probe_root
    )
    return 1 if (failures or check_rc) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    check = sub.add_parser("check", help="校验一份命令文件能不能当容器命令文件用")
    check.add_argument("--image", required=True)
    check.add_argument("--command", type=Path, required=True)
    check.add_argument("--data-root", action="append", default=None)
    check.add_argument("--probe-root", type=Path, default=None, help="(测试用) 用解开的镜像树代替 docker run")

    convert = sub.add_parser("convert", help="宿主命令文件 → 容器命令文件")
    convert.add_argument("--host-command", type=Path, required=True)
    convert.add_argument("--image", required=True)
    convert.add_argument("--out", type=Path, required=True)
    convert.add_argument("--map", action="append", default=[], metavar="HOST=CONTAINER")
    convert.add_argument("--host-embedding-bundle", type=Path, default=None,
                         help="宿主候选 bundle；会被映射到容器账本路径并比对身份")
    convert.add_argument("--data-root", action="append", default=None)
    convert.add_argument("--probe-root", type=Path, default=None)

    args = parser.parse_args(argv)
    data_roots = tuple(args.data_root) if args.data_root else DEFAULT_DATA_ROOTS
    if args.mode == "check":
        return check_command(
            command=args.command.read_text(encoding="utf-8"),
            image=args.image,
            data_roots=data_roots,
            probe_root=args.probe_root,
        )
    mapping: dict[str, str] = {}
    for item in args.map:
        host, _, container = item.partition("=")
        mapping[host] = container
    return convert_command(
        host_command=args.host_command.read_text(encoding="utf-8"),
        image=args.image,
        out_path=args.out,
        mapping=mapping,
        data_roots=data_roots,
        probe_root=args.probe_root,
        host_embedding_bundle=args.host_embedding_bundle,
    )


if __name__ == "__main__":
    raise SystemExit(main())
