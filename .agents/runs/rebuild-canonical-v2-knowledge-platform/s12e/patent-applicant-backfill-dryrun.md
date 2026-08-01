# 专利申请人→发布公司回填 dry-run（s12e）

- Release: `candidate-s12c-20260726-r8`（DB `miroflow_candidate_s12c_20260726_r8`，容器 `canonical-v2-s12c-pg-20260726-r8`，只读 SELECT，`default_transaction_read_only=on`）
- Matcher: `apps/miroflow-agent/src/data_agents/canonical_v2/patent_applicant_linking.py`（exact + normalized 双通道，canonical 唯一性不足即 abstain）
- 目标：1855 条 `core_facts.company_ids` 为空的专利（全部 1931 条中 76 条已有链接）

## 结果汇总

| 指标 | 数量 |
|---|---|
| 扫描未解析专利 | 1855 |
| 申请人名总数 | 2006 |
| 索引发布公司 | 1037 |
| **接受的新链接（patent×company 去重）** | **45** |
| 其中 exact 通道 | 45 |
| 其中 normalized 通道 | 0 |
| 覆盖专利数 | 45（exact 45 / normalized-only 0） |
| 覆盖公司数 | 15 |
| abstain-ambiguous | 0 |
| abstain：abstained_non_company | 229 |
| abstain：abstained_suspected_person | 7 |
| abstain：abstained_company_not_in_release | 1725 |
| 投影后 patent_has_applicant | 76 → 121 |

## 一致性校验

- \[x\] released companies indexed（1037）
- \[x\] unresolved patents scanned（1855）
- \[x\] exact-lane patents reproduce the audited 45（45）
- \[x\] every accepted link resolves to one known canonical company（15）
- \[x\] zero ambiguous abstains（0）

## 接受链接全量清单

