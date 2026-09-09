# `task_logger.py` — 任务日志与结构化输出

## 文件概述

`task_logger.py` 是 MiroThinker 的**核心日志系统**。它定义了多个数据类来追踪任务执行的完整生命周期：从任务开始到每一步 LLM 调用、工具执行、子智能体会话，直到最终答案生成。所有日志最终被序列化为 JSON 文件用于分析和调试。

在项目中，`TaskLog` 实例在 `Pipeline` 初始化时创建，然后作为参数传递给 Orchestrator、LLM 客户端、ToolExecutor 等所有组件。

## 关键代码解读

### 彩色控制台输出

```python
from colorama import Fore, Style, init
init(autoreset=True, strip=False)

def get_color_for_level(level: str) -> str:
    if level == "ERROR":   return f"{Fore.RED}{Style.BRIGHT}"
    elif level == "WARNING": return f"{Fore.YELLOW}{Style.BRIGHT}"
    elif level == "INFO":    return f"{Fore.GREEN}{Style.BRIGHT}"
    elif level == "DEBUG":   return f"{Fore.CYAN}{Style.BRIGHT}"
    else:                    return f"{Fore.WHITE}{Style.BRIGHT}"

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, self.datefmt)
        level_color = get_color_for_level(record.levelname)
        name_color = f"{Fore.BLUE}{Style.BRIGHT}"
        message = record.getMessage()
        return f"[{timestamp}][{name_color}{record.name}{Style.RESET_ALL}][{level_color}{record.levelname}{Style.RESET_ALL}] - {message}"
```

**解释**：

- 使用 `colorama` 实现跨平台的彩色终端输出
- 不同日志级别用不同颜色区分：红色=错误，黄色=警告，绿色=信息，青色=调试
- 日志器名称（`miroflow_agent`）用蓝色高亮

### 日志引导函数

```python
def bootstrap_logger() -> logging.Logger:
    miroflow_agent_logger = logging.getLogger("miroflow_agent")
    if miroflow_agent_logger.handlers:
        return miroflow_agent_logger  # 防止重复配置

    formatter = ColoredFormatter("%(asctime)s,%(msecs)03d", datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    miroflow_agent_logger.addHandler(handler)
    miroflow_agent_logger.setLevel(logging.DEBUG)
    miroflow_agent_logger.propagate = False  # 防止向根日志器传播
    return miroflow_agent_logger
```

**解释**：

- 创建名为 `miroflow_agent` 的专用日志器
- `propagate = False` 防止日志消息向 Python 根日志器传播导致重复输出
- 检查是否已有 handler 防止多次调用造成重复配置

### 步骤日志数据类

```python
@dataclass
class StepLog:
    step_name: str
    message: str
    timestamp: str
    info_level: Literal["info", "warning", "error", "debug"] = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        valid_levels = {"info", "warning", "error", "debug"}
        if self.info_level not in valid_levels:
            raise ValueError(f"info_level must be one of {valid_levels}")
```

**解释**：

- 每个步骤日志包含步骤名称、消息内容、时间戳、日志级别和可选的元数据
- `info_level` 使用 `Literal` 类型约束，并在 `__post_init__` 中验证

### TaskLog 核心数据类

```python
@dataclass
class TaskLog:
    status: str = "running"
    task_id: str = ""
    input: Any = None
    ground_truth: str = ""
    final_boxed_answer: str = ""

    current_main_turn_id: int = 0
    current_sub_agent_turn_id: int = 0
    sub_agent_counter: int = 0

    main_agent_message_history: List[Dict] = field(default_factory=list)
    sub_agent_message_history_sessions: Dict[str, List[Dict]] = field(default_factory=dict)
    step_logs: List[StepLog] = field(default_factory=list)
    trace_data: Dict[str, Any] = field(default_factory=dict)
```

**解释**：

