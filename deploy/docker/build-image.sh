#!/usr/bin/env bash
# 构建交付镜像并打成可网络传输的 kit（镜像 tar + sha256 + 编排/文档副本 + 清单）。
#
# 用法：
#   deploy/docker/build-image.sh [IMAGE_TAG]
#   默认 tag: mirothinker-serving:v1
#   输出目录: ${MIROTHINKER_DOCKER_KIT_DIR:-/var/tmp/mirothinker-docker-kit}
#
# 产出（可直接 scp 到甲方机器）：
#   mirothinker-serving-v1.tar        镜像本体（docker load 即可）
#   mirothinker-serving-v1.tar.sha256 校验和
#   kit-manifest.txt                  镜像 ID/尺寸/构建耗时/文件 sha256/冻结点 commit
#   compose.yaml  README.md           现场编排与运维手册
#   secrets/                          仅放 4 个密钥文件的**占位说明**，不含真实密钥
#
# 现场机器不需要 Docker Hub、不需要 PyPI、不需要 apt（详见 README）。

set -euo pipefail

TAG="${1:-mirothinker-serving:v1}"
KIT_DIR="${MIROTHINKER_DOCKER_KIT_DIR:-/var/tmp/mirothinker-docker-kit}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

TAR_NAME="$(printf '%s' "$TAG" | tr ':/' '--')"
TAR_PATH="${KIT_DIR}/${TAR_NAME}.tar"

