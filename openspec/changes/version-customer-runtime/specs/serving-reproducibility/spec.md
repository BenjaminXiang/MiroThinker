## ADDED Requirements

### Requirement: Deployed runtime is versioned

Every file that runs on the customer node MUST be reproducible from a git ref.
Any file whose bytes exist only on the deployed host is an unversioned behaviour
change and MUST be treated as a defect of the release process, not as a valid
deployment.

#### Scenario: Deployed tree matches the snapshot branch

- **WHEN** `check_runtime_drift.py` compares the deployed `apps/` tree with
  `hotfix/customer-20261026`
- **THEN** every compared file hash matches and the command exits 0

#### Scenario: A hot patch lands on the host only

- **WHEN** any tracked file differs between the deployed tree and the branch
- **THEN** the command lists `path`, `branch_sha256`, `deployed_sha256`
- **AND** exits non-zero, so a deploy or release step can refuse to proceed

### Requirement: Adopted behaviour carries a versioned test

A behaviour that is fixed directly on a deployed host MUST gain a regression
test in the same change, so that a future re-seal cannot silently drop it.

#### Scenario: Cache validation gate

- **WHEN** a candidate answer envelope carries at least one local citation
  (`local-source-*` or `official-source-*`) and a resolvable citation map
- **THEN** it is cacheable even when web citations are also present
- **AND** an envelope with only web citations is rejected

#### Scenario: Topic-professor anchor

- **WHEN** a single-turn query asks `有哪些做 X 的教授` and contains no
  company/enterprise word
- **THEN** no named-company anchor is produced, so the turn is not routed into
  `company→professor` traversal

#### Scenario: Generic person names never anchor

- **WHEN** a pack entity's canonical name is a generic appellation
  (`教授/副教授/讲师/老师/教师/博士/研究员/院士`)
- **THEN** it is excluded from entity linking, so `刘桂良教授` cannot resolve to
  a record literally named `教授`
