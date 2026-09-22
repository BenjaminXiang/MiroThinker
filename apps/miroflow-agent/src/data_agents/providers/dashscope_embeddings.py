# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""DashScope-native text-embedding client (Alibaba's own shape, not OpenAI's).

DashScope's native embeddings route is not the OpenAI one: the request carries
``input: {texts: [...]}`` and the answer arrives under
``output.embeddings[].{text_index, embedding}``. The v2 candidate serving model
(``qwen3.7-text-embedding-flash`` on the MaaS gateway) is addressed only through
this shape, so the build/serving embedding authority needs a second HTTP client
beside the OpenAI-compatible one.

Transport failures are normalized here exactly as
``company.vectorizer.EmbeddingClient`` does for the OpenAI shape — a provider
that is *unreachable* becomes ``TimeoutError``/``ConnectionError``, the builtins
the lane-level fail-open hook understands. An *answer we cannot use* (a wrong
``text_index`` set, an empty vector) stays a validation failure and fails
closed.

One non-2xx answer is not a transport failure and must not be reported as one:
HTTP 429 means *the endpoint answered* and asked us to come back later, so it is
raised as :class:`EmbeddingEndpointRateLimitedError` with the status and the
provider's own ``Retry-After``. It subclasses the builtin ``ConnectionError``,
which keeps every existing consumer's semantics identical (the serving lane still
degrades fail-open) while letting the rebuild's batch fan-out recognize the rate
signal and wait behind a cooldown instead of losing four hours of work. Every
other status names itself in its message ("refused the request (HTTP 400)",
"answered a transient server error (HTTP 503)") rather than claiming the endpoint
was unreachable.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

#: Appended to the bundle's ``base_url``. The bundle records the versioned
#: prefix (``https://maas.qianwenaiapi.com/api/v1``), the way the OpenAI bundle
#: records ``.../v1`` and the client appends ``/embeddings``.
_TEXT_EMBEDDINGS_PATH = "/services/embeddings/text-embedding/text-embedding"


