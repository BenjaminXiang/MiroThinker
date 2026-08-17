"""Focused owner for the explicit Canonical V2 black-box smoke caller."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest


def test_smoke_requires_explicit_release_and_reuses_one_cookie_session() -> None:
    from scripts.smoke_canonical_v2_candidate import SmokeContractError, run_smoke

    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
            assert self.path == "/api/chat"
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append({"body": body, "cookie": self.headers.get("cookie")})
            if body["query"] == "redirect":
                self.send_response(302)
                self.send_header("location", "/elsewhere")
                self.end_headers()
                return
            if body["query"] == "non-json":
                encoded = b"not-json"
                self.send_response(200)
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            payload = {
                "query": body["query"],
                "query_type": "canonical_v2:A",
                "evidence": [{"evidence_id": "evidence:smoke"}],
                "structured_payload": {
                    "canonical_v2": {
                        "release_id": "release:smoke",
                        "plan_id": "plan:smoke",
                        "plan_version": "v1",
                        "lanes": ["exact"],
                        "retrieval_traces": [{"lane": "exact"}],
                        "evidence_ids": ["evidence:smoke"],
                        "claims": [
                            {
                                "claim_id": "claim:smoke",
                                "evidence_ids": ["evidence:smoke"],
                            }
                        ],
                        "claim_evidence_mappings": [
                            {
                                "claim_id": "claim:smoke",
                                "evidence_ids": ["evidence:smoke"],
                            }
                        ],
                    }
                },
            }
            if body["query"] == "wrong-release":
                payload["structured_payload"]["canonical_v2"]["release_id"] = (
                    "release:wrong"
                )
            elif body["query"] == "stale-query":
                payload["query"] = "different query"
            elif body["query"] == "empty-trace":
                payload["structured_payload"]["canonical_v2"]["lanes"] = []
            elif body["query"] == "orphan-claim":
                payload["structured_payload"]["canonical_v2"][
                    "claim_evidence_mappings"
                ][0]["evidence_ids"] = ["evidence:orphan"]
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            if len(requests) == 1:
                self.send_header(
                    "set-cookie", "miroflow_chat_session=session-smoke; Path=/"
                )
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = run_smoke(
            base_url=f"http://127.0.0.1:{server.server_port}",
            expected_release_id="release:smoke",
            queries=("first query", "second query"),
        )
        for invalid_query in (
            "redirect",
            "non-json",
            "wrong-release",
            "stale-query",
            "empty-trace",
            "orphan-claim",
        ):
            with pytest.raises(SmokeContractError):
                run_smoke(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    expected_release_id="release:smoke",
                    queries=(invalid_query,),
                )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert [item["release_id"] for item in result] == [
        "release:smoke",
        "release:smoke",
    ]
    assert requests[0]["cookie"] is None
    assert requests[1]["cookie"] == "miroflow_chat_session=session-smoke"

    with pytest.raises(SmokeContractError):
        run_smoke(
            base_url="http://127.0.0.1:1",
            expected_release_id="",
            queries=("query",),
        )
    with pytest.raises(SmokeContractError):
        run_smoke(
            base_url="http://127.0.0.1:1",
            expected_release_id="release:smoke",
            queries=(),
        )
    for invalid_queries in (("",), ("x" * 501,), tuple("q" for _ in range(11))):
        with pytest.raises(SmokeContractError):
            run_smoke(
                base_url="http://127.0.0.1:1",
                expected_release_id="release:smoke",
                queries=invalid_queries,
            )