| 专利 | 专利标题 | 申请人名 | 命中公司 | 公司 canonical | 通道 |
|---|---|---|---|---|---|
| PAT-19160FA3C466 | 一种一体化关节电机模块及机器人 | 交浦科技(深圳)有限公司 | 交浦科技（深圳）有限公司 | company-c-7dc808ee800f0b9254002e7e | exact |
| PAT-1BE6D18FEC49 | 机器设备 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-20C329FC3DDE | 清洁模式确定方法、装置、计算机设备和存储介质 | 奇勃(深圳)科技有限公司 | 奇勃（深圳）科技有限公司 | company-c-5e6eda40d93fbd7ca40d1309 | exact |
| PAT-23846675E4B8 | 运动规划方法、装置、机器人、可读存储介质和程序产品 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-2E22A0BE0D5A | 媒体传输状态的检测方法、装置及计算机可读存储介质 | 盈合(深圳)机器人与自动化科技有限公司 | 盈合（深圳）机器人与自动化科技有限公司 | company-c-537bd2c13e91e9eb2e81a2ad | exact |
| PAT-30126F13C63B | 一种机械手指的连接结构、机械手及机器人 | 帕西尼感知科技(深圳)有限公司 | 帕西尼感知科技（深圳）有限公司 | company-c-0717a8386e2253a4b57ca90b | exact |
| PAT-37441787BA1D | 机器设备 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-4335B4391002 | 一种机械手指的连接结构、机械手及机器人 | 帕西尼感知科技(深圳)有限公司 | 帕西尼感知科技（深圳）有限公司 | company-c-0717a8386e2253a4b57ca90b | exact |
| PAT-45D6BB48F2A2 | 人脸识别模型训练方法、装置、电子设备及可读存储介质 | 盈合(深圳)机器人与自动化科技有限公司 | 盈合（深圳）机器人与自动化科技有限公司 | company-c-537bd2c13e91e9eb2e81a2ad | exact |
| PAT-4A97E26A1005 | 堆叠结构流体致动器 | 万勋科技(深圳)有限公司 | 万勋科技（深圳）有限公司 | company-c-e5d1f8c30a50245b02fdaab6 | exact |
| PAT-4B36A2DCF713 | 一种柔性电容传感器及其自动化设备 | 帕西尼感知科技(深圳)有限公司 | 帕西尼感知科技（深圳）有限公司 | company-c-0717a8386e2253a4b57ca90b | exact |
| PAT-524ECD5672C1 | 电流采样方法、电流采样控制装置及机器人 | 星尘智能(深圳)有限公司 | 星尘智能（深圳）有限公司 | company-c-bb1cf80221ffa1e54ff2953e | exact |
| PAT-5BD9D28BEA14 | 使用电池供电的设备及机器人 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-5FD1BA401CF2 | 抓夹 | 万勋科技(深圳)有限公司 | 万勋科技（深圳）有限公司 | company-c-e5d1f8c30a50245b02fdaab6 | exact |
| PAT-67DF4C85ABB0 | 一种散热机构及应用其的割草机器人 | 虎鲸(深圳)创新技术有限公司 | 虎鲸（深圳）创新技术有限公司 | company-c-9598fa5658a00980aceead30 | exact |
| PAT-721F1CB8E7F0 | 卡扣自动开合装置 | 盈合(深圳)机器人与自动化科技有限公司 | 盈合（深圳）机器人与自动化科技有限公司 | company-c-537bd2c13e91e9eb2e81a2ad | exact |
| PAT-818F86E3696C | 一种料盘浸泡式清洗装置 | 茵塞普科技(深圳)有限公司 | 茵塞普科技（深圳）有限公司 | company-c-f695ec6229f3b2a8a604aef9 | exact |
| PAT-8330AB8385FA | 一种对湿度不敏感的离电型柔性压力传感器及其制备方法和应用 | 赛感科技(深圳)有限公司 | 赛感科技（深圳）有限公司 | company-c-e3277385a2eeee04317806a3 | exact |
| PAT-833BE1BABC17 | 机柜及充电机器人 | 万勋科技(深圳)有限公司 | 万勋科技（深圳）有限公司 | company-c-e5d1f8c30a50245b02fdaab6 | exact |
| PAT-893F25076415 | 一种热水加注装置及洗地机器人基站 | 清云智能(深圳)有限公司 | 清云智能（深圳）有限公司 | company-c-7c28fb6c978b74260b8b2532 | exact |
| PAT-8ACF50056352 | 图片生成方法、装置、计算机设备和存储介质 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-8C2CF3367C66 | 一种模块化格斗舱 | 玄智(深圳)科技有限公司 | 玄智（深圳）科技有限公司 | company-c-859afba249d2874df997078d | exact |
| PAT-8F6CC41A2F53 | 一种跨场景自适应行人轨迹预测方法及设备 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-92363AD0B027 | 保护电路、待充电装置、机器人设备和供电系统 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-9CA64149EE2C | 料筐周转装置 | 盈合(深圳)机器人与自动化科技有限公司 | 盈合（深圳）机器人与自动化科技有限公司 | company-c-537bd2c13e91e9eb2e81a2ad | exact |
| PAT-9F035259269F | 控制电路、供电电路、通信电路和机器人设备 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-AC5B1DDA5952 | 传动机构及机器人 | 星尘智能(深圳)有限公司 | 星尘智能（深圳）有限公司 | company-c-bb1cf80221ffa1e54ff2953e | exact |
| PAT-B009958DEE21 | 适用于倾斜相机的机械手标定和空间角测量方法及机器人 | 昂视智能(深圳)有限公司 | 昂视智能（深圳）有限公司 | company-c-1aff9a564486269f1dedf348 | exact |
| PAT-B0D6B90395F2 | 供电控制电路、充电桩和供电系统 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-B51B75BC29B7 | 手腕结构、机械手臂和机器人 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-B86337B65B98 | 一种基于3D点云数据的物料边缘曲线标准化拟合方法 | 帝尔博格(深圳)智能科技有限公司 | 帝尔博格（深圳）智能科技有限公司 | company-c-a84f2999ea45e8a76bcdef31 | exact |
| PAT-BA99ACAEB395 | 导航地图和导航路径生成方法、装置、计算机设备及介质 | 深南电路股份有限公司 | 深南电路股份有限公司 | company-c-f48067ecfa0f1351bd9ae65a | exact |
| PAT-BBC096AFAEE2 | 自动化洁净柜 | 盈合(深圳)机器人与自动化科技有限公司 | 盈合（深圳）机器人与自动化科技有限公司 | company-c-537bd2c13e91e9eb2e81a2ad | exact |
| PAT-C39949ECEFD8 | 颈部机构及机器人 | 星尘智能(深圳)有限公司 | 星尘智能（深圳）有限公司 | company-c-bb1cf80221ffa1e54ff2953e | exact |
| PAT-C4ED7CD82D20 | 故障数据获取方法、装置、机器人、可读存储介质和程序产品 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-C7FFCE996586 | 一种语音通讯装置、语音通讯系统及机器人 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-C805A383D025 | 电机及格斗机器人 | 玄智(深圳)科技有限公司 | 玄智（深圳）科技有限公司 | company-c-859afba249d2874df997078d | exact |
| PAT-CBE5DF89D3ED | XYZ轴运动平台及充电机器人 | 万勋科技(深圳)有限公司 | 万勋科技（深圳）有限公司 | company-c-e5d1f8c30a50245b02fdaab6 | exact |
| PAT-D7384109AA7C | 下肢结构及双足机器人 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-E1F2261ED12C | 清洁模组 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-E55E477A1E73 | 一种利用微结构设计与材料调控实现传感器的传感性能协同增强的方法及其产品和应用 | 赛感科技(深圳)有限公司 | 赛感科技（深圳）有限公司 | company-c-e3277385a2eeee04317806a3 | exact |
| PAT-E90A597451BE | 水泵装置和清洁系统 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-E9C1E3D33AC4 | 回环检测方法和计算机设备 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |
| PAT-F4A13AE21926 | 绳驱传动机构和机器人 | 星尘智能(深圳)有限公司 | 星尘智能（深圳）有限公司 | company-c-bb1cf80221ffa1e54ff2953e | exact |
| PAT-FE95975C2464 | 清洁装置及其滚刷驱动机构 | 深圳市普渡科技有限公司 | 深圳市普渡科技有限公司 | company-c-831b0313360b2aa97dd291e1 | exact |

