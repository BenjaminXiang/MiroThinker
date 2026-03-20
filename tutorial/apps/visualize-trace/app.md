# `app.py` -- Flask 应用与 API 端点

## 文件概述

本文件定义了 `visualize-trace` 的 Flask Web 应用，包含主页面路由和所有 REST API 端点。它充当前端和 `TraceAnalyzer` 解析引擎之间的桥梁，接收前端请求、调用分析器方法、返回 JSON 数据。

## 关键代码解读

### 1. 全局分析器实例

```python
app = Flask(__name__)
analyzer = None  # 全局变量存储当前分析器实例
```

**逐步解释**：
- `analyzer` 是全局状态，保存当前加载的 `TraceAnalyzer` 实例。
- 这意味着同一时间只能分析一个 Trace 文件（单用户设计）。

### 2. 文件列表 API

```python
@app.route("/api/list_files", methods=["GET"])
def list_files():
    directory = request.args.get("directory", "")
    if not directory:
        directory = os.path.abspath("..")
    directory = os.path.expanduser(directory)
    directory = os.path.abspath(directory)

    json_files = []
    for file in os.listdir(directory):
        if file.endswith(".json"):
            stat = os.stat(file_path)
            json_files.append({
                "name": file, "path": file_path,
                "size": stat.st_size, "modified": stat.st_mtime,
            })
    json_files.sort(key=lambda x: x["name"])
```

**逐步解释**：
- 接受 `directory` 查询参数，默认使用上级目录。
- 支持 `~` 路径展开和相对路径转绝对路径。
- 列出目录中所有 `.json` 文件，附带文件大小和修改时间。
- 按文件名排序返回。

### 3. Trace 加载 API

```python
@app.route("/api/load_trace", methods=["POST"])
def load_trace():
    global analyzer
    file_path = data.get("file_path")
    analyzer = TraceAnalyzer(file_path)
    return jsonify({"message": "File loaded successfully", "file_path": file_path})
```

**逐步解释**：
- 接受 POST 请求，读取文件路径。
- 创建新的 `TraceAnalyzer` 实例替换全局 `analyzer`。
- 后续所有分析 API 都依赖这个全局实例。

### 4. 分析 API 模式

所有分析 API 遵循统一模式：

```python
@app.route("/api/basic_info")
def get_basic_info():
    if not analyzer:
        return jsonify({"error": "Please load trace file first"}), 400
    try:
        return jsonify(analyzer.get_basic_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

**逐步解释**：
- 先检查 `analyzer` 是否已初始化。
- 调用对应的 `TraceAnalyzer` 方法。
- 将返回的字典直接 JSON 序列化。
- 统一的错误处理模式。

## 核心类/函数表格

| 路由函数 | 端点 | 说明 |
|----------|------|------|
| `index` | `GET /` | 渲染主页面 |
| `list_files` | `GET /api/list_files` | 列出 JSON 文件 |
| `load_trace` | `POST /api/load_trace` | 加载 Trace 文件 |
| `get_basic_info` | `GET /api/basic_info` | 任务基本信息 |
| `get_performance_summary` | `GET /api/performance_summary` | 性能摘要 |
| `get_execution_flow` | `GET /api/execution_flow` | 执行流程 |
| `get_execution_summary` | `GET /api/execution_summary` | 执行统计 |
| `get_spans_summary` | `GET /api/spans_summary` | Spans 统计 |
| `get_step_logs_summary` | `GET /api/step_logs_summary` | 步骤日志统计 |
| `get_raw_messages` | `GET /api/debug/raw_messages` | 原始消息（调试用） |

## 与其他模块的关系

- 依赖 `trace_analyzer.py` 中的 `TraceAnalyzer` 类进行所有数据分析。
- 被 `run.py` 导入并启动。
- 前端 `script.js` 通过 AJAX 调用这些 API 端点。

## 总结

`app.py` 是一个典型的 Flask REST API 应用，职责单一：将 HTTP 请求映射到 `TraceAnalyzer` 的方法调用。所有业务逻辑都封装在 `TraceAnalyzer` 中，`app.py` 仅负责请求解析、参数校验和错误处理。