- `TaskLog` 是整个任务的中央数据容器，追踪：
  - **任务元信息**：ID、状态、输入、标准答案、最终答案
  - **对话轮次**：主智能体和子智能体的当前轮次计数
  - **消息历史**：主智能体和所有子智能体会话的完整消息历史
  - **步骤日志**：所有事件的有序列表
  - **追踪数据**：性能统计和工具使用量数据

### 日志记录方法（带图标）

```python
def log_step(self, info_level, step_name, message, metadata=None):
    icon = ""
    if "Tool Call Start" in step_name:    icon = "▶️ "
    elif "Tool Call Success" in step_name: icon = "✅ "
    elif "Tool Call Error" in step_name:   icon = "❌ "
    elif "agent-" in step_name:            icon = "🤖 "
    elif "Main Agent" in step_name:        icon = "👑 "
    elif "LLM" in step_name:              icon = "🧠 "
    elif "ToolManager" in step_name:       icon = "🔧 "
    # ...

    step_log = StepLog(
        step_name=f"{icon}{step_name}",
        message=message,
        timestamp=get_utc_plus_8_time(),
        info_level=info_level,
        metadata=metadata or {},
    )
    self.step_logs.append(step_log)

    # 同时输出到控制台
    log_message = f"{icon}{step_name}: {message}"
    if info_level == "error":    logger.error(log_message)
    elif info_level == "warning": logger.warning(log_message)
    else:                         logger.info(log_message)
```

**解释**：

- 根据步骤名称自动添加图标，增强控制台输出的可读性
- 同时完成两件事：添加到内存中的 `step_logs` 列表，并输出到控制台
- 这是整个系统中最常被调用的方法——几乎所有组件都通过它记录事件

### JSON 序列化与持久化

```python
def to_json(self) -> str:
    data_dict = asdict(self)
    serialized_dict = self.serialize_for_json(data_dict)
    return json.dumps(serialized_dict, ensure_ascii=False, indent=2)

def save(self):
    os.makedirs(self.log_dir, exist_ok=True)
    timestamp = self.start_time.replace(":", "-").replace(".", "-").replace(" ", "-")
    filename = f"{self.log_dir}/task_{self.task_id}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(self.to_json())
    return filename
```

**解释**：

- `serialize_for_json()` 递归处理不可 JSON 序列化的对象（如 `Path`）
- 文件命名使用 `task_id` + 时间戳，确保唯一性
- 支持 Unicode 和 ASCII 两种编码的回退机制

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `TaskLog` | 数据类 | 任务的中央数据容器，追踪完整的执行生命周期 |
| `StepLog` | 数据类 | 单个执行步骤的结构化日志条目 |
| `LLMCallLog` | 数据类 | LLM 调用的技术详情（Token 数、错误等） |
| `ToolCallLog` | 数据类 | 工具调用的详细信息（参数、结果、错误） |
| `ColoredFormatter` | 类 | 自定义的日志格式化器，支持彩色输出 |
| `bootstrap_logger()` | 函数 | 配置并返回 `miroflow_agent` 日志器 |
| `get_utc_plus_8_time()` | 函数 | 获取 UTC+8 时区的当前时间字符串 |

## 与其他模块的关系

- **`core/Pipeline`**：创建 `TaskLog` 实例并传递给所有下游组件
- **`core/Orchestrator`**：通过 `log_step()` 记录推理循环的每一步
- **`llm/base_client.py`**：记录 LLM 调用事件和 Token 使用量
- **`core/ToolExecutor`**：记录工具调用的开始、成功和失败
- **`summary_time_cost.py`**：读取 `save()` 输出的 JSON 文件进行汇总统计
- **`apps/visualize-trace/`**：Flask 仪表板读取 JSON 日志文件进行可视化分析

## 总结

`task_logger.py` 是 MiroThinker 的"飞行记录仪"。它通过 `TaskLog` 数据类将整个任务执行过程的所有信息（消息历史、步骤日志、性能数据）集中管理，并提供了即时的彩色控制台输出和事后的 JSON 持久化两种消费方式。理解这个文件有助于调试智能体行为和分析性能瓶颈。
