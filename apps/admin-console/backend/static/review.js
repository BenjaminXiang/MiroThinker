"use strict";

class ReviewHttpError extends Error {
  constructor(status, payload) {
    super(payload && payload.code ? payload.code : `HTTP ${status}`);
    this.status = status;
    this.payload = payload || {};
  }
}

const state = {
  workspace: null,
  phase: "registration",
  dirty: false,
  draftTimer: null,
  summaryVisible: false,
  submitting: false,
  confirmedDraftTaskId: null,
  translationBlocksApproval: false,
};

const idempotencyKeys = new Map();
const mutationCoordinator = new ReviewMutationCoordinator();

const elements = {
  workbench: document.getElementById("review-workbench"),
  reviewerName: document.getElementById("reviewer-name"),
  packetHash: document.getElementById("packet-hash"),
  headerProgress: document.getElementById("header-progress"),
  headerPhase: document.getElementById("header-phase"),
  judgeStatus: document.getElementById("judge-status"),
  phaseButtons: Array.from(document.querySelectorAll("[data-phase]")),
  queueProgress: document.getElementById("queue-progress"),
  queueProgressLabel: document.getElementById("queue-progress-label"),
  queueProgressPercent: document.getElementById("queue-progress-percent"),
  queueFilter: document.getElementById("queue-filter"),
  taskList: document.getElementById("task-list"),
  taskKind: document.getElementById("task-kind"),
  taskTitle: document.getElementById("task-title"),
  taskPosition: document.getElementById("task-position"),
  taskInstruction: document.getElementById("task-instruction"),
  taskReadable: document.getElementById("task-readable"),
  rawDetails: document.getElementById("raw-details"),
  rawJson: document.getElementById("raw-json"),
  referencePanel: document.getElementById("reference-prose-panel"),
  referenceProse: document.getElementById("reference-prose"),
  summary: document.getElementById("review-summary"),
  summaryContent: document.getElementById("summary-content"),
  decisionForm: document.getElementById("decision-form"),
  decisionConflict: document.getElementById("decision-conflict"),
  serverFinalDecision: document.getElementById("server-final-decision"),
  unsubmittedDraft: document.getElementById("unsubmitted-draft"),
  confirmDraftSupersede: document.getElementById("confirm-draft-supersede"),
  decisionFieldset: document.getElementById("decision-fieldset"),
  decisionOptions: document.getElementById("decision-options"),
  rationale: document.getElementById("rationale"),
  rationaleHint: document.getElementById("rationale-hint"),
  taskMutabilityStatus: document.getElementById("task-mutability-status"),
  autosaveStatus: document.getElementById("autosave-status"),
  submitDecision: document.getElementById("submit-decision"),
  sealCalibration: document.getElementById("seal-calibration"),
  openExport: document.getElementById("open-export"),
  actionMessage: document.getElementById("action-message"),
  registrationDialog: document.getElementById("registration-dialog"),
  registrationForm: document.getElementById("registration-form"),
  registrationError: document.getElementById("registration-error"),
  exportDialog: document.getElementById("export-dialog"),
  exportForm: document.getElementById("export-form"),
  exportStatus: document.getElementById("export-status"),
  acceptanceExport: document.getElementById("acceptance-export"),
  closeExport: document.getElementById("close-export"),
};

const phaseNames = {
  registration: "评审人登记",
  contract: "合同审核",
  exclusion: "排除审核",
  calibration: "盲标校准",
  summary: "汇总与导出",
};

const taskKindLabels = {
  contract: "合同审核",
  exclusion: "排除审核",
  calibration: "盲标校准",
};

const readOnlyReasons = {
  round_locked: "本轮已锁定，只能查看历史决定。",
  calibration_labels_sealed: "60 条人类盲标已封存，校准任务只能查看。",
  round_not_mutable: "当前轮次状态不允许修改此任务。",
};

