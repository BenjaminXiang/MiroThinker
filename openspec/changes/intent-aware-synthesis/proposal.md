# Proposal: intent-aware-synthesis

> Behavior-affecting. Extends `agentic-rag-retrieval` (in-flight via fix-chat-retrieval-recall-gaps
> + add-synthesis-timeout). Contract-consistent GENERALIZATION of the existing Type-E knowledge-QA
> regime (PRD §1.3/§2.1 authorizes "Web Search + LLM 知识生成...明确标注'综合自网络搜索和 AI 分析'";
> `_KNOWLEDGE_QA_SYSTEM` at chat.py:1102-1108 already implements it with the guard
> "不要编造具体人名/机构/数字"). This change makes synthesis intent-aware across ALL query types.

## Why

The full-testset eval shows 42% recall / 14.6% coverage. The dominant cap: the default synthesis
prompt (`_CHAT_SYNTHESIS_SYSTEM_PROMPT`, chat.py:73-80) rule "evidence-only, refuse if insufficient"
makes 6 knowledge/conceptual cases (qid18–23) REFUSE → ~0. The PRD already authorizes LLM-knowledge
for Type E, but (a) qid18–23 don't route to E (they hit B/unknown), and (b) the synthesis prompt is
uniform (not intent-aware). So the system refuses questions it could answer.

## What Changes

1. **ADD** `_detect_answer_intent(query, query_type, structured_payload) -> "profile"|"list"|"qa"`
   in chat.py, called in `_build_chat_response` before `_build_evidence_blocks`. Derives from
   `query_type` prefixes (A_→profile, B_/C_/D_→list, E_→qa) + knowledge keywords
   (几种/路线/方式/方法/原理/分类/趋势/什么是) that force `qa` even when query_type isn't E.
2. **ADD** 3 system-prompt constants: `_CHAT_SYNTHESIS_SYSTEM_PROMPT_PROFILE` (deep multi-field
   prose, extends current), `_LIST` (bullet-list of objects), `_QA` (REUSES `_KNOWLEDGE_QA_SYSTEM` —
   the existing knowledge-augmented prompt with the entity-no-fabrication guard + the label).
3. **MODIFY** `_call_gemma_synthesis` to accept a `system_prompt` param (default = current prompt);
   select by intent at the `_build_chat_response` call site. Thread through
   `_synthesize_web_search_answer` (stays on _QA for the E-route).
4. **Invariant preserved**: entity claims stay evidence-grounded + `[N]`-cited; LLM-knowledge content
   labeled `（综合自 AI 推理…）`; never invents specific entities; A–G routing + `_VALID_DOMAINS` +
   evidence shape unchanged.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agentic-rag-retrieval`: synthesis SHALL be intent-aware (profile/list/qa modes); the qa mode SHALL
  allow LLM knowledge for conceptual content (reusing the existing _KNOWLEDGE_QA_SYSTEM guard) with
  entity claims staying grounded + labeled. (In-flight capability; baseline = Agentic-RAG-PRD.md.)

## Impact

- Code: `chat.py` (`_detect_answer_intent` new, 3 prompts, `_call_gemma_synthesis` system_prompt
  param, `_build_chat_response` intent selection). No schema/migration/provider change.
- Recall: qid18–23 (6 cases) answer instead of refuse → coverage/recall up from ~0.
- Risk: LLM-knowledge hallucination — mitigated by the existing entity-grounding guard + the label
  + the forbidden-entities eval gate.