## abstain-ambiguous（唯一性不足，全部放弃）

无。

## abstain 分类示例（每类至多 10 例）

### 非公司实体（高校/研究院/医院/协会等）（229）

- PAT-01DD258DEEF1 「香港中文大学深港创新研究院(福田)」
- PAT-0612D5E1A540 「哈尔滨工业大学(深圳)(哈尔滨工业大学深圳科技创新研究院)」
- PAT-088EF35F84C3 「中国科学院深圳先进技术研究院」
- PAT-08B716615F55 「清华大学深圳国际研究生院」
- PAT-09FCE6757940 「中国科学院深圳先进技术研究院」
- PAT-0BD0C768DFB8 「哈尔滨工业大学(深圳)(哈尔滨工业大学深圳科技创新研究院)」
- PAT-0DBB94BEB8E7 「深圳先进技术研究院」
- PAT-0E56BC4F0EB5 「人工智能与数字经济广东省实验室(深圳)」
- PAT-0EA67C48050B 「北京大学深圳研究生院」
- PAT-105C7364D11D 「中山大学·深圳」

### 疑似个人（7）

- PAT-024EDD61AAC3 「黄誉」
- PAT-05091A5FE7A9 「王昕」
- PAT-9B258A77932A 「杨丹枫」
- PAT-A1399B3260C1 「杨一诺」
- PAT-A326ECA0363B 「刘静倩」
- PAT-C408C64455F2 「赵兵」
- PAT-DC0EEA45D9B5 「刘俊」

### 公司但不在发布集（1725）

- PAT-002EE94826BA 「深圳拓邦股份有限公司」
- PAT-004331BCE56B 「深圳市华成工业控制股份有限公司」
- PAT-004E9EA889BD 「深圳赛动智造科技有限公司」
- PAT-00B74391DD47 「深圳市华成工业控制股份有限公司」
- PAT-00E375D1CDA9 「深圳市欢创科技有限公司」
- PAT-014F5FB3824E 「中国平安人寿保险股份有限公司」
- PAT-015D207EDA08 「深圳市德泰兴自动化设备有限公司」
- PAT-01612B56AADD 「广东美房智高机器人有限公司」
- PAT-0168B7D2F3D2 「深圳市欢创科技股份有限公司」
- PAT-017AE89DEC6C 「深圳市零差云控科技有限公司」

______________________________________________________________________

声明：本脚本全部操作为只读 SELECT；未修改任何 DB、索引、仓库文件或运行中进程；未触碰 18188 服务。