const decisionChoices = {
  contract: [
    ["approved", "通过", "完整结构化合同正确，可作为接受依据。"],
    ["needs_change", "需要修改", "存在错误、缺失或要求过度。"],
    ["unable_to_determine", "无法判断", "现有上下文不足以作出决定。"],
  ],
  exclusion: [
    ["accept_exclusion", "接受排除", "现有冻结证据确实不足，可继续保持排除。"],
    ["require_evidence", "要求补证", "该案例不得在缺少新评审证据时排除。"],
    ["unable_to_determine", "无法判断", "现有上下文不足以判断排除是否合理。"],
  ],
  calibration: [
    ["supported", "有证据支持", "给定快照支持候选观察。"],
    ["unsupported", "证据不支持", "给定快照不支持候选观察。"],
    ["unable_to_determine", "无法判断", "给定材料不足；此选择会阻断封存。"],
  ],
};

const fieldLabels = {
  query: "问题",
  family: "案例族",
  as_of: "截至时间",
  required_claims: "必须满足的主张",
  forbidden_claims: "禁止出现的主张",
  required_entities: "必须出现的实体",
  forbidden_entities: "禁止出现的实体",
  allowed_variants: "允许变体",
  enumeration_policy: "枚举规则",
  stage_oracles: "阶段期望",
  evidence_gap_reason: "证据缺口原因",
  requirement: "判断要求",
  candidate_observation: "候选观察",
  evidence_snapshots: "冻结证据快照",
  critical_probe: "关键探针",
  stratum: "校准分层",
};

function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

function makeElement(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text != null) setText(node, text);
  return node;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = { code: "invalid_response" };
  }
  if (!response.ok) {
    if (response.status === 409 && payload.current_revision != null) {
      payload.current_revision = Number(payload.current_revision);
    }
    throw new ReviewHttpError(response.status, payload);
  }
  return payload;
}

function getIdempotencyKey(scope) {
  if (!idempotencyKeys.has(scope)) {
    idempotencyKeys.set(scope, crypto.randomUUID());
  }
  return idempotencyKeys.get(scope);
}

function clearActionMessage() {
  setText(elements.actionMessage, "");
}

function showActionError(error) {
  const code = error instanceof ReviewHttpError ? error.payload.code : "unexpected_error";
  const messages = {
    invalid_session: "会话已失效，请重新登记。",
    stale_revision: "任务已在另一个标签页更新，正在载入最新版本。",
    idempotency_conflict: "本次提交与先前同键请求冲突，请检查最新状态。",
    invalid_decision: "该决定不适用于当前任务，或缺少必填理由。",
    calibration_not_sealed: "需要先完成 60 条有效盲标。",
    judge_unavailable: "评审模型当前不可用，合同和排除审核仍可继续。",
    export_blocked: "当前导出尚未开放或接受门禁未通过。",
  };
  setText(elements.actionMessage, messages[code] || `操作失败：${code}`);
}

function selectedDecision() {
  const checked = elements.decisionOptions.querySelector("input:checked");
  return checked ? checked.value : null;
}

function cancelDraftTimer() {
  if (state.draftTimer != null) window.clearTimeout(state.draftTimer);
  state.draftTimer = null;
}

function markDirty() {
  const task = state.workspace && state.workspace.task;
  if (!task || !task.mutable || state.summaryVisible || state.submitting) return;
  state.dirty = true;
  mutationCoordinator.markDraft();
  elements.autosaveStatus.classList.remove("saved");
  setText(elements.autosaveStatus, "草稿尚未保存…");
  cancelDraftTimer();
  state.draftTimer = window.setTimeout(() => {
    state.draftTimer = null;
    void saveDraft();
  }, 700);
}

async function saveDraft() {
  if (!state.workspace || !state.workspace.task || !state.dirty) return true;
  const task = state.workspace.task;
  if (!task.mutable) return false;
  const captured = mutationCoordinator.capture({
    decision: selectedDecision(),
    rationale: elements.rationale.value,
  });
  setText(elements.autosaveStatus, "正在保存草稿…");
  try {
    await mutationCoordinator.enqueueDraft(
      captured,
      (snapshot) => request(`/api/review/drafts/${encodeURIComponent(snapshot.taskId)}`, {
        method: "PUT",
        body: JSON.stringify(snapshot.payload),
      }),
      (workspace) => {
        state.workspace = workspace;
        state.dirty = false;
        elements.autosaveStatus.classList.add("saved");
        setText(elements.autosaveStatus, "草稿已保存（不计入评审证据）");
        renderHeaderAndQueue();
        if (workspace.task) renderDecisionForm(workspace.task);
      },
    );
    return true;
  } catch (error) {
    if (mutationCoordinator.isCurrent(captured, { matchDraftVersion: true })) {
      setText(elements.autosaveStatus, "草稿保存失败，请勿离开当前任务");
      showActionError(error);
    }
    return false;
  }
}

