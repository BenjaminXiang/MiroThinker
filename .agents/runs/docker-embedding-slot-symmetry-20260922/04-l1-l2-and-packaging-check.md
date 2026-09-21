# L1 判决 + L2 修复 + 出包自检（2026-09-22，第三轮）

上一轮遗留清单里的 L1/L2 做掉，另加一条出包自检（L5 的建议，只做自检、不改文档）。

## 1. L1 判决：**CLI 赢** ⇒ 不是阻塞级；v2 预置里这一项也设成缺席（已做）

`paths.serving_pack_dir` → `CANONICAL_V2_SERVING_PACK`。两条读取路径分别判决：

**(a) 服务到底加载哪个包 —— `--serving-pack` 赢。**
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py::_parse_args`：

```
238    serving_pack = namespace.serving_pack                     # ← CLI --serving-pack
239    if serving_pack is None:                                   # ← 只有 CLI 缺席才看环境变量
240        environment_pack = os.environ.get("CANONICAL_V2_SERVING_PACK", "").strip()
241        if environment_pack:
242            environment_path = Path(environment_pack)
243            if not environment_path.is_absolute(): raise RunnerConfigurationError(...)
246            serving_pack = environment_path
```

镜像内的**交付代码**逐字一致（`/opt/mirothinker/.agents/runs/…/complete_candidate_runner.py:237-246`）。
而交付的冻结命令文件结尾永远是（`serve-command-v11.sh` 与其覆盖件）：

```
… --serve --serve-existing --serving-pack /var/tmp/mirothinker-data-v2/<包名>
```

容器里跑着的服务进程 `/proc/<pid>/cmdline` 也确认带着这个参数。
⇒ **受管预置改不了服务加载哪个包**（要改只能改冻结命令文件/compose 的覆盖件）。

**(b) 页面/探针看到的包身份 —— 活的站点走 runtime manifest，不看环境变量。**
`apps/admin-console/backend/services/canonical_v2_admin_status.py::collect_pack()`（:172-240）：

* 有 runtime manifest（正在服务时就是这种情况）⇒ `source: "runtime_manifest"`（:192-207）；
* 否则回落 `_SERVING_PACK_ENV`（:208-212 起读 `pack_dir/manifest.json`）；
* 两者都没有 ⇒ `unavailable`（:210-212，"…is not set and no runtime manifest is installed"）。

运行中实例实测（`/api/canonical-v2/admin/system-status`）：

```
pack.state = ok | source = runtime_manifest | pack_dir = /var/tmp/mirothinker-data-v2/serving-pack-run16-v11
```

⇒ 只有**没有 runtime manifest 的独立进程**（例如 switch 线 `canonical_v2_embedding_identity.py:243-244`
那种回落读法）才会被预置里的旧路径误导。

**结论与动作**：L1 = 卫生问题（非阻塞）。v2 预置里 `paths.serving_pack_dir` **也改缺席**
（`deploy/docker/site-config/managed-settings.json`，本轮已做），理由与 R1 同：版本相关路径不该由
预置替交付替操作者钉住；缺席时页面/探针会如实说"未配置"，而不是指向旧包目录。

**能判红的检查**：`apps/miroflow-agent/tests/canonical_v2/test_serving_pack_selection_precedence.py`
用**真的参数解析器**（从冻结 runner 文件加载）钉三条：CLI+env 同时给 ⇒ CLI；只给 env ⇒ env；
都不给 ⇒ None。判红演示（把 runner 复制一份、只把优先级反过来，`raw/08-precedence-mutation.txt`）：

```
MUTATION: serving_pack = None; if True:  →  1 failed, 2 passed
FAILED test_cli_pack_wins_over_the_environment
```

（测试支持 `MIROTHINKER_TEST_RUNNER_PATH` 指向别的 runner 文件，便于这种 mutation/回归对照。）

## 2. L2 修复：安装器探针的模型 id 取自**随包 bundle**

**从哪个 bundle 取、依据**：安装器在**解包之前**就跑探针（第 1 步），此刻它只能看到交付包目录里的
`BUNDLE_DIR/bundles/qwen-embedding-bundle-v1.json` —— 而这个文件**本来就已经**提供 base_url 与
dimension，且它带 `model_id`（v1.1 实测 `Qwen/Qwen3-Embedding-8B`；v2 随包换成候选模型）。
所以取这份（而不是服务包 manifest 的 `embedding_model_id`：那要解包后才读得到，且它是**服务线身份**，
与"探针要打的端点"未必同一个 bundle）。

改动（`deploy/docker/install-site.sh`）：

* 一次 `mapfile` 读 `base_url` / `dimension` / `model_id` 三个字段；
* 请求体 `-d "$(python3 -c '…json.dumps({"model": sys.argv[1], "input": ["安装器探针"]})' "$emb_model")"`；
* 三个字段缺一 ⇒ **跳过探针并说明**（"随包 bundle 缺 base_url/dimension/model_id 之一…探针不猜模型"），
  不再回落到任何写死的模型 id。

其它写死值：`grep -n "Qwen\|4096\|1024\|100\.64" deploy/docker/install-site.sh` 现在只剩
`/proc/meminfo` 的 `1024` 换算（假命中）⇒ 安装器里没有写死的嵌入身份值了。

**测试**（行为级，本地假端点收请求体）：`apps/miroflow-agent/tests/canonical_v2/test_install_site_embedding_probe.py`
* 模型 id 与维度都不是 v1 值的假 bundle + 假端点 ⇒ 断言探针请求的 `model` == bundle 的 `model_id`，
  且判定用 bundle 的维度（3 维也不会报黄灯）；
* bundle 缺 `model_id` ⇒ 不发请求、打印跳过说明。
判红演示（同一个测试指向修前的 `install-site.sh`，其 `install-site.sh:233` 仍写死）：
`raw/09-packaging-check.txt` D 段 → **2 failed**。

## 3. 出包自检（新增 `deploy/docker/check-delivery-consistency.py`，挂进 `build-site-bundle.sh`）

只做"**同包内自洽**"（不判断 v1/v2），两档：

* **硬**（exit 1，拦下出包）：预置不许钉 `extraction_endpoints.embedding_base_url` / `embedding_model`
  （地址那条会覆盖 bundle 记录的地址；模型那条会误导页面）；
* **软**（只报，file:line）：文档/脚本里的嵌入端点、"维度 N"、模型 id、服务包名与**随包 bundle/清单**
  不一致时逐条列出（端点/模型/维度优先打印，包名在后；去重 + 上限 12 条）。

实测三段（`raw/09-packaging-check.txt`）：

| 场景 | 结果 |
|---|---|
| A. v1.1 现货包（副本） | 9 条 warn（8 条是 README 里 v1.0 时代的包名 + 1 条预置钉了 `serving_pack_dir`），**exit 0**；把预置刷新成本轮版本后那一条消失 → 8 条 |
| B. 合成 v2 包（bundle 换成网关/1024，文档仍是 v1 数字） | 4 条精确 warn：端点、模型 id、维度 4096、包名，**exit 0** |
| C. 预置钉住嵌入地址 | **exit 1** + `[FAIL] …预置不许替操作者决定嵌入地址/身份…` |

测试：`apps/miroflow-agent/tests/canonical_v2/test_delivery_consistency_check.py`（4 条：出包脚本确实调用它、
硬规则会红、不一致会报、自洽时不报）。

## 4. 没验到 / 留给 v2

* "真候选路由 + 真网关"的端到端仍归 v2（本分支没有候选路由代码）；本轮只把**安装期/交付期**的
  两个会咬人的点修掉（探针假黄灯、预置钉地址）。
* `MIROTHINKER_SITE_LLM_PROBE` 走的是 chat LLM 端点（默认 deepseek），与嵌入身份无关，未动。
* 出包自检的"软"档不保证零误报（例如 README 里作为历史/示例出现的旧包名）——它是**提醒**，
  不是门禁；硬档才是门禁。
