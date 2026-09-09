## MODIFIED Requirements

### Requirement: Synthesis timeout SHALL default to 60s with an env override

The answer-synthesis step SHALL use a default timeout of 60 seconds, overridable via the
`CHAT_SYNTHESIS_TIMEOUT` environment variable (seconds, float). Answers taking up to the
configured timeout SHALL complete rather than be killed.

#### Scenario: a 10s synthesis completes
- **GIVEN** `CHAT_SYNTHESIS_TIMEOUT` unset (default 60s) and a synthesis that takes 10s
- **WHEN** the answer is synthesized
- **THEN** it completes successfully (not timed out)

#### Scenario: env override lowers the timeout
- **GIVEN** `CHAT_SYNTHESIS_TIMEOUT=5`
- **WHEN** a synthesis takes 8s
- **THEN** it times out (honoring the override)

## UNCHANGED Requirements
<!-- Synthesis content/prompts, citation format, streaming, retry policy unchanged. -->
