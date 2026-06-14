import pytest

from src.data_agents.paper.title_cleaner import clean_reference_like_paper_title
from src.data_agents.paper.title_quality import is_plausible_paper_title


@pytest.mark.parametrize(
    "title",
    [
        "Attention Is All You Need",
        "Deep Residual Learning for Image Recognition",
        "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "Neural Machine Translation by Jointly Learning to Align and Translate",
        "Graph Attention Networks",
        "A Survey on Large Language Models for Education",
        "基于深度学习的图像识别方法研究",
        "面向智慧医疗的多模态数据融合模型",
        "面向自动驾驶的三维目标检测方法",
        "融合知识图谱与大语言模型的问答系统研究",
        "基于Transformer的中文长文本分类研究",
        "面向工业质检的 Vision Transformer 缺陷检测方法",
        "Learning to Select Best Paper Candidates in Academic Conferences",
        "The Human Genome Project and Modern Biomedical Data Integration",
        "国家重点研发计划成果的知识图谱表示学习方法",
        "Concurrent Ferroptosis and Pyroptosis Induced by a Dual-Organelle-Targeted Type I/II AIE Photosensitizer for Bladder Cancer Immunotherapy",
        "An Ultra-Local Model-Based Control Method With the Bus Voltage Supervisor for Hybrid Energy Storage System in Electric Vehicles",
        "Joint Propulsion and Cooling Energy Management of Hybrid Electric Vehicles by Optimal Control",
        "Student Performance Prediction Using Deep Learning and Behavioral Data",
        "Committee Neural Networks for Robust Image Classification",
        "COVID-19 in 2020: No Evidence for Increased Transmission in Schools",
        "No Evidence for Increased Transmission in Schools in 2020",
    ],
)
def test_accepts_real_paper_titles(title: str):
    assert is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "raw",
    [
        "On the existence of global vortex rings, J. d’Analyse Math",
        "(with B. Gidas and L. Nirenberg) Symmetry and related properties via the maximum principle, Comm",
        "l1kdeconv: an R package for deconvolution of bulk DNA methylation data. BMC bioinformatics, 18, 1-7",
    ],
)
def test_cleaned_recoverable_reference_titles_remain_plausible(raw: str):
    cleaned = clean_reference_like_paper_title(raw)

    assert cleaned != raw
    assert is_plausible_paper_title(cleaned), cleaned


@pytest.mark.parametrize(
    "title",
    [
        "Heng Tan, Hao Wang, Qingyuan Zhu, Rui Xu, Fengyi Wu, Jinsong Liu",
        "(3)Hao Liu; Hanlong Zhang; Xiaoxi Nie; Wei He; Dongmei Zhang",
        "L. B. Ju; Taiwu Huang; Ran Li; K. Jiang; Chaoneng Wang",
        "ACM SIGMOD China主席、IEEE Transactions on Knowledge and Data Engineering Associate Editor",
    ],
)
def test_rejects_round_7_12_prime_real_bad_titles(title: str):
    assert not is_plausible_paper_title(title), title


def test_rejects_publication_table_excerpt_title():
    assert not is_plausible_paper_title(
        "2019年代表性论文序号论文名称期刊时间作者 1 A distributed data "
        "management system to support large-scale data analysis The Journal "
        "of Systems & Software 20"
    )


@pytest.mark.parametrize("title", [None, "", " ", "Short7!"])
def test_rejects_missing_or_tiny_titles(title):
    assert not is_plausible_paper_title(title)


def test_rejects_titles_longer_than_300_chars():
    title = "Graph representation learning " * 12
    assert len(title) > 300
    assert not is_plausible_paper_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Alice Smith; Bob Chen; Carol Wang; David Li; Eve Zhang",
        "WANG, Hao; LI, Jun; XU, Rui; ZHU, Qingyuan",
    ],
)
def test_rejects_author_lists_with_many_semicolons(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "(12)Alice Smith and Bob Chen",
        "(3)Hao Liu; Hanlong Zhang",
    ],
)
def test_rejects_digit_prefix_author_shapes(title: str):
    assert not is_plausible_paper_title(title), title


