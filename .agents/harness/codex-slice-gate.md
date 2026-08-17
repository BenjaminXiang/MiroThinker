# Codex Slice Gate

## MUST PASS BEFORE EXECUTION

A Codex task is allowed to run only if ALL conditions are true:

### 1. OpenSpec linkage
- Task references an openspec/changes/<change-id>

### 2. Slice status
- Slice is explicitly marked: Ready

### 3. Contract exists
- verification-contract.md exists under:
  .agents/runs/<change-id>/

### 4. Scope bounded
- Task has:
  - allowed files
  - forbidden changes
  - stop conditions

---

## FAIL RULE

If ANY condition is false:

→ STOP
→ Do not implement
→ Request clarification or OpenSpec update
