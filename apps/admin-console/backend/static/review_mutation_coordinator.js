"use strict";

(function installReviewMutationCoordinator(root) {
  function clonePayload(payload) {
    if (typeof structuredClone === "function") return structuredClone(payload);
    return JSON.parse(JSON.stringify(payload));
  }

  function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.freeze(value);
      for (const child of Object.values(value)) deepFreeze(child);
    }
    return value;
  }

  function reconcileDecisionPresentation(task, draftConfirmed) {
    const current = task && task.current_decision;
    const draft = task && task.draft;
    const hasConflict = Boolean(current && draft);
    const useDraft = Boolean(
      draft && (!current || (hasConflict && draftConfirmed)),
    );
    const presented = useDraft ? draft : (current || draft || {});
    const requiresDraftConfirmation = hasConflict && !draftConfirmed;
    return {
      decision: presented.decision || null,
      rationale: presented.rationale || "",
      hasConflict,
      requiresDraftConfirmation,
      editable: Boolean(task && task.mutable && !requiresDraftConfirmation),
    };
  }

  class ReviewMutationCoordinator {
    constructor() {
      this._currentTaskId = null;
      this._epoch = 0;
      this._draftVersion = 0;
      this._tail = Promise.resolve();
    }

    get currentTaskId() {
      return this._currentTaskId;
    }

    activate(taskId) {
      if (typeof taskId !== "string" || taskId.length === 0) {
        throw new TypeError("taskId must be a non-empty string");
      }
      if (taskId !== this._currentTaskId) {
        this._epoch += 1;
        this._currentTaskId = taskId;
        this._draftVersion = 0;
      }
    }

    invalidate() {
      this._epoch += 1;
      this._currentTaskId = null;
      this._draftVersion = 0;
    }

    markDraft() {
      if (this._currentTaskId == null) return 0;
      this._draftVersion += 1;
      return this._draftVersion;
    }

    capture(payload) {
      if (this._currentTaskId == null) {
        throw new Error("cannot capture a mutation without an active task");
      }
      return deepFreeze({
        taskId: this._currentTaskId,
        epoch: this._epoch,
        draftVersion: this._draftVersion,
        payload: clonePayload(payload),
      });
    }

    isCurrent(captured, { matchDraftVersion = false } = {}) {
      return Boolean(
        captured
        && captured.taskId === this._currentTaskId
        && captured.epoch === this._epoch
        && (!matchDraftVersion || captured.draftVersion === this._draftVersion),
      );
    }

    enqueueDraft(captured, operation, apply) {
      return this._enqueue(captured, operation, apply, true);
    }

    enqueueFinal(captured, operation, apply) {
      return this._enqueue(captured, operation, apply, false);
    }

    _enqueue(captured, operation, apply, matchDraftVersion) {
      const run = async () => {
        const result = await operation(captured);
        if (this.isCurrent(captured, { matchDraftVersion })) apply(result);
        return result;
      };
      const pending = this._tail.then(run, run);
      this._tail = pending.catch(() => undefined);
      return pending;
    }
  }

  root.ReviewMutationCoordinator = ReviewMutationCoordinator;
  root.reconcileDecisionPresentation = reconcileDecisionPresentation;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { ReviewMutationCoordinator, reconcileDecisionPresentation };
  }
})(globalThis);
