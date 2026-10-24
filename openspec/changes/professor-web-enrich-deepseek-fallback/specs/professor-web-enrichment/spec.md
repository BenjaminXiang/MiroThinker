## ADDED Requirements

### Requirement: Professor enrichment prefers the DeepSeek search API

Professor web enrichment MUST build its search provider as an ordered chain:
DeepSeek first, Bocha second, Serper only when a Serper key is configured. A
provider that raises or returns no organic results MUST fall through to the next
provider without aborting the professor task.

#### Scenario: DeepSeek answers

- **WHEN** a professor task issues a search query and the DeepSeek provider
  returns at least one organic result
- **THEN** the task uses that result set
- **AND** the Bocha and Serper providers are not called for that query

#### Scenario: DeepSeek errors or returns nothing

- **WHEN** the DeepSeek provider raises or returns `{"organic": []}`
- **THEN** the same query is retried against the next configured provider
- **AND** the professor task continues instead of failing on a dead provider

#### Scenario: No provider is configured

- **WHEN** no DeepSeek key, no Bocha endpoint, and no Serper key are available
- **THEN** the enrichment runs without a search provider, matching the existing
  `skip_web_search` behavior

### Requirement: The enrichment ops script is runnable from any working directory

`scripts/run_professor_web_enrich.py` MUST resolve the application root from its
own path and insert it into `sys.path` before importing `src.data_agents`, so a
job subprocess can start it without `PYTHONPATH` or a specific cwd.

#### Scenario: Started from a neutral directory

- **WHEN** the script is started as
  `python /path/to/apps/miroflow-agent/scripts/run_professor_web_enrich.py --help`
  from `/tmp`
- **THEN** it prints usage and exits zero instead of raising `ModuleNotFoundError`
