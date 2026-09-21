#!/usr/bin/env python3
"""出包自检：交付件里的"数字/名字"必须与随包 bundle / 包清单一致。

为什么需要它（L5）：v1.1 交付包里 `100.64.0.27:18005`、"维度 4096"、`Qwen/Qwen3-Embedding-8B`、
`serving-pack-run16-readerbound` 这些数字/名字散落在指南、runbook、安装器与预置里 —— 对 v1.1 是
正确的，但 v2 换包/换模型时它们**不会自己更新**，而其中两条（预置钉地址、安装器探针写死模型 id）
已经真的咬过现场。这里只做**出包时的自检**：不一致就在打包时报出来（人决定怎么改），
不改文档里的任何文字。

两档：

* **硬**（exit 1）：预置 `state/config-managed/settings.json` 不许钉嵌入地址/模型
  （`extraction_endpoints.embedding_base_url` / `embedding_model`）—— 这两个键有读者（地址）
  或会误导页面（模型），属"预置替操作者拍板"，已明令禁止。
* **软**（只报，exit 0）：文档/脚本里的嵌入端点 URL、"维度 N"、模型 id、服务包名与随包
  bundle/清单不一致时逐条列出（file:line），提醒随包更新。

用法： check-delivery-consistency.py <out-dir> [--quiet]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PRESET_RELATIVE = Path("state/config-managed/settings.json")
_PRESET_FORBIDDEN = (
    "extraction_endpoints.embedding_base_url",
    "extraction_endpoints.embedding_model",
)
_PRESET_ADVISORY = ("paths.serving_pack_dir",)
# 文档里合法的"非自建端点"引用（chat LLM、提供方地址）——命中就不报。
_IGNORED_URLS = frozenset(
    {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
)
# 文档里合法的"带 embedding 字样但不是模型 id"的 token。
_IGNORED_TOKENS = frozenset({"qwen-embedding-bundle-v1.json"})
_MAX_PER_CATEGORY = 12
_TEXT_FILES = ("CONFIG-GUIDE.md", "README.md", "README-FIRST.txt", "BUNDLE-MANIFEST.txt", "install-site.sh")
_URL_RE = re.compile(r"https?://[^\s)\"'`（），。：、；]+")
# 只认"像自建嵌入端点"的地址：裸 IP、带端口的 host，或路径里带 embed。
_ENDPOINT_LIKE_RE = re.compile(r"^https?://(\d{1,3}(?:\.\d{1,3}){3}|[^/]*:\d+|.*embed)", re.IGNORECASE)
_DIMENSION_RE = re.compile(r"维度\s*(\d+)")
_PACK_RE = re.compile(r"serving-pack-[A-Za-z0-9._-]+")
# 只认"像嵌入模型 id"的 token：名字里必须带 embedding（否则 api/health、18005/v1 这类也会命中），
# 并且排除文件名/路径形状（…embedding-bundle-v1.json、bundles/…）。
_MODEL_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.:/-]*[Ee]mbedding[A-Za-z0-9_.:/-]*"
)
_PATHLIKE_RE = re.compile(r"\.[A-Za-z0-9]{2,5}$")


def _bundles(out_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((out_dir / "bundles").glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict) and "base_url" in document:
            records.append(
                {
                    "path": path.name,
                    "base_url": str(document.get("base_url") or "").rstrip("/"),
                    "dimension": document.get("dimension"),
                    "model_id": str(document.get("model_id") or ""),
                }
            )
    return records


def _pack_name(out_dir: Path) -> str:
    checksums = out_dir / "checksums.sha256"
    try:
        text = checksums.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _PACK_RE.search(text)
    return match.group(0) if match else ""


def check(out_dir: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings); errors stop the packaging, warnings only report."""

    errors: list[str] = []
    warnings: list[tuple[int, str]] = []

    def warn(priority: int, message: str) -> None:
        warnings.append((priority, message))

    preset_path = out_dir / _PRESET_RELATIVE
    if preset_path.is_file():
        try:
            preset = json.loads(preset_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{_PRESET_RELATIVE}: 不是合法 JSON（{exc}）")
            preset = {}
        if isinstance(preset, dict):
            endpoints = preset.get("extraction_endpoints") or {}
            for field in _PRESET_FORBIDDEN:
                leaf = field.split(".", 1)[1]
                if isinstance(endpoints, dict) and endpoints.get(leaf) is not None:
                    errors.append(
                        f"{_PRESET_RELATIVE}: 钉住了 {field} = {endpoints[leaf]!r} —— "
                        "预置不许替操作者决定嵌入地址/身份（地址由 bundle 记录，改地址在管理页做）"
                    )
            paths = preset.get("paths") or {}
            for field in _PRESET_ADVISORY:
                leaf = field.split(".", 1)[1]
                if isinstance(paths, dict) and paths.get(leaf) is not None:
                    warn(4, (
                        f"{_PRESET_RELATIVE}: {field} = {paths[leaf]!r} 是版本相关路径；"
                        "服务线的包选择由 --serving-pack 决定（CLI 赢过该环境变量），"
                        "建议随包重打时留空，避免页面/探针指向旧包目录"
                    ))

    bundles = _bundles(out_dir)
    pack_name = _pack_name(out_dir)
    urls = {str(bundle["base_url"]) for bundle in bundles if bundle["base_url"]}
    dimensions = {str(bundle["dimension"]) for bundle in bundles if bundle["dimension"] is not None}
    models = {str(bundle["model_id"]) for bundle in bundles if bundle["model_id"]}

    for name in _TEXT_FILES:
        path = out_dir / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            mentions_embedding = "嵌入" in line or "embedding" in line.lower()
            if mentions_embedding:
                for url in _URL_RE.findall(line):
                    if not _ENDPOINT_LIKE_RE.match(url):
                        continue
                    if url.rstrip("/") in urls or url.rstrip("/") in _IGNORED_URLS:
                        continue
                    warn(
                        0,
                        f"{name}:{number}: 提到嵌入却出现端点 {url}（随包 bundle 记录的是 "
                        f"{sorted(urls) or '无'}）",
                    )
                for token in _MODEL_RE.findall(line):
                    if token in models or token in _IGNORED_TOKENS or _PATHLIKE_RE.search(token):
                        continue
                    warn(
                        1,
                        f"{name}:{number}: 提到嵌入却出现模型 id {token}（随包 bundle 记录的是 "
                        f"{sorted(models) or '无'}）",
                    )
            for found in _DIMENSION_RE.findall(line):
                if dimensions and found not in dimensions:
                    warn(
                        2,
                        f"{name}:{number}: 写着「维度 {found}」（随包 bundle 是 {sorted(dimensions)}）",
                    )
            for found in _PACK_RE.findall(line):
                if pack_name and found != pack_name:
                    warn(
                        3, f"{name}:{number}: 出现 {found}（随包的服务包是 {pack_name}）"
                    )

    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check-delivery-consistency.py <out-dir> [--quiet]", file=sys.stderr)
        return 2
    out_dir = Path(argv[1])
    quiet = "--quiet" in argv[2:]
    if not out_dir.is_dir():
        print(f"[FAIL] 交付包目录不存在：{out_dir}", file=sys.stderr)
        return 1

    errors, warnings = check(out_dir)
    unique_warnings = [
        message for _priority, message in sorted(dict.fromkeys(warnings))
    ]
    for warning in unique_warnings[:_MAX_PER_CATEGORY]:
        print(f"  [warn] {warning}")
    if len(unique_warnings) > _MAX_PER_CATEGORY:
        print(f"  [warn] …另有 {len(unique_warnings) - _MAX_PER_CATEGORY} 条同类（不逐条列）")
    for error in errors:
        print(f"  [FAIL] {error}")
    if not errors and not unique_warnings and not quiet:
        print("  [ok]   交付件里的数字/名字与随包 bundle 一致")
    elif not errors and not quiet:
        print(f"  [warn] 共 {len(unique_warnings)} 处需要人看一眼（改不改由出包人判断）")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
