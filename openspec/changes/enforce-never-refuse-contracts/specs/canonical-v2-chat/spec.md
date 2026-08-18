## ADDED Requirements

### Requirement: Never-Refuse Fallback Wording

The last-resort fallback answer SHALL follow the contract form: the subject
(anchor display name, or the query's named subject when no anchor exists)
appears in the first sentence; at least one confirmed fact or the explicit
statement that only identity-level information is confirmed; the gap is named
as a coverage fact ("本地库暂未覆盖…"); one actionable next step. It SHALL NOT
contain brush-off refusals ("换个角度继续提问" as the whole content,
"暂未能确认您问的具体内容" alone) or subject-less text.

#### Scenario: bare-name fallback names the subject

- **WHEN** a bare-name first turn degrades to the fallback text
- **THEN** the answer's first sentence contains the entity name and the text
  names what is confirmed and what is missing — no refusal-form ending

### Requirement: No External-Database Deflection

Answers SHALL NOT recommend external databases or search platforms
(国家知识产权局/PatSnap/Incopat/专利数据库/专利检索平台 …) as the substance of
the answer when the turn produced no evidence from that source. When the
deflection pattern matches and no patent evidence exists, the answer SHALL be
rewritten to: subject named, the coverage gap stated as a data fact
（本地专利关联暂未建立）, and confirmed non-patent facts retained.

#### Scenario: patent deflection rewritten (P5 form)

- **WHEN** synthesis produces "建议访问国家知识产权局…" over a turn whose
  patent/relation lanes returned zero candidates
- **THEN** the shipped answer names the company, states the local patent
  relation is not yet built, and keeps confirmed company facts
- **AND** contains no external-database recommendation

### Requirement: Lane-Failure Semantic Correction

"检索无结果" and "通道不可用" are distinct answer states. When the turn's
evidence traces show every web provider attempt errored or timed out (the
web-lane-unavailable condition), the answer SHALL state
网络检索暂不可用 (together with available local/cached/prior evidence)
and SHALL NOT ship negative world claims (未找到该机构 / 无相关信息 family)
as if they were retrieval facts.

#### Scenario: fault-injected web outage over a web-only subject

- **WHEN** both web providers fail (invalid keys) and the subject is
  web-only
- **THEN** the answer carries 网络检索暂不可用, retains any cached/prior
  session evidence, and contains no "未找到…" world-negative claim
- **AND** the turn trace records degradation web-lane-unavailable

## MODIFIED Requirements

### Requirement: Synthesis Prompt Contract

The prose synthesis prompt SHALL include the wording contract: end answers
with confirmed content rather than refusal forms; never recommend external
databases as a substitute for the answer; when told the web lane is
unavailable, state 网络检索暂不可用 instead of claiming the information does
not exist. (Deterministic guards remain the backstop.)