async function leaveDirtyTask() {
  if (state.submitting) {
    setText(elements.actionMessage, "当前决定正在提交，请等待服务端确认。" );
    return false;
  }
  if (!state.dirty) return true;
  if (!window.confirm("当前草稿尚未保存。现在保存并继续吗？")) return false;
  cancelDraftTimer();
  return saveDraft();
}

function appendDefinition(card, label, value) {
  const list = card.querySelector("dl") || card.appendChild(makeElement("dl"));
  list.append(makeElement("dt", null, label));
  const rendered = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  list.append(makeElement("dd", null, rendered));
}

function buildCard(title) {
  const card = makeElement("section", "review-card");
  card.append(makeElement("h3", null, title));
  return card;
}

function renderPresentationCard(descriptor) {
  const card = buildCard(descriptor.title || "审核材料");
  if (descriptor.purpose) card.classList.add("review-card-purpose");
  if (descriptor.warning) card.classList.add("review-card-warning");
  for (const paragraph of descriptor.paragraphs || []) {
    card.append(makeElement("p", null, paragraph));
  }
  if (descriptor.facts && descriptor.facts.length) {
    const list = makeElement("dl", "review-facts");
    for (const fact of descriptor.facts) {
      list.append(
        makeElement("dt", null, fact.label),
        makeElement("dd", null, fact.value),
      );
    }
    card.append(list);
  }
  if (descriptor.checks && descriptor.checks.length) {
    const list = makeElement("ul", "review-checklist");
    for (const check of descriptor.checks) list.append(makeElement("li", null, check));
    card.append(list);
  }
  return card;
}

function reviewPresentation(kind, payload, context) {
  const presenter = window.ReviewPresentation;
  const method = {
    contract: "presentContract",
    exclusion: "presentExclusion",
    calibration: "presentCalibration",
  }[kind];
  if (!presenter || !method || typeof presenter[method] !== "function") {
    return {
      instruction: "可读审核说明未能载入。请查看冻结原始结构，并不要选择“通过”。",
      cards: [{
        title: "审核说明不可用",
        paragraphs: ["页面无法安全翻译当前结构化材料。"],
        warning: true,
      }],
      blocksApproval: kind === "contract",
    };
  }
  try {
    return kind === "exclusion"
      ? presenter[method](payload, context)
      : presenter[method](payload);
  } catch (_error) {
    return {
      instruction: "可读审核说明无法生成。请查看冻结原始结构，并不要选择“通过”。",
      cards: [{
        title: "审核说明不可用",
        paragraphs: ["当前材料没有被安全翻译为审核清单。"],
        warning: true,
      }],
      blocksApproval: kind === "contract",
    };
  }
}

function renderTaskPresentation(presentation) {
  for (const descriptor of presentation.cards || []) {
    elements.taskReadable.append(renderPresentationCard(descriptor));
  }
}

function renderContract(task) {
  const presentation = reviewPresentation("contract", task.payload, null);
  state.translationBlocksApproval = Boolean(presentation.blocksApproval);
  renderTaskPresentation(presentation);
  setText(elements.taskInstruction, presentation.instruction);
}

function renderExclusion(task) {
  const context = task.review_context || {};
  const presentation = reviewPresentation("exclusion", task.payload, context);
  renderTaskPresentation(presentation);
  if (context.reference_prose) {
    elements.referencePanel.hidden = false;
    setText(elements.referenceProse, context.reference_prose.content);
  }
  setText(elements.taskInstruction, presentation.instruction);
}

