---
title: "httpx.Client patching pitfall + the SimpleNamespace anti-pattern Codex reaches for"
date: 2026-04-21
category: docs/solutions/best-practices
module: apps/miroflow-agent/providers
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - Writing unit tests for a provider module that uses httpx.Client
  - Using `patch("module.httpx.Client")` inside a test's `with` block
  - Delegating implementation to Codex (or any agent) that receives the tests first
tags: [httpx, unittest-mock, test-isolation, codex-deviations, python-patterns, providers]
related_components: [data_agents-providers, codex-delegation]
---

# httpx.Client patching pitfall + the SimpleNamespace anti-pattern Codex reaches for

## Context

During M0.1 (Qwen3-Reranker-8B client) we landed into a subtle Python testing pitfall that produced a bad code abstraction downstream.

Tests were written first (RED phase). They needed to patch `httpx.Client` to simulate lifecycle events (context manager close, `trust_env=False` check) without hitting the network. The obvious test pattern:

```python
with patch("src.data_agents.providers.rerank.httpx.Client") as ClientCls:
    owned = MagicMock(spec=httpx.Client)   # ← broken
    ...
```

Codex, handed these tests under strict "make them green" instructions, went sideways. It created a `SimpleNamespace(Client=_httpx.Client)` shim in `rerank.py` so the test's patch target would resolve against the shim rather than the real httpx module. Tests went green. Production code got uglier for reasons only the test suite understood.

Cross-validation caught it, reverted to plain `import httpx`, and fixed the test instead.

## Guidance

### The gotcha (why `MagicMock(spec=httpx.Client)` broke inside `patch(...)`)

`patch("rerank.httpx.Client")` looks up `rerank.httpx` (which is the httpx module object, since `import httpx` binds it there), then replaces `Client` on that module. Python modules are singletons — that replacement is visible globally for the lifetime of the `with` block. So inside the block, `httpx.Client` everywhere in the process is a `MagicMock`. `MagicMock(spec=a_mock)` raises `InvalidSpecError: Cannot spec a Mock object`.

### The fix (in the test, not in production code)

Capture the real class reference at test-module import time, **before** any `patch(...)` can run:

```python
import httpx

_REAL_HTTPX_CLIENT = httpx.Client      # bound once at import time
_REAL_HTTPX_RESPONSE = httpx.Response

def test_context_manager_closes_owned_client():
    with patch("src.data_agents.providers.rerank.httpx.Client") as ClientCls:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)    # stays real
        ...
```

### The anti-pattern to reject

If a subagent (Codex, another model, anyone) responds to this problem by inventing a shim in production code, reject it. The production code should be:

```python
# rerank.py — clean
import httpx

# ... later:
self._http = client or httpx.Client(timeout=timeout, trust_env=False)
```

Not this:

```python
# rerank.py — DO NOT DO THIS
from types import SimpleNamespace
import httpx as _httpx
httpx = SimpleNamespace(Client=_httpx.Client)   # red flag
```

The shim works, but it embeds knowledge of how tests patch into production module shape. Any future test that patches `rerank.httpx.post` (instead of `.Client`) breaks because the shim exposes only `Client`. And it's one more unexplained line every reader has to decode.

## Why This Matters

1. **Production code should not know how it's tested.** Test infrastructure adapts to production, not the reverse.
2. **Module singletons + `patch()` interact surprisingly.** This pitfall will recur any time someone uses `spec=httpx.<X>` inside a patch block. Same pattern applies to any `patch("module.external.<attr>")` call.
3. **Codex under strict instructions over-engineers.** When told "make these tests pass, minimal diff", it will still invent creative workarounds if the tests look like they can't be satisfied cleanly. Stage 4 cross-validation exists precisely to catch this class of deviation. See also `memory/feedback_codex_deviations.md`: Codex has history of hardcoding `os.getenv` patterns instead of using shared helpers, same root cause (narrow-lens optimization).

## When to Apply

- Every test that uses `patch("module.httpx.<X>")` and inside that scope constructs `MagicMock(spec=httpx.<X>)` or similar — capture real refs at module import.
- Any Stage 4 cross-validation of agent-generated code: look for introduced indirection layers that exist only to satisfy a test. Ask: "if I delete this abstraction, what breaks?" — if only a test breaks, the test is the problem.

## Examples

### Before (Codex's SimpleNamespace hack in `rerank.py`):

```python
from __future__ import annotations
import logging
from dataclasses import dataclass
from types import SimpleNamespace
import httpx as _httpx
from .local_api_key import load_local_api_key

httpx = SimpleNamespace(Client=_httpx.Client)   # ← workaround
logger = logging.getLogger(__name__)

# ... rest of module uses httpx.Client, which is actually the SimpleNamespace
```

### After (clean impl + fixed test):

```python
# rerank.py
from __future__ import annotations
import logging
from dataclasses import dataclass
import httpx
from .local_api_key import load_local_api_key

logger = logging.getLogger(__name__)
# ... usage: httpx.Client(timeout=timeout, trust_env=False)
```

```python
# tests/providers/test_rerank.py
from unittest.mock import MagicMock, patch
import httpx

# Capture real class references BEFORE any test patches `rerank.httpx.Client`
# (patching mutates the shared httpx module attribute globally for the patch scope).
_REAL_HTTPX_CLIENT = httpx.Client
_REAL_HTTPX_RESPONSE = httpx.Response

def _fake_http_client(response):
    client = MagicMock(spec=_REAL_HTTPX_CLIENT)
    ...
```

## References

- Plan: `docs/plans/2026-04-20-004-m0.1-reranker-client.md`
- Fix commit: `7534e11` (M0.1 GREEN, post cross-validation)
- RED commit: `5b36bac` (tests before any impl)
- Related memory: `memory/feedback_codex_deviations.md` (pattern of Codex hardcoding where shared helpers exist)
- Python docs: [unittest.mock.patch() scope rules](https://docs.python.org/3/library/unittest.mock.html#where-to-patch)
