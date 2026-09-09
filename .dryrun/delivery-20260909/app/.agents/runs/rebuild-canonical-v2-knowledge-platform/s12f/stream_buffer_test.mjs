// 答案 token 级流式输出 — 前端行级缓冲逻辑单元测试。
//
// 从 chat.html 的 <script> 中按函数名提取真实实现，用最小 DOM 桩运行：
//   - 未闭合 ** 不渲染、闭合后渲染
//   - 未闭合 ``` 代码块不渲染、闭合后渲染
//   - 完整行即时渲染（只追加、不清空）
//   - 流式增量输出与全量 renderMarkdown 渲染结果一致（flush/整体重渲染兜底）
//   - safePublicText 长度上限已移除（8000 截断不再生效）、内部 ID 过滤仍生效
//
// 运行：node .agents/runs/rebuild-canonical-v2-knowledge-platform/s12f/stream_buffer_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const chatHtml = resolve(here, "../../../../apps/admin-console/backend/static/chat.html");
const html = readFileSync(chatHtml, "utf8");
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) throw new Error("chat.html 中未找到 <script>");

// ---------- 提取器：按名字从脚本中取出函数/常量定义（跳过字符串与注释） ----------
// 注：正则 /^\s*```/ 中的反引号会被误认为模板字符串引号，提取前先替换为占位符，
// 提取后再还原（模板字面量只存在于未提取的函数中，不会受影响）。
function skipString(text, start) {
  const quote = text[start];
  let i = start + 1;
  while (i < text.length) {
    if (text[i] === "\\") { i += 2; continue; }
    if (text[i] === quote) return i;
    i++;
  }
  return text.length;
}

function extractFunction(script, name) {
  const marker = `function ${name}(`;
  const start = script.indexOf(marker);
  if (start < 0) throw new Error(`function ${name} 未找到`);
  let i = start + marker.length;
  let parens = 0;
  let openBrace = -1;
  while (i < script.length) {
    const ch = script[i];
    if (ch === "'" || ch === '"' || ch === "`") { i = skipString(script, i) + 1; continue; }
    if (ch === "(") parens++;
    else if (ch === ")") {
      parens--;
      if (parens <= 0) {
        openBrace = i + 1;
        while (script[openBrace] === " " || script[openBrace] === "\t" || script[openBrace] === "\n") openBrace++;
        if (script[openBrace] !== "{") throw new Error(`${name} 无函数体`);
        break;
      }
    }
    i++;
  }
  if (openBrace < 0) throw new Error(`${name} 未找到参数表结束`);
  let depth = 0;
  let j = openBrace;
  while (j < script.length) {
    const ch = script[j];
    if (ch === "'" || ch === '"' || ch === "`") { j = skipString(script, j) + 1; continue; }
    if (ch === "/" && script[j + 1] === "/") {
      while (j < script.length && script[j] !== "\n") j++;
      continue;
    }
    if (ch === "/" && script[j + 1] === "*") {
      j += 2;
      while (j + 1 < script.length && !(script[j] === "*" && script[j + 1] === "/")) j++;
      j += 2;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return script.slice(start, j + 1);
    }
    j++;
  }
  throw new Error(`${name} 函数体括号不平衡`);
}

function extractConst(script, name) {
  const marker = `const ${name} = `;
  const start = script.indexOf(marker);
  if (start < 0) throw new Error(`const ${name} 未找到`);
  let i = start + marker.length;
  while (i < script.length && script[i] !== "[" && script[i] !== "{") i++;
  const openChar = script[i];
  const closeChar = openChar === "[" ? "]" : "}";
  let depth = 0;
  while (i < script.length) {
    const ch = script[i];
    if (ch === "'" || ch === '"' || ch === "`") { i = skipString(script, i) + 1; continue; }
    if (ch === "/" && script[i + 1] === "/") {
      while (i < script.length && script[i] !== "\n") i++;
      continue;
    }
    if (ch === "/" && script[i + 1] === "*") {
      i += 2;
      while (i + 1 < script.length && !(script[i] === "*" && script[i + 1] === "/")) i++;
      i += 2;
      continue;
    }
    if (ch === openChar) depth++;
    else if (ch === closeChar) {
      depth--;
      if (depth === 0) {
        // 包含语句收尾（如 Object.freeze(...) 的 ")" 与 ";"）
        const end = script.indexOf(";", i + 1);
        return script.slice(start, (end >= 0 ? end : i + 1) + 1);
      }
    }
    i++;
  }
  throw new Error(`const ${name} 括号不平衡`);
}

// ---------- 最小 DOM 桩 ----------
function fakeTextNode(text) {
  return { nodeType: 3, textContent: String(text), children: [] };
}
function fakeElement(tagName) {
  const element = {
    nodeType: 1,
    tagName,
    className: "",
    children: [],
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
  };
  // 与真实 DOM 一致：赋值 textContent 会清空子节点并生成文本子节点
  Object.defineProperty(element, "textContent", {
    get() { return this.children.filter((n) => n.nodeType === 3).map((n) => n.textContent).join(""); },
    set(value) { this.children = [fakeTextNode(String(value))]; },
  });
  return element;
}
const fakeDocument = {
  createElement: (tag) => fakeElement(tag),
  createTextNode: (text) => fakeTextNode(text),
};