function renderCalibration(task) {
  const presentation = reviewPresentation("calibration", task.payload, null);
  renderTaskPresentation(presentation);
  if (task.model_judgment && state.workspace.lifecycle !== "in_progress") {
    const revealed = buildCard("封存后模型判断");
    appendDefinition(
      revealed,
      "模型判断",
      task.model_judgment === "supported" ? "有证据支持" : "证据不支持",
    );
    appendDefinition(revealed, "响应哈希", task.judge_response_sha256);
    elements.taskReadable.append(revealed);
  }
  setText(elements.taskInstruction, presentation.instruction);
}

function renderDecisionForm(task) {
  const choices = decisionChoices[task.kind] || [];
  const draftConfirmed = state.confirmedDraftTaskId === task.task_id;
  const presentation = reconcileDecisionPresentation(task, draftConfirmed);
  const selected = presentation.decision;
  const approvalBlocked = task.kind === "contract" && state.translationBlocksApproval;
  const fragment = document.createDocumentFragment();
  for (const [value, label, description] of choices) {
    const wrapper = makeElement("label", "decision-choice");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "decision";
    input.value = value;
    input.checked = selected === value;
    input.disabled = approvalBlocked && value === "approved";
    input.addEventListener("change", markDirty);
    const copy = makeElement("span");
    copy.append(makeElement("strong", null, label));
    copy.append(makeElement("small", null, description));
    wrapper.append(input, copy);
    fragment.append(wrapper);
  }
  elements.decisionOptions.replaceChildren(fragment);
  elements.rationale.value = presentation.rationale;
  elements.decisionConflict.hidden = !presentation.hasConflict;
  setText(
    elements.serverFinalDecision,
    presentation.hasConflict ? JSON.stringify(task.current_decision, null, 2) : "",
  );
  setText(
    elements.unsubmittedDraft,
    presentation.hasConflict ? JSON.stringify(task.draft, null, 2) : "",
  );
  elements.confirmDraftSupersede.hidden = !presentation.requiresDraftConfirmation;
  elements.rationale.disabled = !presentation.editable;
  elements.decisionFieldset.disabled = !presentation.editable;
  elements.submitDecision.disabled = !presentation.editable || (approvalBlocked && selected === "approved");
  setText(
    elements.taskMutabilityStatus,
    approvalBlocked
      ? "当前合同含有页面未支持的结构；请查看原始结构并选择“需要修改”或“无法判断”。"
      : presentation.requiresDraftConfirmation
      ? "服务端正式结论优先；确认后才能按草稿改判。"
      : (task.mutable ? "当前任务可编辑。" : (readOnlyReasons[task.read_only_reason] || "当前任务只读。")),
  );
  setText(
    elements.rationaleHint,
    task.kind === "exclusion"
      ? "排除审核始终需要理由。"
      : "需要修改、无法判断或改判时必须填写理由。",
  );
  elements.autosaveStatus.classList.remove("saved");
  setText(
    elements.autosaveStatus,
    presentation.requiresDraftConfirmation
      ? "未提交草稿尚未启用"
      : (task.mutable ? (task.draft ? "已恢复未提交草稿" : "尚无草稿") : "只读状态不会自动保存或提交"),
  );
}

function renderTask() {
  const workspace = state.workspace;
  const task = workspace && workspace.task;
  elements.taskReadable.replaceChildren();
  elements.referencePanel.hidden = true;
  elements.summary.hidden = true;
  elements.rawDetails.hidden = !task;
  elements.decisionForm.hidden = !task;
  state.summaryVisible = false;
  state.translationBlocksApproval = false;

  if (!task) {
    setText(elements.taskKind, "无待办任务");
    setText(elements.taskTitle, "当前阶段没有待处理项目");
    setText(elements.taskPosition, "— / 112");
    setText(elements.taskInstruction, "可前往汇总查看服务端门禁状态，或从左侧打开已提交任务进行复核。" );
    elements.decisionOptions.replaceChildren();
    elements.submitDecision.disabled = true;
    setText(elements.taskMutabilityStatus, "当前没有可编辑任务。" );
    return;
  }

  setText(elements.taskKind, taskKindLabels[task.kind]);
  setText(elements.taskTitle, task.task_id);
  setText(elements.taskPosition, `${workspace.progress.current_position || "—"} / ${workspace.progress.total}`);
  setText(elements.rawJson, JSON.stringify({ payload: task.payload, review_context: task.review_context }, null, 2));
  if (task.kind === "contract") renderContract(task);
  if (task.kind === "exclusion") renderExclusion(task);
  if (task.kind === "calibration") renderCalibration(task);
  renderDecisionForm(task);
}