def test_rejects_editorial_bio_not_paper_title():
    """'ACM SIGMOD China主席、IEEE TKDE Associate Editor' is an editorial bio."""
    assert not is_plausible_paper_title(
        "ACM SIGMOD China主席、IEEE TKDE Associate Editor"
    )


@pytest.mark.parametrize(
    "title",
    [
        "A representative result of my works is the article Planar Carrollean dynamics",
        "Highlighted in SUSTech News",
        "Highlighted in X-MOL",
        "Associate Editor",
    ],
)
def test_rejects_homepage_prose_and_highlight_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "30万元, 在研, 主持",
        "2022中国博士后科学基金会博士后国际交流引进计划",
        "国家重点研发计划：服务机器人云服务平台，任务负责人",
        "2023年，入选CCF Fellow",
        "山东省重点研发计划：智能装卸车机器人系统关键技术研究与应用，项目负责人",
    ],
)
def test_rejects_suat_project_honor_and_talent_plan_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Applied Catalysis B: Environmental",
        "Muhammad-Sadeeq (Jie Tang) Balogun",
    ],
)
def test_rejects_suat_venue_only_and_person_alias_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "International Journal of Human-Computer Studies",
        "International Journal of Human–Computer Studies",
        "ACM Transactions on Evolutionary Learning and Optimization",
        "ICML/NeurIPS/ICLR",
        "IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2018",
        "IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2023",
    ],
)
def test_rejects_seed47_standalone_venue_and_conference_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Best Paper",
        "TPC Co-Chair",
        "更新时间：2024-03-19",
    ],
)
def test_rejects_szu_seed18_award_role_and_update_metadata(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "IF= 11.301 (JCR1)",
        "中科院大类 1 区， IF = 14.7",
        "11774241, 62万元",
        "主持深圳市项目一项",
        "【 Patents 】",
        "教师考评优秀",
        "Electrochim",
        "Fabrication",
        "poly(3",
        "poly(9",
    ],
)
def test_rejects_szu_seed15_metric_grant_patent_and_truncated_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "IF: 6.578 (JCR1)",
        "(IF=7.311)",
        "(中科院 1 区 Top",
        "66(2), 696-706. 中科院大类 2 区， IF = 6.8",
        "Conductivity and mechanical properties of conductive adhesive with silver "
        "nanowires Rare Met. (2016). IF: 1.785 (JCR2) 2015",
        "湖北省国际科技合作项目, 2021EHB006",
        "国家科技基础条件平台建设项目, 2005DKA10400-Z12",
        "深圳市高端人才科研启动经费（2016年立项，已结题）",
        "上海市青年科技启明星人才计划",
        "近年来深圳大学年度教师考评优秀（2023，2024）",
        "符合条件的博士后人员在站期间可按以下情况给予在站生活补助之一：符合广东省海外博士后人才支持项目",
    ],
)
def test_rejects_szu_seed15_adjacent_metric_grant_and_award_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "pp. 184--192",
        "陈海强、韩乾、吴锴，2012，现金流波动、融资约束与企业投资行为研究，第181-194页。 部分英文发表",
        "IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2023",
        "Sensors and Actuators B: Chemical",
        "李熙莹，陈玲，一种基于显著性分析的车辆颜色识别方法. ZL201310343195.5",
        "UV resistant/flame retardant composites for application in cable. Patent NO.: ZL 2022102758009, China. （授权）",
        "24级硕士： Mingyang Liu （ 第一作者发表 NeurIPS两篇、ICCV一篇）",
        "Category Quartile:Q2",
        "Representative Publication",
        "Book Chapter",
        "Selected recent works",
        "He, GJ; Chen",
    ],
)
def test_rejects_runtime_audit_cross_seed_pollution_examples(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Shenzhen high-level professional talent",
        "Conference of the North American Chapter of the Association for Computational Linguistics (NAACL-HLT)",
        "Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP)",
        "主持教育部产学研协同育人项目3项、省级教改项目3项",
        "Committee Member, Program Committee, Senior Program Committee",
        "Research interests include computer systems, database systems, and distributed computing",
        "Selected service: Area chair for top conferences and reviewer for journals",
    ],
)
def test_rejects_seed19_29_profile_venue_project_and_service_pollution(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "课题组实验室情况详见课题组主页",
        "更多论文和课题组成员情况详见实验室主页",
    ],
)
def test_rejects_seed37_homepage_group_navigation_prose(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "H∞ filtering for discrete fuzzy stochastic systemAn industrial-based "
        "framework for distributed control of heterogeneous network systemss "
        "with randomly occurred sensor nonlinearities",
    ],
)
def test_rejects_seed37_concatenated_multi_title_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Research Interests: computer systems, database systems, and distributed computing",
        "Research Interests Computer Systems Database Systems Distributed Computing",
        "深圳市高层次专业人才",
        "主持国家自然科学基金项目2项、省部级项目3项",
        "PC member for ACL 2024, EMNLP 2023 and NAACL 2022",
        "Senior PC member for AAAI and IJCAI",
        "担任ACL 2024程序委员会委员",
        "Selected Publications",
        "Research Projects",
    ],
)
def test_rejects_seed19_29_profile_service_and_section_label_variants(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Autonomous Agents and Multi-Agent Systems (JAAMAS)",
        "IEEE Transactions on Knowledge and Data Engineering (TKDE)",
        "Xingshan Zeng and Kam-Fai Wong",
        "Kam-Fai Wong",
        "Behrouz Minaei-Bidgoli",
        "Annual Conference of the Nations of the Americas Chapter of the ACL (NAACL)",
        "2022年广东省一流本科课程，负责人（排第一）",
        "主要教学获奖及教学教改",
        "全球前2%顶尖科学家",
        "IEEE高级会员（Senior Member）",
        "吴文俊人工智能科学技术奖（第一发明人）",
        "一种手势信息处理方法",
        "基于联邦学习的脑电信号分类模型训练方法及装置",
        "中国第一个微机集群大型操作系统的研制者",
        "历任中国计算机学会学术委员会副主任",
    ],
)
def test_rejects_seed6_19_29_leaked_resolver_candidate_pollution(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Meitong Dong, Wang",
        "(2024): The essentialist gender assumptions and the overgeneralization "
        "of managerial power’s impact on perceptions of organizational justice. "
        "Group & Organization Management. (ABDC A, ABS 3, SCI Q1, IF=4.8)",
    ],
)
def test_rejects_title_backfill_author_and_citation_metadata_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Constructions of Optimal Cyclic (r",
        "What C an RL B ring to VLA G eneralization? A n E mpirical St udy",
        "Taoshu, Jiushuang Zhang",
    ],
)
def test_rejects_sigs_truncated_broken_spacing_and_author_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "杨舰主编《科学方法》",
        "梁波译《科学的社会史》",
        "杨舰、戴吾三编著《历史上的科学名著》",
        "朱晨著《微纳世界中国芯——李志坚传》",
        "Jian Yang and Lewis Pyenson Compatible Humanists: Yuen Ren Chao Meets George Sarton Isis A",
        "Wang lei, Yang Jian Process and Impact of Niels Bohr's Visit to Japan and China in 1937: A Comparative Perspective Endeavour 2017 Vol. 41 No. 1 ， pp.12-22",
        "中国环境科学研究热点及其演化——基于文献计量学方法的量化分析”《 科学学研究》 2016 Vol.34 (9): pp.1294-1300",
        "Implementing Sponsored Search in Web Search Engines: Computational Evaluation of Alternative Mechanisms, with Hemant Bhargava and David Pennock, Informs",
    ],
)
def test_rejects_book_translation_and_citation_tail_records(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "83, December 2014",
        "Elsevier, 2012",
        "Kuruoglu and Kevin Knuth (ed.)",
        "Magnet-Assisted GaN Monolithically Integrated Device..., ACS Photonics, vol",
        "Datian Ye, An approach to the correspondence problem in the 1-D optical transducers tracking system",
        "Lieber has published over 420 articles in peer-reviewed scientific journals",
        "一种计算隔舱式双钢板 - 混凝土组合结构的抗弯承载力的方法...授权发明专利",
        "Selected Professional Activities... Reviewer for SIGMOD 2027",
        "DOI: 10.1016/j.ijmecsci.2025.110087 (Q1",
        "Human cytomegalovirus... 继续了解>> 本科招生人才招聘科研平台",
    ],
)
def test_rejects_sigs_and_sustech_metadata_prose_patent_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Jingying Zhai",
        "Jiang Pi 4",
        "Muir, Appl. Numer. Math, Vol 50",
        "Muir, ACM Trans. Math. Softw, Vol 30",
        "Muir, J. Comput. Appl. Math, Vol 169",
        "vol. 31, no. 8, pp. 953 - 956",
        "A Wide Angle and Circularly Polarized Beam Scanning Antenna Based on "
        "Microstrip Spoof Surface Plasmon Polariton Transmission Line, "
        "IEEE Antenn. Wireless Propag. Lett, vol. 16, pp. 2538 - 2541",
        "Muscle Connectivity Analysis for Hand Gesture Recognition via "
        "sEMG[C/OL]//2018 Asia-Pacific Signal and Information Processing "
        "Association Annual Summit and Conference (APSIPA ASC)",
        'Phosphoric Acid-Catalyzed Asymmetric Classic Passerini Reaction" J. Am',
    ],
)
def test_rejects_sustech_author_volume_and_citation_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Palaeogeography, Palaeoclimatology",
        "Annealing synchronizes the 70S ribosome into a minimum-energy",
        "(2012.). Oracle model selection for nonlinear regression",
        "Advanced filtering for RF systems, IEEE Trans. Microw. Theory Tech, vol. 65",
        "Toxicity and accumulation of",
        "PCT/SG2022/050487",
    ],
)
def test_rejects_sustech_seed9_surviving_pollution_examples(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "脑电信号分类方法",
        "一种视频处理方法及装置",
        "图像渲染处理方法",
        "图像处理方法及装置",
        "运动想象脑电信号的处理方法和装置及存储介质",
        "一种基于深度学习的模型训练方法以及相关装置",
        "12：多模态视觉跟踪中端到端表征学习研究 (62006245)",
        "仿生假肢手感知与控制的神经信息解析和交互技术研究——神经信号编码与假肢手柔顺运动控制",
        "基于柔性传感的假肢手感觉信号检测及感觉神经反馈方法研究",
        "曾以第一作者身份，获得视觉目标跟踪领域VOT-RGBT 2019国际竞赛冠军",
        "理论与实际相结合，研制了一些列软件系统",
        "率先设计了计算机机群计算系统",
        "Yu: Mining Top-K Large Structural Patterns in a Massive Network. Proc. VLDB Endow",
        "Qiang Qu: Opinion leader detection: A methodological review",
        "Muhammad Muzamma：On Spatio-temporal Blockchain Query Processing",
        "l1kdeconv: an R package for deconvolution of bulk DNA methylation data. BMC bioinformatics, 18, 1-7",
    ],
)
def test_rejects_suat_seed29_surviving_pollution_examples(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "On the existence of global vortex rings, J. d’Analyse Math",
        "(with B. Gidas and L. Nirenberg) Symmetry and related properties via the maximum principle, Comm",
        "25 (3): bbae208",
        "in-hospital analysis",
        "Chinese guidelines for the diagnosis and treatment of hand",
    ],
)
def test_rejects_cuhk_seed35_surviving_pollution_examples(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Selected as Cover pictures",
        "Turing Lecture slides",
        "Invited paper",
        "Selected research articles",
        "Sci. China Chem",
        "Aging-US. 2019 May 13;11(9):2812-2821. doi: 10.18632/aging.101953",
        "Iss 4 (Aug) pp. 1679 – 1728",
        "创建中国科学院深圳先进技术研究院与深圳广道数字有限公司大数据与AI联合实验室",
        "美国健康研究院NIH R01 项目负责人",
        "美国国家科学基金NSF IIS-1910492 项目负责人",
        "J. Zhang 1, W. Wang 1, J. Zhu, K. Wang, H. Sun, ACS Nano, Vol.18, No",
    ],
)
def test_rejects_seed_audit_remaining_section_venue_grant_and_citation_noise(
    title: str,
):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Springer LNCS 3483",
        "Springer LNAI 12000",
        "Springer CCIS 873",
    ],
)
def test_rejects_publisher_series_volume_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "一种萘环改性的含芴聚芳醚及其合成方法，200710124809.5",
        "Method and device for monitoring a machine store",
        "一种用于经皮肾镜取石术的机器人辅助穿刺系统研究",
        "Microgels: Synthesis, Properties and Applications (Chapter 12",
        "Janeway’s Immunobiology: Chapter 15",
        "Full paper list available at My Goolge Scholar",
        "Full paper list available at My Google Scholar",
        "Traffic resilience in urban transportation systems: Reliability Engineering & System Safety, 110095",
        "Domain decomposition methods for nonlocal problems, IMA J. Numer. Anal.. 41(3):2139-2185 (2021)",
        "BreakID: A computational method to identify chromosomal breakpoints, Bioinformatics",
    ],
)
def test_rejects_subagent_audit_patent_chapter_profile_and_citation_noise(
    title: str,
):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Email ： wangtao35@mail.sysu.edu.cn",
        "指导大学生创新创业训练计划项目获得优秀 2 组",
        "指导本科生毕业设计获得校级优秀和院级优秀各 1 人",
        "深圳市龙岗区深龙英才 C 类人才 (2020.08)",
        "国家青年人才项目（2023 ）",
    ],
)
def test_rejects_seed36_contact_teaching_and_talent_profile_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "广东省量子科学战略专项重点项目 2024-2027",
        "He received his B.S",
        "K Wang, W Sun",
        "Hasan Y？lmaz",
        "Y？lmaz Hasan",
        "electrochromic",
        "Influence of",
        "哈工大青年拔尖启动项目 2023-2025",
        "ResearcherID",
        "JinhongGuo.* Biomarkers detection with magnetoresistance-based sensors",
        "Xing M a*. Nanomaterial Labels in Lateral Flow Immunoassays for Point-of-Care-T esting",
        "Hasan Y？lmaz, Shumin Xiao*",
        "Y？lmaz Hasan, Xiao Shumin",
        "Chan, Xianglin Ke / Sazio, Chaoxing Liu / Haesendonck",
        "Stretchable ultrasonic transducer arrays for three-dimensional imaging on complex surfaces Sheng Xu*",
    ],
)
def test_rejects_seed20_project_bio_author_and_truncated_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "基于NTP协议的授时系统研究 1996-2000 获工学学士学位（通信与信息系统），北京师范大学学位论文：基于GPS和广播的授时系统",
        "2024 Huawei: Peng*",
        "2026 Huawei: Hu**, Bian**, Ren**",
        "etc, Nano Features of Al/Au Ultrasonic Bond Interface Observed by High Resolution Transmission Electron Microscope",
        "Haijun Tang(1), Can Huang(1,*), Yuhan Wang, Xiong Jiang, Shumin Xiao, Qinghai Song.* Dynamically Tunable Long-range Coupling Enabled by Bound State in the Continuum",
        "？, Jingsong Fu1",
        "Lett. 114. 146802 (2015)",
        "ACS Energy Lett",
        "ACS na no 2020",
        "T. ？ kereň",
        "High-Density and Uniform Lead Halide Perovskite Nanolaser Array on Silicon,K Wang, Z Gu, S Liu, W Sun, N Zhang, S Xiao*, Q Song*,The",
        "Improving the performances CH3NH3PbBr3 perovskite microrod laser through hybridization with few-layered graphene, Advanced Optical Materials, C Zhang, K Wang, N Yi, Y Gao, M Zhu, W Sun, S Liu, K Xu,Q Song*,S Xiao*, In Press",
        "Yuri Kivshar*& Shumin Xiao*. Highly efficient vortex generation at the nanoscale",
        "Lead halide perovskite vortex microlasers (vol 11",
        "Lett. 35. 1425 (2010)",
    ],
)
def test_rejects_seed20_remaining_candidate_pollution(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Selected List",
        "Representative works",
        "Selected Examples of Recent Publications (in recent five years)",
        "Selected Examples of Invited Review Articles (in recent five years)",
        "stands for equal contributions",
        "Note: and label the co-first authors and co-corresponding authors respectively",
        "(*Correspondence author)",
        "Nanyang Technological University",
        "XIAO Yunyun",
        "AFTER joining CUHKSZ",
        "32 (10): e4758",
        "50 (D1): D460-D470",
        "33 (6): e5006",
        "no. 4, pp",
        "Unconstrained face recognition, Ph.D",
        "Wavelet-based texture retrieval and modeling visual texture perception, M.S",
    ],
)
def test_rejects_cuhk_heading_legend_profile_and_volume_noise(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Book chapters",
        "IEEE Transactions on Information Theory, vol. 67, no. 8, pp. 5212-5224",
        "Nature Communications 12, 3456",
        "25 (3): bbae208",
    ],
)
def test_rejects_cuhk_myweb_title_only_venue_volume_page_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Sparse_matrix factorization for graph signal processing",
        "Learning with L_2 regularization and H_infinity constraints",
    ],
)
def test_accepts_real_titles_with_underscores_or_math_tokens(title: str):
    assert is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Uncovering, Explaining and Predicting Defects in Software Systems",
        "Proc. Macro Expansion for Reproducible Build Systems",
        "Sparse Matrix-Vector Multiplication: From O(n log n) to O(n)",
        "Learning VLDB-Style Query Plans for Modern Data Systems",
    ],
)
def test_accepts_comma_proc_math_and_venue_like_real_titles(title: str):
    assert is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        "Selected professional activities: program committee member of AAAI",
        "主要从事人工智能与机器人领域的教学科研工作",
        "承担本科生课程《机器学习》教学工作",
        "Yu Zhang and Wei Li",
        "Wang, Li, Zhang",
        "Machine Learning Course",
        "Linear Algebra Textbook",
    ],
)
def test_rejects_profile_prose_author_and_course_like_fragments(title: str):
    assert not is_plausible_paper_title(title), title


