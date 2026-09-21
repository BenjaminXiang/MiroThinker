# Canonical V2 服务栈容器镜像（交付 v1，冻结点 delivery-v1 = 36df47b8）。
#
# 构建（在仓库根目录执行，context 必须是仓库根）：
#   docker buildx build --load \
#     -f deploy/docker/Dockerfile \
#     -t mirothinker-serving:v1 .
# 或直接用 deploy/docker/build-image.sh（它同时产出可网络传输的镜像 tar）。
#
# 设计要点：
#   * 基础镜像 Ubuntu LTS，镜像内自带 python3.12 + uv + .venv（构建期 `uv sync`）+
#     Chromium 及其系统依赖 ⇒ 现场不需要 apt、不需要 PyPI、不需要 uv sync。
#   * 代码落在镜像内固定路径 /opt/mirothinker；editable 指针因此指向容器内路径，
#     不会带上构建机的绝对路径。
#   * 冻结的「账本/门禁」绝对路径在镜像内直接创建（其中有 2 个真实小文件随镜像 COPY），
#     现场不必为了满足解析期的存在性检查去铺一堆空目录。
#   * 数据面（服务包 / 索引根）不进镜像，运行期按冻结绝对路径 bind mount。

FROM ubuntu:24.04

# uv 固定版本，避免构建不可复现
ARG UV_VERSION=0.9.27
ENV DEBIAN_FRONTEND=noninteractive

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    # 只用镜像内的系统 python3.12，不让 uv 去下载托管解释器
    UV_PYTHON=/usr/bin/python3.12 \
    UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy \
    # 环境已在构建期固化：运行期禁止 uv 改锁、禁止 uv 出网
    UV_FROZEN=1 \
    UV_OFFLINE=1 \
    # 三份 pyproject（根 / miroflow-agent / admin-console）共用根 .venv，
    # 避免运行期 `uv run` 在没有外网的机器上现场建第二个 venv
    UV_PROJECT_ENVIRONMENT=/opt/mirothinker/.venv \
    # Chromium 装在全局可读路径：容器以非 root uid 运行时也能找到浏览器
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    # 运行期 HOME（uv/python/chromium 都要可写 HOME）；粘滞位，任意 uid 均可用
    HOME=/var/tmp/mirothinker-home

# python3.12 + venv + 构建依赖 + curl/ca-certificates + pip（装 uv 用）+ tini（容器 init）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      python3-pip \
      python3.12 \
      python3.12-venv \
      python3.12-dev \
      tini \
 && rm -rf /var/lib/apt/lists/*

# uv（固定版本）。走 PyPI 而不是 astral 安装脚本：安装脚本要去 GitHub release
# CDN 取二进制，本机实测在容器内会长时间挂住；PyPI 这条路稳定且可复现。
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python3.12 -m pip install --break-system-packages "uv==${UV_VERSION}" \
 && uv --version

WORKDIR /opt/mirothinker

# 代码树（.dockerignore 排除了 .git/.venv/htmlcov/report.html/.tmp-*/缓存）
COPY . /opt/mirothinker/

# 就地重建 Python 环境：editable 指针解析到 /opt/mirothinker 下的成员包。
# 构建期需要外网（PyPI）；现场完全不需要 —— 所以这一步显式关掉镜像里的 UV_OFFLINE。
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_OFFLINE=0 uv sync --frozen --no-progress

# Chromium（tier-1 网页渲染）+ 其系统依赖。必须是 root 执行；装到
# PLAYWRIGHT_BROWSERS_PATH（全局可读），使非 root 运行的用户也能用。
# 浏览器包从 cdn.playwright.dev 取（构建期外网），与 uv 的 registry 无关。
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_OFFLINE=0 uv run --no-sync playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# 上面这条以 root 跑，会往 HOME 里写 uv/chromium 的缓存目录（root 属主）。
# 运行期容器是非 root（数据属主 uid），那些目录对它不可写 ⇒ 清掉，
# 让运行期用户在自己的 HOME 里建（否则 `uv run` 直接报
# "Failed to initialize cache … Permission denied"）。
RUN rm -rf /var/tmp/mirothinker-home/.cache /var/tmp/mirothinker-home/.config \
           /var/tmp/mirothinker-home/.local /var/tmp/mirothinker-home/.npm \
 && chmod 1777 /var/tmp/mirothinker-home

# 冻结账本/门禁路径（服务期真正会被 stat/读取的绝对路径）。
# 说明见 deploy/docker/README.md「镜像内的冻结账本路径」：
#   * s12a/、s12c/ 目录 + 两个真实小文件：解析期与运行期会读（哈希绑定）；
#   * source-build-manifest-p4.json 的父目录、s12a 门禁根：只在解析期要求存在；
#   * canonical-v2-s11-consolidation → /opt/mirothinker：让冻结命令文件里的
#     代码绝对路径（启动脚本被调用路径、--recorded-serving-bundle）原样成立，
#     从而**不改一行**冻结命令文件。
RUN mkdir -p \
      /var/tmp/mirothinker-data-v2 \
      /var/tmp/mirothinker-canonical-v2-s12f \
      /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a \
      /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c \
      /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild \
      /var/tmp/mirothinker-home \
      /opt/ms-playwright \
 && chmod 1777 /var/tmp/mirothinker-home \
 && ln -s /opt/mirothinker \
      /home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation

# 两个「解析期真正会读」的账本小文件（内容非机密：嵌入端点/模型/维度；决策包为空集）。
# 取自重建树的同名文件，字节一致；sha256 见 deploy/docker/README.md。
COPY deploy/docker/ledger/s12a/recorded-decision-bundle-v1.json \
     /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/recorded-decision-bundle-v1.json
COPY deploy/docker/ledger/s12c/qwen-embedding-bundle-v1.json \
     /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/qwen-embedding-bundle-v1.json

# 交付工具（容器内自检：/chat、/main、/api/health、嵌入探针 200 + 4096 维；
# replay 回归门；入口预检）
COPY deploy/docker/verify.sh /usr/local/bin/mirothinker-verify
COPY deploy/docker/replay.sh /usr/local/bin/mirothinker-replay
COPY deploy/docker/entrypoint.sh /usr/local/bin/mirothinker-entrypoint
RUN chmod 0755 /usr/local/bin/mirothinker-verify /usr/local/bin/mirothinker-replay \
              /usr/local/bin/mirothinker-entrypoint

# 服务进程在容器内固定监听 18188（冻结命令文件把端口钉死在 18188，端口映射交给 compose）
EXPOSE 18188

# 以非 root 运行（uid/gid 由 compose 指定）。注意这里故意不写死数字：
# 现场数据属主是谁，就用谁的 uid —— 见 README「uid / 权限」。
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/mirothinker-entrypoint"]