function renderQueue() {
  const workspace = state.workspace;
  if (!workspace) {
    elements.taskList.replaceChildren();
    return;
  }
  const filter = elements.queueFilter.value;
  const queue = workspace.queue.filter((item) => {
    if (["contract", "exclusion", "calibration"].includes(state.phase) && item.kind !== state.phase) return false;
    return filter === "all" || item.status === filter;
  });
  const fragment = document.createDocumentFragment();
  for (const item of queue) {
    const row = makeElement("li");
    const button = makeElement("button");
    button.type = "button";
    button.dataset.taskId = item.task_id;
    if (workspace.task && workspace.task.task_id === item.task_id) button.classList.add("active");
    if (item.status === "submitted") button.classList.add("submitted");
    button.append(
      makeElement("span", "task-number", String(item.position).padStart(3, "0")),
      makeElement("span", "task-name", item.task_id),
    );
    button.addEventListener("click", () => void openTask(item.task_id));
    row.append(button);
    fragment.append(row);
  }
  elements.taskList.replaceChildren(fragment);
}

function renderHeaderAndQueue() {
  const workspace = state.workspace;
  if (!workspace) return;
  setText(elements.reviewerName, workspace.reviewer.display_name);
  const packet = workspace.artifact_identity.packet_raw_sha256;
  setText(elements.packetHash, `${packet.slice(0, 12)}…${packet.slice(-8)}`);
  elements.packetHash.title = packet;
  setText(elements.headerProgress, `${workspace.progress.submitted} / ${workspace.progress.total}`);
  setText(elements.headerPhase, phaseNames[state.phase] || state.phase);
  const percent = Math.round((workspace.progress.submitted / workspace.progress.total) * 100);
  elements.queueProgress.value = workspace.progress.submitted;
  elements.queueProgress.max = workspace.progress.total;
  setText(elements.queueProgressLabel, `${workspace.progress.remaining} 项待提交`);
  setText(elements.queueProgressPercent, `${percent}%`);
  if (workspace.judge_configured) {
    elements.judgeStatus.classList.add("configured");
    setText(elements.judgeStatus, "评审模型已配置；完成 60 条有效盲标后可执行封存。" );
  } else {
    elements.judgeStatus.classList.remove("configured");
    setText(elements.judgeStatus, "评审模型未配置：合同与排除审核可继续，盲标封存暂停。" );
  }
  for (const button of elements.phaseButtons) {
    button.classList.toggle("active", button.dataset.phase === state.phase);
  }
  const gate = workspace.gate_summary;
  elements.sealCalibration.disabled = !(
    workspace.judge_configured
    && gate.calibration_labels_valid
    && gate.calibration_ready_to_seal
  );
  elements.acceptanceExport.disabled = !gate.acceptance_ready;
  renderQueue();
}

