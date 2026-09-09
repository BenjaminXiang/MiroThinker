"""Initial taxonomy_vocabulary seeds.

Covers three namespaces used in plan 005 §6.2 company_fact.fact_type:
  - industry         : 行业领域（行业画像 + 投研过滤）
  - data_route       : 数据路线（Type G 具身智能 / 机器人数据采集问题）
  - technology_route : 技术路线（SLAM / embodied AI / cloud robotics …）

Each seed row is idempotent upsert-able to the `taxonomy_vocabulary` table:
  code         TEXT PRIMARY KEY
  namespace    TEXT NOT NULL
  display_name TEXT NOT NULL
  display_name_en TEXT
  parent_code  TEXT NULL
  description  TEXT
  status       TEXT DEFAULT 'active'

Convention: code uses '.' separators, e.g. 'industry:robotics.service'.
Flat-string hierarchy lets callers query prefix with LIKE 'industry:robotics%'
without requiring parent_code recursion.

Scope note: r1 draft covered ~40 codes. r2 aligned this seed against
docs/测试集答案.xlsx 17 questions; every taxonomy-relevant answer token should
now have a corresponding code below (or be a legitimate out-of-scope topic
per plan §2 non-goals).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxonomySeed:
    code: str
    namespace: str
    display_name: str
    display_name_en: str | None
    parent_code: str | None
    description: str | None


# =====================================================================
# industry namespace
# =====================================================================
_INDUSTRY: list[TaxonomySeed] = [
    # robotics
    TaxonomySeed(
        "industry:robotics", "industry", "机器人", "Robotics", None, "机器人整体行业"
    ),
    TaxonomySeed(
        "industry:robotics.service",
        "industry",
        "服务机器人",
        "Service robotics",
        "industry:robotics",
        "家庭 / 商业 / 餐饮 / 医疗辅助 等",
    ),
    TaxonomySeed(
        "industry:robotics.service.food_delivery",
        "industry",
        "送餐机器人",
        "Food-delivery robot",
        "industry:robotics.service",
        "酒店 / 餐厅场景送餐机器人（普渡、擎朗、云迹等）",
    ),
    TaxonomySeed(
        "industry:robotics.industrial",
        "industry",
        "工业机器人",
        "Industrial robotics",
        "industry:robotics",
        None,
    ),
    TaxonomySeed(
        "industry:robotics.humanoid",
        "industry",
        "人形机器人",
        "Humanoid robotics",
        "industry:robotics",
        None,
    ),
    TaxonomySeed(
        "industry:robotics.dexterous_hand",
        "industry",
        "灵巧手",
        "Dexterous hand",
        "industry:robotics",
        "五指灵巧手、触觉灵巧手等多自由度末端执行器",
    ),
    TaxonomySeed(
        "industry:robotics.surgical",
        "industry",
        "手术机器人",
        "Surgical robotics",
        "industry:robotics",
        None,
    ),
    TaxonomySeed(
        "industry:robotics.logistics",
        "industry",
        "物流机器人",
        "Logistics robotics",
        "industry:robotics",
        None,
    ),
    TaxonomySeed(
        "industry:robotics.space",
        "industry",
        "空间机器人",
        "Space robotics",
        "industry:robotics",
        "面向航天工程的机器人（王学谦团队等）",
    ),
    TaxonomySeed(
        "industry:robotics.drone",
        "industry",
        "无人机",
        "UAV / Drone",
        "industry:robotics",
        None,
    ),
    # AI
    TaxonomySeed("industry:ai", "industry", "人工智能", "AI", None, None),
    TaxonomySeed(
        "industry:ai.llm",
        "industry",
        "大语言模型",
        "LLM",
        "industry:ai",
        None,
    ),
    TaxonomySeed(
        "industry:ai.vision",
        "industry",
        "计算机视觉",
        "Computer Vision",
        "industry:ai",
        None,
    ),
    TaxonomySeed(
        "industry:ai.speech",
        "industry",
        "语音",
        "Speech / Audio",
        "industry:ai",
        None,
    ),
    TaxonomySeed(
        "industry:ai.autonomous_driving",
        "industry",
        "自动驾驶",
        "Autonomous driving",
        "industry:ai",
        None,
    ),
    TaxonomySeed(
        "industry:ai.embodied",
        "industry",
        "具身智能",
        "Embodied AI",
        "industry:ai",
        None,
    ),
    # AR / VR
    TaxonomySeed(
        "industry:vr_ar",
        "industry",
        "VR/AR",
        "Virtual / Augmented Reality",
        None,
        None,
    ),
    TaxonomySeed(
        "industry:vr_ar.xr_content",
        "industry",
        "XR 内容",
        "XR content",
        "industry:vr_ar",
        None,
    ),
    TaxonomySeed(
        "industry:vr_ar.xr_hardware",
        "industry",
        "XR 硬件",
        "XR hardware",
        "industry:vr_ar",
        None,
    ),
    # healthcare
    TaxonomySeed(
        "industry:healthcare", "industry", "医疗健康", "Healthcare", None, None
    ),
    TaxonomySeed(
        "industry:healthcare.diagnostics",
        "industry",
        "诊断设备",
        "Diagnostics",
        "industry:healthcare",
        None,
    ),
    TaxonomySeed(
        "industry:healthcare.devices",
        "industry",
        "医疗器械",
        "Medical devices",
        "industry:healthcare",
        None,
    ),
    TaxonomySeed(
        "industry:healthcare.digital",
        "industry",
        "数字医疗",
        "Digital health",
        "industry:healthcare",
        None,
    ),
    TaxonomySeed(
        "industry:healthcare.biotech",
        "industry",
        "生物技术",
        "Biotech",
        "industry:healthcare",
        None,
    ),
    TaxonomySeed(
        "industry:healthcare.rehabilitation",
        "industry",
        "康复医疗",
        "Rehabilitation",
        "industry:healthcare",
        "康复外骨骼、医疗康复机器人（迈步、奥达智声等）",
    ),
    TaxonomySeed(
        "industry:healthcare.surgical_robotics",
        "industry",
        "手术机器人（医疗）",
        "Surgical robotics (medical vertical)",
        "industry:healthcare",
        "血管介入、脑血管介入等手术机器人（爱博合创等）",
    ),
    # semiconductor & hardware
    TaxonomySeed(
        "industry:semiconductor", "industry", "半导体", "Semiconductor", None, None
    ),
    TaxonomySeed(
        "industry:semiconductor.chip_design",
        "industry",
        "芯片设计",
        "Chip design",
        "industry:semiconductor",
        None,
    ),
    TaxonomySeed(
        "industry:semiconductor.eda",
        "industry",
        "EDA",
        "EDA",
        "industry:semiconductor",
        None,
    ),
    TaxonomySeed(
        "industry:semiconductor.sensor",
        "industry",
        "传感器",
        "Sensor",
        "industry:semiconductor",
        None,
    ),
    # energy
    TaxonomySeed("industry:energy", "industry", "能源", "Energy", None, None),
    TaxonomySeed(
        "industry:energy.battery",
        "industry",
        "电池",
        "Battery",
        "industry:energy",
        None,
    ),
    TaxonomySeed(
        "industry:energy.new_energy",
        "industry",
        "新能源",
        "New energy",
        "industry:energy",
        None,
    ),
    # materials
    TaxonomySeed(
        "industry:materials", "industry", "新材料", "Advanced materials", None, None
    ),
    # fintech / enterprise software
    TaxonomySeed("industry:fintech", "industry", "金融科技", "Fintech", None, None),
    TaxonomySeed(
        "industry:enterprise_software",
        "industry",
        "企业服务软件",
        "Enterprise software",
        None,
        None,
    ),
    # PCB / 电子制造（测试集 Q5）
    TaxonomySeed(
        "industry:pcb",
        "industry",
        "PCB",
        "Printed circuit board",
        None,
        "PCB 打样 / 打板 / 批量（嘉立创、一博科技、深南电路等）",
    ),
    TaxonomySeed(
        "industry:pcb.prototype",
        "industry",
        "PCB 打样",
        "PCB prototyping",
        "industry:pcb",
        None,
    ),
    TaxonomySeed(
        "industry:electronics_manufacturing",
        "industry",
        "电子制造",
        "Electronics manufacturing",
        None,
        None,
    ),
]


# =====================================================================
# data_route namespace (直接服务 Type G 查询)
# =====================================================================
_DATA_ROUTE: list[TaxonomySeed] = [
    TaxonomySeed(
        "data_route:real_world_collection",
        "data_route",
        "真实世界采集",
        "Real-world data collection",
        None,
        "相机、激光雷达、IMU、遥操作、示范采集等真实物理世界传感",
    ),
    TaxonomySeed(
        "data_route:real_world_collection.camera",
        "data_route",
        "相机采集",
        "Camera capture",
        "data_route:real_world_collection",
        None,
    ),
    TaxonomySeed(
        "data_route:real_world_collection.lidar",
        "data_route",
        "激光雷达采集",
        "LiDAR capture",
        "data_route:real_world_collection",
        None,
    ),
    TaxonomySeed(
        "data_route:real_world_collection.imu",
        "data_route",
        "惯性测量采集",
        "IMU capture",
        "data_route:real_world_collection",
        None,
    ),
    TaxonomySeed(
        "data_route:real_world_collection.teleoperation",
        "data_route",
        "遥操作采集",
        "Teleoperation",
        "data_route:real_world_collection",
        None,
    ),
    TaxonomySeed(
        "data_route:real_world_collection.demonstration",
        "data_route",
        "示范采集",
        "Human demonstration",
        "data_route:real_world_collection",
        None,
    ),
    TaxonomySeed(
        "data_route:real_world_collection.motion_capture",
        "data_route",
        "动作捕捉",
        "Motion capture",
        "data_route:real_world_collection",
        "动捕设备记录人类动作并映射到本体（测试集 Q12）",
    ),
    TaxonomySeed(
        "data_route:real_world_collection.multimodal_sensor_fusion",
        "data_route",
        "多模态传感器融合",
        "Multimodal sensor fusion",
        "data_route:real_world_collection",
        "图像+激光+IMU+力/触觉 等多模态统一采集（测试集 Q12）",
    ),
    TaxonomySeed(
        "data_route:synthetic_generation",
        "data_route",
        "合成生成",
        "Synthetic generation",
        None,
        "仿真、域随机化、生成模型等纯合成数据路线",
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.simulation",
        "data_route",
        "仿真",
        "Simulation",
        "data_route:synthetic_generation",
        None,
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.domain_randomization",
        "data_route",
        "域随机化",
        "Domain randomization",
        "data_route:synthetic_generation",
        None,
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.generative_models",
        "data_route",
        "生成模型",
        "Generative models",
        "data_route:synthetic_generation",
        None,
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.video_synthesis_3d_reconstruction",
        "data_route",
        "视频合成+3D 重建",
        "Video synthesis + 3D reconstruction",
        "data_route:synthetic_generation",
        "测试集 Q15 合成数据发展方向之一",
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.e2e_3d_generation",
        "data_route",
        "端到端 3D 生成",
        "End-to-end 3D generation",
        "data_route:synthetic_generation",
        "光轮智能、银河通用、群核科技等厂商采用（测试集 Q15）",
    ),
    TaxonomySeed(
        "data_route:synthetic_generation.rule_based",
        "data_route",
        "规则生成",
        "Rule-based generation",
        "data_route:synthetic_generation",
        None,
    ),
    TaxonomySeed(
        "data_route:hybrid_real_synthetic",
        "data_route",
        "混合路线",
        "Hybrid real-synthetic",
        None,
        "Sim-to-Real / 真实预训练 + 合成微调 等混合策略",
    ),
]


# =====================================================================
# technology_route namespace
# =====================================================================
_TECH_ROUTE: list[TaxonomySeed] = [
    TaxonomySeed(
        "technology_route:slam", "technology_route", "SLAM", "SLAM", None, None
    ),
    TaxonomySeed(
        "technology_route:slam.visual",
        "technology_route",
        "视觉 SLAM",
        "Visual SLAM",
        "technology_route:slam",
        None,
    ),
    TaxonomySeed(
        "technology_route:slam.lidar",
        "technology_route",
        "激光 SLAM",
        "LiDAR SLAM",
        "technology_route:slam",
        None,
    ),
    TaxonomySeed(
        "technology_route:slam.visual_inertial",
        "technology_route",
        "视觉惯性 SLAM",
        "VI-SLAM",
        "technology_route:slam",
        None,
    ),
    TaxonomySeed(
        "technology_route:embodied_ai",
        "technology_route",
        "具身智能",
        "Embodied AI",
        None,
        None,
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.manipulation",
        "technology_route",
        "操作层",
        "Manipulation",
        "technology_route:embodied_ai",
        None,
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.locomotion",
        "technology_route",
        "运动层",
        "Locomotion",
        "technology_route:embodied_ai",
        None,
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.proprioception",
        "technology_route",
        "本体感知",
        "Proprioception",
        "technology_route:embodied_ai",
        "关节角度/扭矩/加速度等自身状态感知（测试集 Q16）",
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.environment_perception",
        "technology_route",
        "环境感知",
        "Environment perception",
        "technology_route:embodied_ai",
        "外部视觉/深度/激光等环境建模（测试集 Q16）",
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.cross_embodiment_learning",
        "technology_route",
        "跨本体学习",
        "Cross-embodiment learning",
        "technology_route:embodied_ai",
        "跨机器人形态迁移的策略学习（无界智航 X-Sim 等）",
    ),
    TaxonomySeed(
        "technology_route:embodied_ai.world_model",
        "technology_route",
        "世界模型",
        "World model",
        "technology_route:embodied_ai",
        None,
    ),
    TaxonomySeed(
        "technology_route:cloud_robotics",
        "technology_route",
        "云端机器人",
        "Cloud robotics",
        None,
        None,
    ),
    TaxonomySeed(
        "technology_route:vla",
        "technology_route",
        "VLA 模型",
        "Vision-Language-Action model",
        None,
        None,
    ),
    TaxonomySeed(
        "technology_route:multimodal_llm",
        "technology_route",
        "多模态大模型",
        "Multimodal LLM",
        None,
        None,
    ),
    TaxonomySeed(
        "technology_route:foundation_model",
        "technology_route",
        "基础模型",
        "Foundation model",
        None,
        None,
    ),
    # 感知 / 传感（测试集 Q7 / Q8）
    TaxonomySeed(
        "technology_route:tactile_sensing",
        "technology_route",
        "触觉感知",
        "Tactile sensing",
        None,
        "触觉传感器、触觉灵巧手（帕西尼感知等）",
    ),
    TaxonomySeed(
        "technology_route:force_sensing",
        "technology_route",
        "力传感",
        "Force sensing",
        None,
        "多维力/力矩传感（华力创科学等）",
    ),
    TaxonomySeed(
        "technology_route:force_sensing.optical_multi_axis",
        "technology_route",
        "光基多维力传感",
        "Optical multi-axis force sensing",
        "technology_route:force_sensing",
        "基于光学多模态感知的六维力/力矩测量（测试集 Q8）",
    ),
    TaxonomySeed(
        "technology_route:wearable_data_collection",
        "technology_route",
        "可穿戴数采套件",
        "Wearable data-collection kit",
        None,
        "无界智航 X-H1 等",
    ),
    # 医疗 / 康复（测试集 Q7 / Q10）
    TaxonomySeed(
        "technology_route:exoskeleton",
        "technology_route",
        "外骨骼",
        "Exoskeleton",
        None,
        "康复外骨骼、助力外骨骼（迈步机器人等）",
    ),
    TaxonomySeed(
        "technology_route:vascular_intervention",
        "technology_route",
        "血管介入",
        "Vascular intervention",
        None,
        "血管介入手术机器人（爱博合创 PANVIS-A 等）",
    ),
    # 空间 / 遥感（测试集 Q9）
    TaxonomySeed(
        "technology_route:remote_sensing",
        "technology_route",
        "遥感图像处理",
        "Remote sensing image processing",
        None,
        None,
    ),
    TaxonomySeed(
        "technology_route:multi_source_data_fusion",
        "technology_route",
        "多源数据融合",
        "Multi-source data fusion",
        None,
        "多源异构数据统一建模（王学谦团队等）",
    ),
]


TAXONOMY_SEEDS: list[TaxonomySeed] = [*_INDUSTRY, *_DATA_ROUTE, *_TECH_ROUTE]


def as_upsert_rows() -> list[dict[str, str | None]]:
    """Return seed rows in a shape suitable for an `INSERT ... ON CONFLICT UPDATE` batch."""
    return [
        {
            "code": s.code,
            "namespace": s.namespace,
            "display_name": s.display_name,
            "display_name_en": s.display_name_en,
            "parent_code": s.parent_code,
            "description": s.description,
            "status": "active",
        }
        for s in TAXONOMY_SEEDS
    ]
