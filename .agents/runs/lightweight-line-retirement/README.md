# 轻量线退役记录（R19，2026-09-15）

> 用户裁定：**轻量线完全退役、下线不再保留**。
> 本目录保存退役时的关键文件副本；代码本体由 git 历史保留。

## 已退役实体（两批）

| 实体 | 位置 | 处置 | 证据 |
|---|---|---|---|
| `mirothinker-serve.service`（simple_serve，18190） | `~/.config/systemd/user/` → 单元文件 | stop + disable + 单元文件移除（副本见本目录） | 端口关闭、单元消失、数据线提交 `1ee824a7` |
| `simple_serve.py` | 数据线 run 目录 | `git rm` | 同上提交 |
| `SERVING_PACK_SKIP_HASH_VERIFY=1` 哈希校验旁路（dev 后门） | 数据线副本 8 处 | 清除（服务线从未携带） | 同上提交；pack-loader 19 测通过 |
| **light-lane 原型 API**（`light_lane/api.py`，18201） | 数据线 run 目录 | 进程停止 + `git rm`（副本见 `light-lane/`） | 端口关闭；数据线提交 `312a8beb` |

## 残留（未清，注明待定）

- 主 PG（容器 `canonical-v2-s12c-pg-20260726-r8`，端口 55458）中的两个数据库：
  **`miroflow_light_lane_r1`** 与 **`miroflow_light_lane_rehearsal`**——轻量线遗留，无消费者。
  **未删除**（不可逆操作，等用户决定；如要清，建议先 `pg_dump` 留档再 drop）。
- `miro-light-pg` Docker 容器：退役时已不存在（先前已清理）。