function renderSummary() {
  const workspace = state.workspace;
  if (!workspace) return;
  state.summaryVisible = true;
  elements.summary.hidden = false;
  elements.decisionForm.hidden = true;
  elements.rawDetails.hidden = true;
  elements.referencePanel.hidden = true;
  elements.taskReadable.replaceChildren();
  setText(elements.taskKind, "服务端汇总");
  setText(elements.taskTitle, "评审进度与接受门禁");
  setText(elements.taskPosition, `${workspace.progress.submitted} / ${workspace.progress.total}`);
  setText(elements.taskInstruction, "这里仅呈现服务端计算结果；完成表单不等于 Task 2.8 已接受。" );
  const gate = workspace.gate_summary;
  const statusCard = buildCard("服务端接受门禁");
  appendDefinition(statusCard, "生命周期", workspace.lifecycle);
  appendDefinition(statusCard, "接受就绪", gate.acceptance_ready ? "是" : "否");
  appendDefinition(statusCard, "接受阻断原因", gate.acceptance_blockers);
  appendDefinition(statusCard, "缺失任务数", gate.missing_task_ids.length);
  appendDefinition(statusCard, "缺失任务 IDs", gate.missing_task_ids);
  appendDefinition(statusCard, "阻断任务 IDs", gate.blocking_task_ids);
  appendDefinition(statusCard, "阻断任务原因", gate.blocking_reasons);
  appendDefinition(statusCard, "60 条标签全部有效", gate.calibration_labels_valid ? "是" : "否");
  appendDefinition(statusCard, "允许启动封存", gate.calibration_ready_to_seal ? "是" : "否");

  const coverageCard = buildCard("服务端覆盖核算");
  appendDefinition(coverageCard, "案例族覆盖", gate.family_coverage);
  appendDefinition(coverageCard, "校准分层覆盖", gate.stratum_coverage);

  const artifactCard = buildCard("冻结工件标识");
  appendDefinition(artifactCard, "全部绑定哈希", workspace.artifact_identity);

  const cards = [statusCard, coverageCard, artifactCard];
  if (workspace.calibration) {
    const calibration = workspace.calibration;
    const calibrationCard = buildCard("封存后校准证据");
    appendDefinition(calibrationCard, "配对数量", calibration.pair_count);
    appendDefinition(calibrationCard, "分层计数", calibration.stratum_counts);
    appendDefinition(calibrationCard, "人类支持", calibration.human_supported);
    appendDefinition(calibrationCard, "人类不支持", calibration.human_unsupported);
    appendDefinition(calibrationCard, "关键探针中的人类不支持", calibration.unsupported_critical_probes);
    appendDefinition(calibrationCard, "精确一致率", calibration.agreement);
    appendDefinition(calibrationCard, "混淆矩阵", calibration.confusion_matrix);
    appendDefinition(calibrationCard, "关键错误接受", calibration.critical_false_accepts);
    appendDefinition(calibrationCard, "全部校准门禁", calibration.gates);
    appendDefinition(calibrationCard, "校准是否通过", calibration.passed ? "通过" : "未通过");
    appendDefinition(calibrationCard, "模型标识", calibration.model_id);
    appendDefinition(calibrationCard, "校准策略标识", calibration.calibration_policy_id);
    appendDefinition(calibrationCard, "评审模型策略标识", calibration.judge_policy_id);
    appendDefinition(calibrationCard, "授权哈希", calibration.authorization_sha256);
    appendDefinition(calibrationCard, "人类标签快照哈希", calibration.human_snapshot_sha256);
    const judgmentDetails = makeElement("details", "judgment-details");
    judgmentDetails.append(
      makeElement("summary", null, `查看 ${calibration.judgments.length} 条配对判断`),
      makeElement("pre", null, JSON.stringify(calibration.judgments, null, 2)),
    );
    calibrationCard.append(judgmentDetails);
    cards.push(calibrationCard);
  } else {
    const blindCard = buildCard("盲标状态");
    appendDefinition(blindCard, "校准状态", "尚未封存；模型结果保持隐藏");
    cards.push(blindCard);
  }
  elements.summaryContent.replaceChildren(...cards);
}

function renderWorkspace(workspace, { preserveActionMessage = false } = {}) {
  cancelDraftTimer();
  state.confirmedDraftTaskId = null;
  if (workspace.task) mutationCoordinator.activate(workspace.task.task_id);
  else if (mutationCoordinator.currentTaskId != null) mutationCoordinator.invalidate();
  state.workspace = workspace;
  state.dirty = false;
  if (!preserveActionMessage) clearActionMessage();
  if (workspace.task && !state.summaryVisible) state.phase = workspace.task.kind;
  renderHeaderAndQueue();
  if (state.phase === "summary") renderSummary();
  else renderTask();
  elements.workbench.setAttribute("aria-busy", "false");
}

