# OpenSpec + Superpowers Harness

This harness keeps Superpowers useful without letting TDD choose the behavior contract.

## Rule

OpenSpec defines behavior and verification intent. Superpowers executes the engineering discipline. For behavior-affecting work, `.agents/runs/<change-id>/verification-contract.md` selects RED before production-code edits.

TDD is not the default best practice for all vibe coding in this repo. It is allowed for deterministic units and contracts after the behavior boundary is known. For agentic behavior, recurring defects, or ambiguous badcases, use OpenSpec exploration, systematic debugging, pattern-repair, eval-first, trace replay, and code review before using TDD for any extracted deterministic pieces.

Weak oracles are treated as incomplete. A verification contract should not rely only on one exact string, one DOM node, one snapshot, or one visible input. Web/UI changes need browser/API/state workflow evidence; mock-heavy tests need a complementary real interaction, contract, trace, or browser check.

## Hook Script

Use `.agents/harness/openspec_superpowers_gate.py` as a pre-edit gate for high-risk Agentic RAG/chat and agent-behavior paths.

Recommended first enablement: pre-edit only. Do not enable full diff/stop enforcement in a dirty workspace, because it evaluates old uncommitted work too.

Claude Code local settings example:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/.agents/harness/openspec_superpowers_gate.py\" pretool",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

For other clients, wire the same command to the equivalent pre-edit hook. Set `OPENSPEC_CHANGE_ID=<change-id>` when more than one active change exists.

Manual check:

```bash
python3 .agents/harness/openspec_superpowers_gate.py contract .agents/runs/<change-id>/verification-contract.md
python3 .agents/harness/openspec_superpowers_gate.py diff
```

Use `.agents/harness/verification-contract.examples.md` as calibration examples for deterministic, agentic/chat, web/UI, and systemic-defect changes.
