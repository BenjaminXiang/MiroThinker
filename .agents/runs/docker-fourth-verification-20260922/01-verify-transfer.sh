#!/usr/bin/env bash
# 命题 4：跨文件系统传送后的完整链路 —— 第 1 步：传输 + 校验
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
cd "$B" || exit 1

echo "== 0. 落点与来源 =="
echo "CWD=$PWD"
echo "src fs: $(df --output=source,avail -h /var/tmp/mirothinker-site-bundle-v11 | tail -1)"
echo "dst fs: $(df --output=source,avail -h "$B" | tail -1)"
echo "dst bytes(du -sb): $(du -sb "$B" | cut -f1) / src bytes(du -sb): $(du -sb /var/tmp/mirothinker-site-bundle-v11 | cut -f1)"
echo

echo "== 1. 两个大归档：与交付清单记录的 sha256 对比（传输完整性）=="
for pair in mirothinker-serving-v1.1.tar.gz serving-data-v1.1.tar.gz; do
  expected="$(awk '{print $1}' "${pair}.sha256")"
  t0=$(date +%s)
  actual="$(sha256sum "$pair" | cut -d' ' -f1)"
  printf '%s\n  recorded=%s\n  actual  =%s  (%s s, %s bytes)\n  -> %s\n' \
    "$pair" "$expected" "$actual" "$(( $(date +%s) - t0 ))" "$(stat -c %s "$pair")" \
    "$( [[ "$expected" == "$actual" ]] && echo MATCH || echo MISMATCH )"
done
echo

echo "== 2. 逐文件核对（BUNDLE-MANIFEST.txt 的 file 行 → sha256sum -c，相对路径）=="
awk '$1=="file" {print $4"  "$6}' BUNDLE-MANIFEST.txt > /tmp/bundle-manifest-check.txt
wc -l < /tmp/bundle-manifest-check.txt | sed 's/^/  manifest file 行数: /'
t0=$(date +%s)
sha256sum -c /tmp/bundle-manifest-check.txt
echo "  exit=$? （0 = 全部 OK；耗时 $(( $(date +%s) - t0 ))s）"
echo

echo "== 3. README-FIRST.txt 第 ① 步的原文命令，在传输后的副本上照抄执行 =="
echo "-- 3a. 数据面（.sha256 里是相对文件名）:"
sha256sum -c serving-data-v1.1.tar.gz.sha256; echo "  exit=$?"
echo "-- 3b. 镜像（.sha256 里是**打包机绝对路径**）:"
echo "  文件内容: $(cat mirothinker-serving-v1.1.tar.gz.sha256)"
echo "  本机执行:"
sha256sum -c mirothinker-serving-v1.1.tar.gz.sha256; echo "  exit=$?"
echo "  ↑ 注意它校验的是**哪一条路径**：不是本目录的副本。"
echo "-- 3c. 复现甲方机器上的情形（同一格式，但绝对路径在其机器上不存在）:"
sed 's#/var/tmp/mirothinker-docker-kit-v11#/srv/mirothinker-delivery#' \
  mirothinker-serving-v1.1.tar.gz.sha256 > /tmp/customer-view.sha256
echo "  模拟文件内容: $(cat /tmp/customer-view.sha256)"
sha256sum -c /tmp/customer-view.sha256; echo "  exit=$? （甲方看到的就是这个）"