async function openTask(taskId) {
  if (!(await leaveDirtyTask())) return;
  clearActionMessage();
  const previousTaskId = mutationCoordinator.currentTaskId;
  mutationCoordinator.invalidate();
  try {
    const workspace = await request(`/api/review/workspace?task_id=${encodeURIComponent(taskId)}`);
    state.phase = workspace.task ? workspace.task.kind : state.phase;
    renderWorkspace(workspace);
  } catch (error) {
    if (previousTaskId != null) mutationCoordinator.activate(previousTaskId);
    showActionError(error);
  }
}

async function openPhase(phase) {
  if (phase === "registration") {
    if (!elements.registrationDialog.open) elements.registrationDialog.showModal();
    return;
  }
  if (!(await leaveDirtyTask()) || !state.workspace) return;
  state.phase = phase;
  if (phase === "summary") {
    renderHeaderAndQueue();
    renderSummary();
    return;
  }
  state.summaryVisible = false;
  const next = state.workspace.queue.find((item) => item.kind === phase && item.status === "pending")
    || state.workspace.queue.find((item) => item.kind === phase);
  if (next) await openTask(next.task_id);
  else {
    renderHeaderAndQueue();
    renderTask();
  }
}

async function submitDecision(event) {
  event.preventDefault();
  clearActionMessage();
  if (!state.workspace || !state.workspace.task) return;
  const task = state.workspace.task;
  if (!task.mutable) {
    setText(elements.actionMessage, "当前任务为只读状态，不能保存草稿或提交决定。" );
    return;
  }
  const presentation = reconcileDecisionPresentation(
    task,
    state.confirmedDraftTaskId === task.task_id,
  );
  if (presentation.requiresDraftConfirmation) {
    setText(elements.actionMessage, "请先点击“确认按草稿改判”，再提交新的正式结论。" );
    return;
  }
  const decision = selectedDecision();
  if (!decision) {
    setText(elements.actionMessage, "请选择一个决定。" );
    return;
  }
  const rationale = elements.rationale.value.trim() || null;
  const scope = JSON.stringify({
    round: state.workspace.round_id,
    task: task.task_id,
    revision: task.revision,
    decision,
    rationale,
  });
  const idempotencyKey = getIdempotencyKey(`decision:${scope}`);
  const captured = mutationCoordinator.capture({
    task_id: task.task_id,
    task_kind: task.kind,
    decision,
    rationale,
    expected_revision: task.revision,
    idempotency_key: idempotencyKey,
  });
  cancelDraftTimer();
  state.submitting = true;
  elements.decisionFieldset.disabled = true;
  elements.rationale.disabled = true;
  elements.submitDecision.disabled = true;
  try {
    if (state.dirty && !(await saveDraft())) return;
    await mutationCoordinator.enqueueFinal(
      captured,
      (snapshot) => request("/api/review/decisions", {
        method: "POST",
        body: JSON.stringify(snapshot.payload),
      }),
      (workspace) => renderWorkspace(workspace),
    );
    idempotencyKeys.delete(`decision:${scope}`);
  } catch (error) {
    if (mutationCoordinator.isCurrent(captured)) showActionError(error);
    if (error instanceof ReviewHttpError && error.status === 409 && error.payload.current_revision != null) {
      const staleError = error;
      idempotencyKeys.delete(`decision:${scope}`);
      mutationCoordinator.invalidate();
      try {
        const workspace = await request(
          `/api/review/drafts/${encodeURIComponent(captured.taskId)}`,
          {
            method: "PUT",
            body: JSON.stringify({
              decision: captured.payload.decision,
              rationale: captured.payload.rationale,
            }),
          },
        );
        renderWorkspace(workspace, { preserveActionMessage: true });
        showActionError(staleError);
      } catch (reloadError) {
        mutationCoordinator.activate(captured.taskId);
        showActionError(reloadError);
      }
    }
  } finally {
    state.submitting = false;
    const currentTask = state.workspace && state.workspace.task;
    const currentPresentation = currentTask
      ? reconcileDecisionPresentation(
        currentTask,
        state.confirmedDraftTaskId === currentTask.task_id,
      )
      : null;
    const editable = Boolean(currentPresentation && currentPresentation.editable);
    elements.decisionFieldset.disabled = !editable;
    elements.rationale.disabled = !editable;
    elements.submitDecision.disabled = !editable;
  }
}