class EmbeddingEndpointRateLimitedError(ConnectionError):
    """The endpoint answered HTTP 429: this call was refused *for now*.

    A subclass of the builtin ``ConnectionError`` on purpose, because both
    consumers have to keep working unchanged:

    * the serving lane's fail-open hook (``knowledge_read._invoke_lane``
      captures the builtin) still degrades the lane instead of failing the turn,
      and the embedding breaker still counts the refused call as a transport
      failure;
    * a caller that *can* wait — the rebuild's per-batch fan-out — recognizes
      the provider's rate signal and retries behind a cooldown rather than
      abandoning a four-hour pass.

    ``status_code`` carries the provider's answer (429). ``retry_after`` is its
    own ``Retry-After`` in seconds when it sent a usable one, else ``None``: the
    caller then falls back to its own back-off instead of guessing.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _retry_after_seconds(value: str | None) -> float | None:
    """The provider's ``Retry-After`` as a delay, or ``None`` when unusable.

    Only the delay-seconds form is read (RFC 9110 also allows an HTTP date): a
    date would have to be turned into a delay against a clock this client does
    not trust, and reporting "no hint" is more honest than guessing one.
    """

    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _status_failure(
    error: httpx.HTTPStatusError,
    *,
    base_url: str,
) -> ConnectionError:
    """Classify one non-2xx answer into the failure it actually is.

    The distinction the previous single message erased: "unreachable" is for a
    provider that did not answer, while a status answer must name the status.
    Only the rate status is a type of its own, because only the rate status is
    waited out (see the module docstring); a server fault stays a plain
    ``ConnectionError`` — honest about being transient, but failing the pass the
    way it always did.
    """

    status = error.response.status_code
    if status == 429:
        retry_after = _retry_after_seconds(error.response.headers.get("Retry-After"))
        message = f"embedding endpoint {base_url} rate limited the batch (HTTP {status}"
        if retry_after is not None:
            message += f", Retry-After={retry_after:g}s"
        return EmbeddingEndpointRateLimitedError(
            message + ")",
            status_code=status,
            retry_after=retry_after,
        )
    if 500 <= status < 600:
        return ConnectionError(
            f"embedding endpoint {base_url} answered a transient server error "
            f"(HTTP {status})"
        )
    return ConnectionError(
        f"embedding endpoint {base_url} refused the request (HTTP {status})"
    )


class DashScopeTextEmbeddingClient:
    """One DashScope-native ``text-embedding`` call per ``embed_batch``.

    ``text_type``/``instruct`` are the route's query-side knobs and are absent by
    default: an absent ``text_type`` is the route's ``document`` role, which is
    what a rebuild must use. Only a caller holding a *query* role passes them
    (the serving lane), and it passes the values the frozen bundle records.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
        text_type: str | None = None,
        instruct: str | None = None,
    ) -> None:
        if instruct is not None and text_type is None:
            raise ValueError("instruct needs the text_type it qualifies")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.text_type = text_type
        self.instruct = instruct

    def embed_batch(
        self,
        texts: list[str],
        *,
        model: str,
    ) -> list[list[float]]:
        """Embed ``texts`` in one call, returning vectors in input order.

        ``dimension`` is deliberately not sent: the candidate model answers 1024
        dimensions by default and rejects an unsupported ``dimension`` with HTTP
        400 (measured 2026-09-21), so the declared dimension is enforced on the
        response instead — a silent dimension change then fails closed rather
        than mixing vector spaces.
        """

        if not texts:
            return []
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {"model": model, "input": {"texts": texts}}
        if self.text_type is not None:
            payload["text_type"] = self.text_type
        if self.instruct is not None:
            payload["instruct"] = self.instruct
        try:
            with httpx.Client(trust_env=False, timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}{_TEXT_EMBEDDINGS_PATH}",
                    json=payload,
                    headers=headers,
                )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            # The endpoint answered; the answer is the failure. Caught before the
            # generic HTTPError clause so a status is never reported as "the
            # endpoint did not answer".
            raise _status_failure(exc, base_url=self.base_url) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"embedding endpoint {self.base_url} did not answer in time"
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise ConnectionError(
                f"embedding endpoint {self.base_url} is unreachable"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConnectionError(
                f"embedding endpoint {self.base_url} answered with a non-JSON body"
            ) from exc
        return _ordered_embeddings(data, expected=len(texts))


#: Where a row states its input position. DashScope's documentation names it
#: ``text_index``; the MaaS gateway's native route answers ``index`` (measured
#: live 2026-09-21: rows carry ``['embedding', 'index', 'type']``). Both are
#: accepted, and the row is placed by whichever one it carries.
_ROW_INDEX_KEYS = ("text_index", "index")


def _ordered_embeddings(document: Any, *, expected: int) -> list[list[float]]:
    """Read ``output.embeddings`` and restore input order through the row index.

    Neither DashScope nor the gateway promises the answer order, so every row is
    placed back at the index it names; a set that is not exactly ``0..n-1`` is a
    validation failure, never a silent misalignment of text and vector.
    """

    output = document.get("output") if isinstance(document, dict) else None
    rows = output.get("embeddings") if isinstance(output, dict) else None
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError("embedding provider returned a different row count")
    ordered: dict[int, list[float]] = {}
    for row in rows:
        text_index = None
        if isinstance(row, dict):
            for key in _ROW_INDEX_KEYS:
                value = row.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    text_index = value
                    break
        if text_index is None:
            raise ValueError("embedding provider returned a malformed embedding row")
        if text_index in ordered or not 0 <= text_index < expected:
            raise ValueError(
                "embedding provider returned a non-permutation text_index set"
            )
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("embedding provider returned an empty embedding")
        ordered[text_index] = embedding
    return [ordered[index] for index in range(expected)]


__all__ = ["DashScopeTextEmbeddingClient", "EmbeddingEndpointRateLimitedError"]
