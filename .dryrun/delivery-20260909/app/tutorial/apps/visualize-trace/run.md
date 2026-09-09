# `run.py` -- 启动脚本

## 文件概述

本文件是 `visualize-trace` 应用的启动入口，负责依赖检查、自动安装、JSON 文件检测和 Flask 应用启动。设计为"开箱即用"——即使环境中尚未安装依赖也能自动处理。

## 关键代码解读

### 1. 依赖检查

```python
def check_dependencies():
    import importlib.util
    if importlib.util.find_spec("flask") is not None:
        print("Flask is installed")
        return True
    else:
        raise ImportError("Flask not found")
```

**逐步解释**：
- 使用 `importlib.util.find_spec` 检查 Flask 是否可导入。
- 不直接 `import flask`，避免在检查阶段产生副作用。

### 2. 自动安装依赖

```python
def install_dependencies():
    try:
        subprocess.check_call(["uv", "sync"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        return True
```

**逐步解释**：
- 优先使用 `uv sync`（MiroThinker 项目的标准包管理器）。
- 如果 `uv` 不可用，回退到 `pip install`。

### 3. 主函数

```python
def main():
    parser = argparse.ArgumentParser(description="Trace Analysis Web Demo")
    parser.add_argument("-p", "--port", type=int, default=5000)
    args = parser.parse_args()

    if not check_dependencies():
        if not install_dependencies():
            return

    # 检查父目录中的 JSON 文件
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    json_files = [f for f in os.listdir(os.path.join(parent_dir, "..")) if f.endswith(".json")]

    from app import app
    app.run(debug=True, host="0.0.0.0", port=args.port)
```

**逐步解释**：
- 支持 `-p/--port` 参数指定端口号（默认 5000）。
- 依赖检查失败时尝试自动安装。
- 扫描父目录提示可用的 JSON 文件数量。
- 启动 Flask 应用，监听所有接口（`0.0.0.0`）。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `check_dependencies` | 检查 Flask 是否已安装 |
| `install_dependencies` | 自动安装依赖（优先 uv，回退 pip） |
| `main` | 启动入口：参数解析 + 依赖检查 + 应用启动 |

## 与其他模块的关系

- 导入 `app.py` 中的 Flask 应用实例 `app`。
- 是整个 `visualize-trace` 的推荐启动方式。

## 总结

`run.py` 是一个用户友好的启动脚本，通过自动依赖管理和环境检测降低了使用门槛。用户只需运行 `python run.py` 即可启动仪表板。