async function sealCalibration() {
  if (!state.workspace) return;
  const scope = `seal:${state.workspace.round_id}`;
  const key = getIdempotencyKey(scope);
  elements.sealCalibration.disabled = true;
  clearActionMessage();
  try {
    const workspace = await request("/api/review/calibration/seal", {
      method: "POST",
      body: JSON.stringify({ expected_revision: 60, idempotency_key: key }),
    });
    idempotencyKeys.delete(scope);
    renderWorkspace(workspace);
  } catch (error) {
    showActionError(error);
    if (error instanceof ReviewHttpError && error.payload.code === "judge_unavailable") {
      idempotencyKeys.delete(scope);
      setText(elements.actionMessage, "评审模型运行失败；再次点击将启动新的评审模型运行。" );
    }
  } finally {
    renderHeaderAndQueue();
  }
}

async function createExport(event) {
  event.preventDefault();
  if (!state.workspace) return;
  const selected = elements.exportForm.querySelector('input[name="export_mode"]:checked');
  const mode = selected ? selected.value : "review_evidence";
  const scope = `export:${state.workspace.round_id}:${mode}`;
  const key = getIdempotencyKey(scope);
  setText(elements.exportStatus, "正在生成并复验导出…");
  try {
    const receipt = await request("/api/review/exports", {
      method: "POST",
      body: JSON.stringify({ mode, idempotency_key: key }),
    });
    idempotencyKeys.delete(scope);
    setText(elements.exportStatus, `导出已生成：${receipt.export_id}（${receipt.content_sha256}）`);
  } catch (error) {
    const code = error instanceof ReviewHttpError ? error.payload.code : "unexpected_error";
    setText(elements.exportStatus, `导出失败：${code}`);
  }
}

async function registerReviewer(event) {
  event.preventDefault();
  setText(elements.registrationError, "");
  const data = new FormData(elements.registrationForm);
  try {
    const workspace = await request("/api/review/sessions", {
      method: "POST",
      body: JSON.stringify({
        display_name: data.get("display_name"),
        staff_id: data.get("staff_id"),
      }),
    });
    elements.registrationDialog.close();
    renderWorkspace(workspace);
  } catch (error) {
    const code = error instanceof ReviewHttpError ? error.payload.code : "unexpected_error";
    setText(elements.registrationError, `登记失败：${code}`);
  }
}

async function initialize() {
  for (const button of elements.phaseButtons) {
    button.addEventListener("click", () => void openPhase(button.dataset.phase));
  }
  elements.queueFilter.addEventListener("change", renderQueue);
  elements.rationale.addEventListener("input", markDirty);
  elements.confirmDraftSupersede.addEventListener("click", () => {
    const task = state.workspace && state.workspace.task;
    if (!task || !task.current_decision || !task.draft || !task.mutable) return;
    state.confirmedDraftTaskId = task.task_id;
    renderDecisionForm(task);
    setText(elements.actionMessage, "已确认按草稿改判；提交后将生成新的可追溯版本。" );
  });
  elements.decisionForm.addEventListener("submit", (event) => void submitDecision(event));
  elements.registrationForm.addEventListener("submit", (event) => void registerReviewer(event));
  elements.sealCalibration.addEventListener("click", () => void sealCalibration());
  elements.openExport.addEventListener("click", () => elements.exportDialog.showModal());
  elements.closeExport.addEventListener("click", () => elements.exportDialog.close());
  elements.exportForm.addEventListener("submit", (event) => void createExport(event));
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty && !state.submitting) return;
    event.preventDefault();
    event.returnValue = "";
  });

  try {
    const workspace = await request("/api/review/workspace");
    renderWorkspace(workspace);
  } catch (error) {
    if (error instanceof ReviewHttpError && error.status === 401) {
      elements.workbench.setAttribute("aria-busy", "false");
      elements.registrationDialog.showModal();
      return;
    }
    showActionError(error);
    elements.workbench.setAttribute("aria-busy", "false");
  }
}

void initialize();
