# `task_planner.py` -- 任务计划管理 MCP 服务器

## 文件概述

`task_planner.py` 提供了一个任务计划（TODO）管理工具，让 Agent 能够创建、查看、完成和删除任务计划项。这不是一个信息获取或计算工具，而是一个"元工具"——帮助 Agent 组织和跟踪自己的工作流程。每个任务以 JSON 文件持久化存储，通过 `TASK_ID` 环境变量实现多任务隔离。

## 关键代码解读

### 1. 任务隔离机制

```python
TASK_ID = os.environ.get("TASK_ID")
if not TASK_ID:
    raise ValueError(
        "TASK_ID environment variable is required for task_planner tool."
    )
TODO_DATA_FILE = os.path.join(TODO_DATA_DIR, f"todos_{TASK_ID}.json")
```

在并发执行场景中（如同时运行多个基准测试任务），每个任务实例有唯一的 `TASK_ID`，对应独立的 JSON 文件。这防止了并发写入冲突。如果未设置 `TASK_ID`，服务器启动时会直接报错。

### 2. Markdown 格式化输出

```python
def format_todos_as_markdown(todos, message=""):
    total = len(todos)
    completed = sum(1 for t in todos if t.get("completed", False))
    pending = total - completed
    lines = []
    lines.append("# Task Plan\n")
    lines.append(f"Total: {total} | Pending: {pending} | Completed: {completed}\n")
    for todo in todos:
        checkbox = "[x]" if todo.get("completed", False) else "[ ]"
        lines.append(f"- {checkbox} {todo['title']} ({todo['id'][:8]})")
```

将任务列表格式化为 Markdown 清单，包含统计信息（总数/待完成/已完成）和每个任务的复选框状态。使用 UUID 的前 8 位作为短 ID，方便 Agent 引用。

### 3. 四个 CRUD 工具

```python
@mcp.tool()
async def add_todo(titles: List[str]) -> str:
    # 批量添加任务，每个自动分配 UUID

@mcp.tool()
async def list_todos() -> str:
    # 查看所有任务及完成状态

@mcp.tool()
async def complete_todo(todo_ids: List[str]) -> str:
    # 标记任务为已完成（支持短 ID 匹配）

@mcp.tool()
async def delete_todo(todo_ids: List[str]) -> str:
    # 删除任务
```

- 所有操作都支持批量（接受列表参数）
- `complete_todo` 和 `delete_todo` 支持短 ID 匹配（`todo["id"].startswith(todo_id)`）
- 每次操作后返回更新后的完整任务列表

### 4. 数据持久化

```python
def load_todos() -> List[Dict[str, Any]]:
    with open(TODO_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_todos(todos: List[Dict[str, Any]]) -> bool:
    with open(TODO_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)
```

使用简单的 JSON 文件存储。每个任务项包含：`id`（UUID）、`title`（标题）、`completed`（是否完成）、`created_at`（创建时间）。

## 核心类/函数

| 名称 | 类型 | 用途 |
|------|------|------|
| `load_todos` | 函数 | 从 JSON 文件加载任务列表 |
| `save_todos` | 函数 | 将任务列表保存到 JSON 文件 |
| `format_todos_as_markdown` | 函数 | 将任务列表格式化为 Markdown 清单 |
| `add_todo` | MCP 工具 | 批量添加任务计划项 |
| `list_todos` | MCP 工具 | 查看完整任务计划 |
| `complete_todo` | MCP 工具 | 标记任务为已完成 |
| `delete_todo` | MCP 工具 | 删除任务计划项 |

## 与其他模块的关系

- **属于 dev_mcp_servers**：作为辅助性的元工具使用
- **通过 `TASK_ID` 与外部系统关联**：Pipeline 或 Orchestrator 在启动时设置此变量
- **存储路径**：默认在 `../../logs/todo_lists/` 目录下
- **独立运行**：不依赖其他 MCP 服务器

## 总结

`task_planner.py` 是一个帮助 Agent 组织工作流程的元工具。通过 CRUD 操作管理任务计划，以 JSON 文件持久化存储，通过 `TASK_ID` 实现并发隔离。Markdown 格式化的输出方便 Agent 和人类阅读。这体现了 MiroThinker 中"让 Agent 自我管理"的设计理念。
