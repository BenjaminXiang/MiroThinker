# AGENTS.md

## Claude Cross Review Routing

When the user asks for Claude to review, cross-check, validate, or leave review comments on Codex-produced changes, treat that as a request to run the repo-local Claude cross-review workflow.

Authority and transport rules:

- Codex CLI remains the session orchestrator. It owns task routing, gathers context, decides the review scope, invokes local Claude when needed, and is responsible for the final answer to the user.
- Claude is used through the locally installed `claude` command as an independent executor or reviewer, depending on task type.
- Do not use web search, browser automation, direct HTTP calls, external Anthropic API clients, or any alternate Claude access path for this workflow.
- If the review request is ambiguous, ask the user concise follow-up questions before invoking Claude. Typical ambiguities are: review scope, target files, base ref, and whether a plan/spec should be attached.

Default ownership model:

- Implementation and code changes: `Codex -> Claude -> Codex`
  - Codex writes the code.
  - Claude reviews the resulting artifacts.
  - The findings flow back to Codex.
  - Codex fixes problems, tightens weak areas, and can make adjacent optimizations that materially improve the result.
- Plan review, code review, and review-comment generation: `Claude -> Codex`
  - Codex invokes local Claude as the primary reviewer.
  - Claude produces the main review artifact.
  - The review artifact flows back to Codex.
  - Codex verifies that the review is grounded in the raw plan/diff/files, filters out weak findings, and then either applies fixes or presents the validated findings to the user.

Workflow:

1. Read [local-skills/claude-cross-review/SKILL.md](local-skills/claude-cross-review/SKILL.md).
2. Run `python3 scripts/claude_review.py` with the scope that matches the request:
   - Current uncommitted work: no extra flags
   - Staged changes: `--staged`
   - Branch diff against a base ref: `--base-ref origin/main`
   - Only the files Codex touched: `--path <file-or-dir>` repeated as needed
   - Plan-driven review: add `--plan <path>`
3. Treat Claude's findings as an independent review artifact that must flow back into Codex.
4. Codex must then do one of the following for each material finding:
   - fix it
   - make a justified decision to waive it
   - surface it clearly to the user
5. After applying fixes, Codex may also improve adjacent weak spots revealed by the review, not just the exact line-item findings.
6. Do not mark the task complete until this loop is closed.

Automatic trigger:

- Before declaring completion on changes that touch auth, permissions, persistence, data mutations, external APIs, background jobs, or deletion/update flows, run the Claude cross-review workflow even if the user only asked for stronger validation rather than naming Claude explicitly.
- If the worktree contains unrelated edits, narrow the review with `--path` or `--staged` instead of reviewing the whole tree.
- If the user gives a more specific review scope, their explicit scope wins.
