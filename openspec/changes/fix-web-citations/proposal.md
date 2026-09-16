# Proposal: fix-web-citations (P2-B)

> User product rule "尽量能指出处": enumeration/concept answers lean entirely
> on web evidence yet ship ZERO citations — the citation chain requires an
> entity HANDLE binding (`_public_citations` drops handle-less evidence),
> and non-"official" web evidence never yields a URL. Single-entity turns
> sometimes carry 1 official citation; list/concept turns carry none.

## What Changes

1. `chat_contracts.py`: ChatCitation.type gains "web".
2. `canonical_v2_chat._public_citations`: second pass — handle-unbound
   citations over `current_web` evidence with a public locator become web
   cards (label = page title head from the evidence snippet, url =
   source_locator), URL-deduped, capped at 6, appended after official cards.
3. `chat.html`: citationTypeLabels.web = "网络".

## Impact

- Enumeration/concept answers become 可核查 (source links listed).
- Local evidence without handles still produces no card (no public URL).
- Non-goal: inline numbered citations in the answer body.