@pytest.mark.parametrize(
    "title",
    [
        # Real titles from miroflow_real that must NOT be over-rejected:
        "香猪 ADAMTS-1 基因克隆及遗传效应分析",
        "小型汽油发动机电喷系统平台——MSE2．0",
        "一种Sn-Sb/石墨烯纳米复合材料的制备方法",
        "CONCAVE EXTENDED LINEAR MODELING: A THEORETICAL SYNTHESIS",
        "RELATION BETWEEN WATER TEMPERATURE, WATER EXCHANGE AMOUNT, FEED AND PRAWN DISEASE",
        "4,4'—二偶氮苯重氮氨基偶氮苯分光光度法测定水和废水中的痕量汞（II）",
        "基于ICP-MS/MS分析微量金属元素的原油产地溯源",
        "w (Co)/w (Ni)对Ti(C,N)基金属陶瓷高温氧化和耐腐蚀性能的影响",
        "斑节对虾 CFSH 基因的克隆及其多功能性探究",
        "5-氨基酮戊酸光动力疗法对兔耳痤疮模型皮损及组织中IL-17表达水平的影响",
        "Scaling CO2 Electroreduction Revolution: Pathways from Laboratory Breakthroughs to Industrial Implementation",
        "Bio-based and Waterborne Polyurethane Coatings with High hardness",
        "Low-grade thermal energy utilization: Technologies and applications",
        "Fast Range and Motion Parameters Estimation for Maneuvering Targets Using Time-Reversal Process",
        "Synergistic Proton and Oxygen Transport Optimization via Binder Engineering for High-Efficiency ORR in High-Temperature Fuel Cell",
        "Environmental Exposure and Childhood Atopic Dermatitis in Shanghai: A Season-Stratified Time-Series Analysis",
        "Clinical Efficacy and Microbiome Changes Following Fecal Microbiota Transplantation in Children With Recurrent Clostridium Difficile Infection",
        "Mini-Emulsion Fabricated Magnetic and Fluorescent Hybrid Janus Micro-Motors",
        "Symmetry Breaking and Other Nonlinear Elastic Responses of Metallic Glasses Subject to Uniaxial Loading",
        "Smoothing Splines and Rank Structured Matrices: Revisiting the Spline Kernel",
    ],
)
def test_accepts_cjk_titles_with_acronyms_and_all_caps_english(title: str):
    """Chinese titles with embedded Latin acronyms and all-caps western
    titles must pass — the v1 uppercase_ratio rule over-rejected them."""
    assert is_plausible_paper_title(title), title
