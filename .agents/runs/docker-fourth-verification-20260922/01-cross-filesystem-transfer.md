# 命题 4（第 1 段）· 跨文件系统传送后的链路 —— 传输与校验

**判定：通过**（传输完整、逐文件一致；同时发现 1 个会拦住甲方手册第 ① 步的打包缺陷）

## 跑了什么

```bash
# 源（/，nvme0n1p2）→ 目标（/home，sda1）：真跨 fs，不是硬链接
mkdir -p /home/longxiang/delivery-xfer-v11
time cp -a /var/tmp/mirothinker-site-bundle-v11 ./site-bundle     # 3.4 GB
```

原始输出（`raw/01-copy.txt`）：

```
src: /var/tmp/mirothinker-site-bundle-v11 (fs: /dev/nvme0n1p2)
dst: /home/longxiang/delivery-xfer-v11/site-bundle (fs: /dev/sda1)
real  0m1.770s        ← 页缓存命中，落盘由内核延迟；真实完整性看下面的 sha256
dst bytes(du -sb): 3645060568 / src bytes: 3645076759
```

`stat` 复核：交付包 15 个文件 + `state/config-managed/settings.json`，两个大归档
2 162 962 373 B / 1 481 979 537 B，与源一致。

## 校验（`raw/01-verify.txt`、`raw/01-verify-manifest.txt`）

| 检查 | 命令 | 结果 |
|---|---|---|
| 镜像归档 | 记录值 vs `sha256sum` | `f842f6de…` **MATCH**（13 s） |
| 数据面归档 | 记录值 vs `sha256sum` | `beb9449d…` **MATCH**（8 s） |
| 逐文件（含两个大归档） | `BUNDLE-MANIFEST.txt` 的 17 条 file 行 → `sha256sum -c` | **17/17 OK**（21 s，exit 0） |

⇒ 跨 fs 拷贝出来的副本与交付清单**逐字节一致**，"传送损坏"这条风险在本次被排除。

## 顺带发现（缺陷 D2）：手册第 ① 步在甲方机器上会报错

`README-FIRST.txt` 第 ① 步原文是：

```bash
sha256sum -c mirothinker-serving-v1.1.tar.gz.sha256
sha256sum -c serving-data-v1.1.tar.gz.sha256
```

两个 `.sha256` 的格式**不一样**：

```
mirothinker-serving-v1.1.tar.gz.sha256 : f842f6de…  /var/tmp/mirothinker-docker-kit-v11/mirothinker-serving-v1.1.tar.gz
serving-data-v1.1.tar.gz.sha256        : beb9449d…  serving-data-v1.1.tar.gz
```

镜像那条写的是**打包机绝对路径**（连 kit 目录名都写进去了），于是：

- 在打包机上执行：`sha256sum -c` **exit 0 但校验的是 `/var/tmp/mirothinker-docker-kit-v11/…` 那个文件**，
  不是当前目录里的副本（实测输出：`/var/tmp/mirothinker-docker-kit-v11/mirothinker-serving-v1.1.tar.gz: OK`）；
- 在甲方机器上执行：同一路径不存在 ⇒
  `sha256sum: /srv/mirothinker-delivery/mirothinker-serving-v1.1.tar.gz: No such file or directory` +
  `WARNING: 1 listed file could not be read`（exit 1）——操作者会以为**包坏了**，实际是校验文件写错。

（3c 段用同格式、指向甲方路径的复现文件跑出上面这条原文；不是编造。）

**修（机制）**：`build-image.sh` 生成 `.sha256` 时改成相对文件名；`build-site-bundle.sh`
在把 kit 的 `.sha256` 放进交付包时再归一一次（即使 kit 是旧格式，出包也是对的）。
数据面那条本来就对（`build-data-face-kit.sh` 已经是 `cd $OUT && sha256sum basename`）。
v1.1 现货交付包的这个文件仍是绝对路径 ⇒ 现场遇到时用安装器（它只取第一列做比较，不受影响）。