command -v docker >/dev/null || { echo "缺少 docker" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker info 失败（权限或 daemon 未起）" >&2; exit 1; }
command -v uv >/dev/null || { echo "缺少 uv（构建机需要它来准备托管 CPython 3.12.12）" >&2; exit 1; }

# 冻结契约：镜像里的解释器必须是**封印服务包时用的那个补丁版本**（3.12.12），
# 否则 serving_pack_loader.reader_contract_digest() 与包里的摘要不符，
# 每次启动会重放整张对象图的 reconstruction（实测 +190 s）。
# 这里复用构建机上 uv 已装好的那一份（python-build-standalone 直连只有 ~17 KB/s）。
mkdir -p "$KIT_DIR"
managed_python_root="$(uv python dir 2>/dev/null)"
managed_python="${managed_python_root}/cpython-3.12.12-linux-x86_64-gnu"
if [[ ! -x "${managed_python}/bin/python3.12" ]]; then
  echo "构建机缺少托管 CPython 3.12.12：${managed_python}" >&2
  echo "先执行：uv python install 3.12.12（本机网络约 17 KB/s，33 MB ≈ 33 分钟，一次即可）" >&2
  exit 1
fi
echo "== 托管 CPython：$("${managed_python}/bin/python3.12" -V 2>&1) @ ${managed_python} =="

echo "== 构建 $TAG（context=$REPO_ROOT）=="
# --network=host：本机的容器出网是白名单制（ash 只放行 apt 镜像 / CDN / 模型服务），
# PyPI 不在其中 ⇒ 构建期必须借宿主机网络命名空间（现场不需要网络，这只是构建机的事）。
started="$(date +%s)"
docker buildx build \
  --load \
  --network=host \
  --build-context managed_python="${managed_python}" \
  --file "${REPO_ROOT}/deploy/docker/Dockerfile" \
  --tag "$TAG" \
  "$REPO_ROOT"
build_seconds=$(( $(date +%s) - started ))
echo "== 构建完成：${build_seconds}s =="

image_id="$(docker image inspect -f '{{.Id}}' "$TAG")"
image_size_bytes="$(docker image inspect -f '{{.Size}}' "$TAG")"
image_size_human="$(numfmt --to=iec --suffix=B "$image_size_bytes" 2>/dev/null || echo "${image_size_bytes}B")"
echo "image id=$image_id size=$image_size_human"

echo "== 镜像内冒烟（依赖齐全 + Chromium 可解析 + 非 root 下 uv run 可用）=="
# 以**交付时真正使用的非 root 身份**跑冒烟：root 跑得通不代表现场跑得通
# （HOME/uv 缓存属主就是这类坑）。
docker run --rm --user "${MIROTHINKER_SMOKE_UID:-1004}:${MIROTHINKER_SMOKE_GID:-1004}" \
  --entrypoint /bin/bash "$TAG" -lc '
  set -e
  /opt/mirothinker/.venv/bin/python - <<'"'"'PY'"'"'
import importlib
for name in ("uvicorn", "fastapi", "playwright", "numpy", "pandas", "pymilvus", "milvus_lite", "openai"):
    importlib.import_module(name)
print("python deps: ok")
PY
  /opt/mirothinker/.venv/bin/python - <<'"'"'PY'"'"'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    path = p.chromium.executable_path
import os
print("chromium:", path, "exists:", os.path.exists(path))
assert os.path.exists(path), "chromium 不在镜像里"
PY
  uv --version
  uv run --no-sync python -c "import sys; print(\"uv run ok:\", sys.version.split()[0])"
'

echo "== 导出镜像 tar =="
docker save "$TAG" -o "$TAR_PATH"
# 校验文件里写**相对文件名**：写绝对路径的话，现场 `sha256sum -c` 要么校验到打包机上的
# 另一个同名文件（打包机上），要么直接 "No such file or directory"（甲方机器上）。
( cd "$(dirname "$TAR_PATH")" && sha256sum "$(basename "$TAR_PATH")" > "$(basename "$TAR_PATH").sha256" )

# 压缩副本（网络传输用）。docker load 直接吃 .tar.gz：
#   docker load -i mirothinker-serving-v1.tar.gz
# 4.7 GB 的裸 tar 压缩后约 1/3，跨网传输明显划算；裸 tar 仍保留（校验/离线 U 盘）。
if command -v pigz >/dev/null 2>&1; then
  echo "== 生成 gzip 压缩副本（pigz，多线程）=="
  pigz -c -6 "$TAR_PATH" > "${TAR_PATH}.gz"
  sha256sum "${TAR_PATH}.gz" > "${TAR_PATH}.gz.sha256"
  gz_bytes="$(stat -c %s "${TAR_PATH}.gz")"
  echo "压缩副本：$(basename "${TAR_PATH}").gz = ${gz_bytes} bytes"
fi

cp "${REPO_ROOT}/deploy/docker/compose.yaml" "${KIT_DIR}/compose.yaml"
cp "${REPO_ROOT}/deploy/docker/README.md" "${KIT_DIR}/README.md"
# 凭据模板（真值在 secrets/，不入 git/镜像）
rm -rf "${KIT_DIR}/secrets.example"
cp -r "${REPO_ROOT}/deploy/docker/secrets.example" "${KIT_DIR}/secrets.example"
mkdir -p "${KIT_DIR}/secrets"
cat > "${KIT_DIR}/secrets/README.txt" <<'TXT'
把 4 个密钥文件放进本目录（文件名必须完全一致，0600，仅属主可读）：
  .deepseek_api_key   .bocha_api_key   .serper_api_key   .sglang_api_key
它们会被只读挂载到容器内 /opt/mirothinker/ 下同名位置。
TXT

commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo '<unknown>')"
{
  echo "kit: mirothinker-serving (container 交付 v1)"
  echo "built_at: $(date -Is)"
  echo "commit: ${commit}"
  echo "image_tag: ${TAG}"
  echo "image_id: ${image_id}"
  echo "image_size_bytes: ${image_size_bytes}"
  echo "image_size_human: ${image_size_human}"
  echo "build_seconds: ${build_seconds}"
  echo "tar: $(basename "$TAR_PATH")"
  echo "tar_bytes: $(stat -c %s "$TAR_PATH")"
  echo "tar_sha256: $(cut -d' ' -f1 "${TAR_PATH}.sha256")"
  if [[ -f "${TAR_PATH}.gz" ]]; then
    echo "tar_gz: $(basename "$TAR_PATH").gz"
    echo "tar_gz_bytes: $(stat -c %s "${TAR_PATH}.gz")"
    echo "tar_gz_sha256: $(cut -d' ' -f1 "${TAR_PATH}.gz.sha256")"
  fi
  echo "data_plane_not_included: serving-pack-run16-readerbound + index-v3-v2（约 7 GB，另行传输）"
} > "${KIT_DIR}/kit-manifest.txt"

echo "== kit 就绪 =="
cat "${KIT_DIR}/kit-manifest.txt"
