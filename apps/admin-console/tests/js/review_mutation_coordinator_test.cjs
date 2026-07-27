"use strict";

const assert = require("node:assert/strict");
const {
  ReviewMutationCoordinator,
  reconcileDecisionPresentation,
} = require("../../backend/static/review_mutation_coordinator.js");

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function lateTaskAResponsesCannotReplaceTaskBOrBorrowItsValues() {
  const coordinator = new ReviewMutationCoordinator();
  const draftResponse = deferred();
  const requests = [];
  const applied = [];

  coordinator.activate("contract:A");
  coordinator.markDraft();
  const draftA = coordinator.capture({
    decision: "needs_change",
    rationale: "A draft",
  });
  const pendingDraft = coordinator.enqueueDraft(
    draftA,
    async (captured) => {
      requests.push(["draft", captured.taskId, captured.payload.rationale]);
      return draftResponse.promise;
    },
    (workspace) => applied.push(["draft", workspace.task.task_id]),
  );
  const finalA = coordinator.capture({
    task_id: "contract:A",
    decision: "approved",
    rationale: "A final",
  });
  const pendingFinal = coordinator.enqueueFinal(
    finalA,
    async (captured) => {
      requests.push(["final", captured.taskId, captured.payload.rationale]);
      return { task: { task_id: "contract:A" } };
    },
    (workspace) => applied.push(["final", workspace.task.task_id]),
  );

  await Promise.resolve();
  assert.deepEqual(requests, [["draft", "contract:A", "A draft"]]);

  coordinator.invalidate();
  coordinator.activate("contract:B");
  const visibleTaskBValues = { decision: "needs_change", rationale: "B visible" };
  assert.equal(visibleTaskBValues.rationale, "B visible");

  draftResponse.resolve({ task: { task_id: "contract:A" } });
  await Promise.all([pendingDraft, pendingFinal]);

  assert.deepEqual(requests, [
    ["draft", "contract:A", "A draft"],
    ["final", "contract:A", "A final"],
  ]);
  assert.deepEqual(applied, []);
  assert.equal(coordinator.currentTaskId, "contract:B");
}

async function finalMutationRunsAfterItsDraftAndAppliesLast() {
  const coordinator = new ReviewMutationCoordinator();
  const draftResponse = deferred();
  const events = [];

  coordinator.activate("contract:A");
  coordinator.markDraft();
  const draft = coordinator.capture({ rationale: "draft" });
  const pendingDraft = coordinator.enqueueDraft(
    draft,
    async () => {
      events.push("draft:start");
      const value = await draftResponse.promise;
      events.push("draft:end");
      return value;
    },
    () => events.push("draft:apply"),
  );
  const final = coordinator.capture({ rationale: "final" });
  const pendingFinal = coordinator.enqueueFinal(
    final,
    async () => {
      events.push("final:start");
      return { ok: true };
    },
    () => events.push("final:apply"),
  );

  await Promise.resolve();
  assert.deepEqual(events, ["draft:start"]);
  draftResponse.resolve({ ok: true });
  await Promise.all([pendingDraft, pendingFinal]);

  assert.deepEqual(events, [
    "draft:start",
    "draft:end",
    "draft:apply",
    "final:start",
    "final:apply",
  ]);
}

function sharedDraftNeverSilentlyOverridesTheServerFinal() {
  const task = {
    mutable: true,
    current_decision: { decision: "approved", rationale: "server final" },
    draft: { decision: "needs_change", rationale: "stale local draft" },
  };

  const safeDefault = reconcileDecisionPresentation(task, false);
  assert.deepEqual(safeDefault, {
    decision: "approved",
    rationale: "server final",
    hasConflict: true,
    requiresDraftConfirmation: true,
    editable: false,
  });

  const confirmed = reconcileDecisionPresentation(task, true);
  assert.deepEqual(confirmed, {
    decision: "needs_change",
    rationale: "stale local draft",
    hasConflict: true,
    requiresDraftConfirmation: false,
    editable: true,
  });
}

Promise.resolve()
  .then(lateTaskAResponsesCannotReplaceTaskBOrBorrowItsValues)
  .then(finalMutationRunsAfterItsDraftAndAppliesLast)
  .then(sharedDraftNeverSilentlyOverridesTheServerFinal)
  .catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  });