// ---------- 沙箱：真实函数 + 真实过滤逻辑 ----------
// 把 ``` 替换为占位符再提取（避免正则里的反引号被误判为模板字符串），提取后还原。
const scriptRaw = scriptMatch[1];
const scanScript = scriptRaw.replaceAll("```", "FENCE_SEQ");
const restore = (piece) => piece.replaceAll("FENCE_SEQ", "```");
const functionNames = [
  "create",
  "renderInline",
  "createMarkdownState",
  "flushMarkdownList",
  "renderMarkdownLine",
  "finalizeMarkdown",
  "renderMarkdown",
  "countFences",
  "hasUnpairedBold",
  "streamingReleaseEnd",
  "renderStreamingMarkdown",
];
const source = [
  restore(extractConst(scanScript, "unsafePublicTextPatterns")),
  ...functionNames.map((name) => restore(extractFunction(scanScript, name))),
  ...["unsafePublicText", "safePublicText"].map((name) => restore(extractFunction(scanScript, name))),
].join("\n");
const run = new Function("document", `${source}
return { unsafePublicText, safePublicText, ${functionNames.join(", ")} };`);
const api = run(fakeDocument);

const { renderMarkdown, renderStreamingMarkdown, safePublicText } = api;

// ---------- 断言与辅助 ----------
let passed = 0;
let failed = 0;
function check(name, cond, detail = "") {
  if (cond) {
    passed++;
    console.log(`ok - ${name}`);
  } else {
    failed++;
    console.log(`FAIL - ${name} ${detail}`);
  }
}

function serialize(node) {
  if (node.nodeType === 3) return JSON.stringify(node.textContent);
  return `<${node.tagName}>${node.children.map(serialize).join("")}</${node.tagName}>`;
}
// 全量渲染基线（与真实 renderMarkdown 一致）
function renderAll(text) {
  const box = fakeElement("div");
  renderMarkdown(box, text);
  return serialize(box);
}
function streamAll(...chunks) {
  const box = fakeElement("div");
  const s = renderStreamingMarkdown(box);
  for (const chunk of chunks) s.append(chunk);
  return { box, s };
}

// ---------- 用例 ----------
{
  const { box } = streamAll("第一段文字\n");
  check("完整行即时渲染", box.children.length === 1 && serialize(box) === renderAll("第一段文字"));
}
{
  const { box } = streamAll("这是 **未闭合加粗\n");
  check("未闭合 ** 行留在 buffer 不渲染", box.children.length === 0);
}
{
  const { box, s } = streamAll("这是 **未闭合加粗\n", "后续行**\n");
  check("跨行未闭合 ** 仍不渲染", box.children.length === 0);
  s.append("普通段落\n");
  check(
    "** 闭合（后续偶数行到达）后整体渲染",
    serialize(box) === renderAll("这是 **未闭合加粗\n后续行**\n普通段落"),
  );
}
{
  const { box } = streamAll("这是 **加粗文字** 结尾\n");
  check("单行闭合 ** 立即渲染", serialize(box) === renderAll("这是 **加粗文字** 结尾") && box.children.length === 1);
  check(
    "加粗结构正确",
    box.children[0]?.tagName === "p"
      && box.children[0].children.find((n) => n.tagName === "strong")?.textContent === "加粗文字",
    serialize(box),
  );
}
{
  const { box } = streamAll("开头段落\n```\n代码第一行\n");
  check("未闭合 ``` 代码块整体留 buffer", box.children.length === 0);
}
{
  const { box } = streamAll("开头段落\n```\n代码第一行\n", "```\n结尾段落\n");
  check(
    "``` 闭合后渲染（含代码块与后续行）",
    serialize(box) === renderAll("开头段落\n```\n代码第一行\n```\n结尾段落"),
  );
  const pre = box.children.find((n) => n.tagName === "pre");
  check(
    "代码块结构正确",
    !!pre && pre.children[0]?.tagName === "code" && pre.children[0].textContent === "代码第一行",
    serialize(box),
  );
}
{
  const { box } = streamAll("```\n**代码内加粗标记**\n```\n");
  check("代码块内 ** 不触发行缓冲", serialize(box) === renderAll("```\n**代码内加粗标记**\n```"));
}
{
  const { box, s } = streamAll("完整一行\n**未闭合\n");
  s.flush();
  check("flush 渲染残留 buffer，与全量渲染一致", serialize(box) === renderAll("完整一行\n**未闭合"));
}
{
  const { box, s } = streamAll("段落\n```\n未闭合代码\n");
  s.flush();
  // flush 与全量渲染对同一输入（含结尾 \n）输出一致：未闭合代码块收尾为 pre
  check("未闭合代码块 flush 收尾与全量渲染一致", serialize(box) === renderAll("段落\n```\n未闭合代码\n"));
}
{
  const { box } = streamAll("第一行**加", "粗文字**\n", "第二行\n");
  check("chunk 切分在行内时正常渲染", serialize(box) === renderAll("第一行**加粗文字**\n第二行"));
}
{
  const mixed = "第一段\n\n- 列表项一\n- 列表项二\n\n**加粗** 文本\n```\ncode line\n```\n结束\n";
  const { box } = streamAll(mixed);
  check("混合内容流式输出与全量渲染一致", serialize(box) === renderAll(mixed));
}
{
  const longText = "很长的答案内容。".repeat(1000); // 13000 字符 > 原 8000 上限
  check("safePublicText 不再限制答案长度", safePublicText(longText) === longText);
  const hex64 = "a".repeat(64);
  check("safePublicText 仍拒绝内部 ID", safePublicText(`前缀 ${hex64} 后缀`) === null);
  const { box } = streamAll("正常第一行\n", `内部${hex64}泄漏\n`, "正常第二行\n");
  check(
    "流式逐块过滤内部 ID（问题块跳过、其余照常渲染）",
    serialize(box) === renderAll("正常第一行\n正常第二行"),
    serialize(box),
  );
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
