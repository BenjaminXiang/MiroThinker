# `templates/index.html` -- 页面模板

## 文件概述

本文件是 `visualize-trace` 仪表板的 HTML 页面模板，使用 Flask 的 Jinja2 模板引擎渲染。页面基于 Bootstrap 5 构建，定义了完整的仪表板布局，包括导航栏、摘要面板、步骤导航、执行流程、统计区域以及各种交互组件。

## 关键代码解读

### 1. 页面结构概览

```html
<body>
    <div class="container-fluid">
        <!-- 顶部导航栏 -->
        <nav class="navbar navbar-dark bg-primary">
            <!-- 目录输入框 + 文件选择器 + 前后导航按钮 + 加载/刷新按钮 -->
        </nav>

        <!-- 顶部摘要面板（三列） -->
        <div class="row mt-3">
            <div class="col-md-4">基本信息</div>
            <div class="col-md-4">执行摘要</div>
            <div class="col-md-4">性能摘要</div>
        </div>

        <!-- 主内容区（两列） -->
        <div class="row mt-3">
            <div class="col-md-2">步骤导航（侧边栏）</div>
            <div class="col-md-10">执行流程面板</div>
        </div>

        <!-- 底部统计（两列） -->
        <div class="row mt-3">
            <div class="col-md-6">Spans 统计</div>
            <div class="col-md-6">步骤日志统计</div>
        </div>
    </div>
</body>
```

**逐步解释**：
- 使用 Bootstrap 的 12 列网格系统进行响应式布局。
- **导航栏**：包含目录输入框、文件下拉选择器（支持前后箭头导航）、加载和刷新按钮。
- **摘要面板**：三列等宽，分别显示基本信息、执行摘要、性能摘要。
- **主内容区**：左侧窄栏（2/12）为步骤导航，右侧宽栏（10/12）为执行流程详情。
- **底部统计**：两列等宽，分别显示 Spans 和步骤日志统计。

### 2. 文件导航组件

```html
<div class="input-group input-group-sm file-navigation">
    <button class="btn btn-outline-light nav-btn" id="prevFileBtn">
        <i class="fas fa-chevron-left"></i>
    </button>
    <select class="form-select" id="fileSelect" style="min-width: 250px;">
        <option value="">Select Trace file...</option>
    </select>
    <button class="btn btn-outline-light nav-btn" id="nextFileBtn">
        <i class="fas fa-chevron-right"></i>
    </button>
</div>
```

**逐步解释**：
- 文件选择器由三部分组成：上一个按钮、下拉列表、下一个按钮。
- 下拉列表的选项由 `script.js` 通过 API 动态填充。

### 3. 快捷键提示

```html
<div class="position-fixed bottom-0 start-0 p-3">
    <div class="card border-0 shadow-sm">
        <strong>Shortcuts:</strong>
        <span class="badge bg-secondary">左右箭头</span> 切换文件
        <span class="badge bg-secondary">Enter</span> 加载
        <span class="badge bg-secondary">Ctrl+R</span> 刷新
    </div>
</div>
```

**逐步解释**：
- 固定在页面左下角的小卡片，提示可用的键盘快捷键。

### 4. 模态框与通知

```html
<!-- 消息详情模态框 -->
<div class="modal fade" id="messageModal">
    <div class="modal-dialog modal-lg">
        <div class="modal-body" id="messageContent"></div>
    </div>
</div>

<!-- 加载遮罩层 -->
<div class="loading-overlay d-none" id="loadingOverlay">
    <div class="spinner-border text-primary"></div>
</div>

<!-- Toast 通知 -->
<div id="errorToast" class="toast">...</div>
<div id="successToast" class="toast">...</div>
```

**逐步解释**：
- **模态框**：点击消息内容时弹出，显示完整消息详情。
- **加载遮罩层**：全屏半透明遮罩 + 旋转加载指示器，在数据加载时显示。
- **Toast 通知**：错误（红色）和成功（绿色）通知，固定在右上角。

### 5. 外部依赖

```html
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
<link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/script.js') }}"></script>
```

**逐步解释**：
- **Bootstrap 5.1.3**：UI 框架（CSS + JS），提供网格系统、卡片、模态框等组件。
- **Font Awesome 6.0**：图标库，用于按钮和标题图标。
- **自定义样式和脚本**：通过 Flask 的 `url_for` 引用静态文件。

## 核心区域表格

| 区域 | DOM ID | 说明 |
|------|--------|------|
| 目录输入 | `directoryInput` | 文件目录路径输入框 |
| 文件选择 | `fileSelect` | Trace 文件下拉选择器 |
| 基本信息 | `basicInfo` | 任务状态、答案、判定结果 |
| 执行摘要 | `executionSummary` | 步骤数、工具调用数等统计 |
| 性能摘要 | `performanceSummary` | 执行时间、Token 用量等 |
| 步骤导航 | `navigationList` | 左侧步骤列表导航 |
| 执行流程 | `executionFlow` | 主内容区，逐步显示执行过程 |
| Spans 统计 | `spansStats` | Agent 维度的 Span 统计 |
| 步骤日志 | `stepLogsStats` | 步骤类型和状态分布 |

## 与其他模块的关系

- 被 `app.py` 的 `index()` 路由通过 `render_template("index.html")` 渲染。
- 引用 `static/css/style.css` 和 `static/js/script.js`。
- 所有数据面板的内容由 `script.js` 通过 API 动态填充。

## 总结

`index.html` 定义了仪表板的完整 HTML 骨架，使用 Bootstrap 实现响应式布局。页面本身不包含任何数据，所有内容都通过 JavaScript 动态渲染。设计为"空壳 + 占位提示"模式——加载文件前显示"请先加载 Trace 文件"提示，加载后由 `script.js` 填充实际内容。
