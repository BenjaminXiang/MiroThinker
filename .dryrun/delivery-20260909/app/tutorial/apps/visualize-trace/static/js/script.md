# `static/js/script.js` -- 前端交互逻辑

## 文件概述

本文件是 `visualize-trace` 仪表板的前端核心，约 1000 行 JavaScript 代码。它负责：与后端 API 通信、渲染所有面板内容、管理文件导航、处理用户交互（展开/折叠、键盘快捷键、步骤导航等），以及将 Markdown 和 MCP XML 格式的内容转换为可读的 HTML。

## 关键代码解读

### 1. 全局状态与 DOM 元素

```javascript
let currentFlowData = null;
let currentBasicInfo = null;
let currentFileList = [];
let currentFileIndex = -1;

const elements = {
    directoryInput: document.getElementById('directoryInput'),
    fileSelect: document.getElementById('fileSelect'),
    basicInfo: document.getElementById('basicInfo'),
    executionFlow: document.getElementById('executionFlow'),
    // ...
};
```

**逐步解释**：
- 全局变量维护当前加载的数据和文件列表状态。
- 在初始化时一次性获取所有 DOM 元素引用，避免重复查询。

### 2. 应用初始化

```javascript
function initializeApp() {
    // 绑定事件
    elements.browseDirectoryBtn.addEventListener('click', loadFileList);
    elements.loadBtn.addEventListener('click', loadTrace);
    elements.prevFileBtn.addEventListener('click', navigatePrevFile);
    elements.nextFileBtn.addEventListener('click', navigateNextFile);

    // 键盘快捷键
    document.addEventListener('keydown', handleKeyboardShortcuts);

    // 自动加载文件列表
    loadFileList();
}
```

**逐步解释**：
- 绑定按钮点击、键盘快捷键等事件。
- 支持的快捷键：左右箭头切换文件、Enter 加载、Ctrl+R 刷新。
- 页面加载时自动获取默认目录的文件列表。

### 3. Trace 加载流程

```javascript
async function loadTrace() {
    showLoading();
    const response = await fetch('/api/load_trace', {
        method: 'POST',
        body: JSON.stringify({ file_path: filePath }),
    });
    // 并行加载所有数据
    await Promise.all([
        loadBasicInfo(),
        loadExecutionFlow(),
        loadExecutionSummary(),
        loadPerformanceSummary(),
        loadSpansStats(),
        loadStepLogsStats(),
    ]);
    hideLoading();
}
```

**逐步解释**：
- 先调用 `/api/load_trace` 加载文件。
- 然后用 `Promise.all` 并行请求所有分析数据。
- 显示/隐藏加载遮罩层提供视觉反馈。

### 4. 执行流程渲染

```javascript
function renderExecutionFlow(flowData) {
    const container = document.createElement('div');
    container.className = 'execution-steps-container';

    flowData.forEach((step, index) => {
        const stepElement = createStepElement(step, index);
        container.appendChild(stepElement);

        // 如果有浏览器会话，渲染子流程
        if (step.browser_flow && step.browser_flow.length > 0) {
            const browserSession = createBrowserSessionElement(step);
            container.appendChild(browserSession);
        }
    });
}
```

**逐步解释**：
- 遍历执行流程数据，为每个步骤创建 DOM 元素。
- 如果步骤包含浏览器子会话（`browser_flow`），额外渲染嵌套的子流程面板。
- 每个步骤包含：角色标签、内容预览、工具调用信息、展开/折叠功能。

### 5. MCP 工具调用渲染

```javascript
function renderMCPToolCalls(toolCalls) {
    return toolCalls.map(tool => {
        const isBrowserAgent = tool.server_name?.startsWith('agent-') || ...;
        return `
            <div class="mcp-tool-call ${isBrowserAgent ? 'browser-agent' : ''}">
                <div class="mcp-tool-header">
                    <i class="fas fa-wrench"></i>
                    Tool: <span class="mcp-tool-name">${tool.tool_name}</span>
                    Server: ${tool.server_name}
                </div>
                <div class="mcp-tool-args">
                    <pre>${JSON.stringify(tool.arguments, null, 2)}</pre>
                </div>
            </div>
        `;
    }).join('');
}
```

**逐步解释**：
- 将工具调用渲染为卡片式 UI。
- 浏览器 Agent 调用使用绿色主题（`browser-agent` class），普通工具使用蓝色主题。
- 参数以格式化 JSON 显示。

### 6. Markdown 简易渲染

```javascript
function renderMarkdown(text) {
    // 代码块
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<div class="code-block"><pre><code>$2</code></pre></div>');
    // 标题
    text = text.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    // 粗体、斜体、行内代码、链接、列表等
    ...
}
```

**逐步解释**：
- 使用正则表达式将 Markdown 文本转换为 HTML。
- 支持代码块、标题、粗体、斜体、行内代码、链接、列表等常见格式。
- 不依赖第三方 Markdown 库，轻量实现。

### 7. 步骤导航面板

```javascript
function renderNavigation(flowData) {
    flowData.forEach((step, index) => {
        const navItem = document.createElement('div');
        navItem.className = 'nav-item';
        navItem.innerHTML = `
            <span class="step-number">#${step.step_id}</span>
            <span class="step-role ${step.role}">${step.role}</span>
            <div class="step-summary">${step.content_preview}</div>
        `;
        navItem.addEventListener('click', () => scrollToStep(index));
    });
}
```

**逐步解释**：
- 左侧导航面板列出所有步骤，显示步骤编号、角色和内容预览。
- 点击导航项会平滑滚动到对应步骤。
- 包含浏览器子步骤的展开/折叠功能。

## 核心类/函数表格

| 函数名 | 说明 |
|--------|------|
| `initializeApp` | 应用初始化，绑定事件 |
| `loadFileList` | 加载指定目录的 JSON 文件列表 |
| `loadTrace` | 加载 Trace 文件并刷新所有面板 |
| `renderBasicInfo` | 渲染基本信息面板 |
| `renderExecutionFlow` | 渲染执行流程面板 |
| `renderExecutionSummary` | 渲染执行统计面板 |
| `renderPerformanceSummary` | 渲染性能摘要面板 |
| `renderSpansStats` | 渲染 Spans 统计面板 |
| `renderStepLogsStats` | 渲染步骤日志统计面板 |
| `renderNavigation` | 渲染左侧步骤导航面板 |
| `renderMCPToolCalls` | 渲染 MCP 工具调用卡片 |
| `renderMarkdown` | 简易 Markdown 转 HTML |
| `handleKeyboardShortcuts` | 处理键盘快捷键 |
| `showLoading / hideLoading` | 加载遮罩层控制 |
| `showError / showSuccess` | Toast 通知 |

## 与其他模块的关系

- 通过 `fetch` 调用 `app.py` 定义的所有 REST API 端点。
- 被 `templates/index.html` 通过 `<script>` 标签引入。
- 使用 `style.css` 中定义的样式类。

## 总结

`script.js` 是仪表板的交互引擎，将后端返回的数据转换为可视化界面。核心功能包括：并行数据加载、MCP 工具调用可视化、Markdown 渲染、步骤导航、键盘快捷键等。代码采用函数式组织，每个 `render*` 函数负责一个面板的渲染。
