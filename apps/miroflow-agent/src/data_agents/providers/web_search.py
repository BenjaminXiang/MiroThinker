from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Callable

import requests


class WebSearchProvider:
    def __init__(
        self,
        *,
        endpoint: str = "https://google.serper.dev/search",
        api_key: str | None = None,
        gl: str = "cn",
        hl: str = "zh-cn",
        timeout: float = 30.0,
        session: requests.Session | Any | None = None,
        curl_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "").strip()
        self.gl = gl
        self.hl = hl
        self.timeout = timeout
        self.session = session or requests.Session()
        self.curl_runner = curl_runner or subprocess.run
        self._disabled_reason: str | None = None
        if hasattr(self.session, "trust_env"):
            self.session.trust_env = False

    def build_payload(
        self,
        query: str,
        *,
        gl: str | None = None,
        hl: str | None = None,
    ) -> dict[str, str]:
        return {
            "q": query,
            "gl": gl or self.gl,
            "hl": hl or self.hl,
        }

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
        }

    def search(self, query: str, *, gl: str | None = None, hl: str | None = None) -> dict[str, Any]:
        if self._disabled_reason:
            raise RuntimeError(self._disabled_reason)

        payload = self.build_payload(query, gl=gl, hl=hl)
        try:
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=self.build_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self._normalize_response_payload(response.json())
        except requests.exceptions.HTTPError as exc:
            raise self._build_api_error(exc.response, default_message=str(exc)) from exc
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ProxyError,
        ):
            return self._search_via_curl(payload)

    def _normalize_response_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        status_code = payload.get("statusCode")
        message = str(payload.get("message") or "").strip()
        if isinstance(status_code, int) and status_code >= 400:
            raise self._build_api_error(None, payload=payload)
        if message and not payload.get("organic") and not payload.get("knowledgeGraph"):
            raise self._build_api_error(None, payload=payload)
        return payload

    def _build_api_error(
        self,
        response: Any | None,
        *,
        payload: dict[str, Any] | None = None,
        default_message: str = "Serper API request failed",
    ) -> RuntimeError:
        error_payload = payload or self._extract_error_payload(response)
        message = str((error_payload or {}).get("message") or "").strip()
        status_code = (error_payload or {}).get("statusCode")
        if message:
            if status_code:
                detail = f"Serper API error ({status_code}): {message}"
            else:
                detail = f"Serper API error: {message}"
        else:
            detail = default_message

        if "not enough credits" in message.casefold():
            self._disabled_reason = detail
        return RuntimeError(detail)

    def _extract_error_payload(self, response: Any | None) -> dict[str, Any]:
        if response is None:
            return {}
        if hasattr(response, "json"):
            try:
                data = response.json()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        text = getattr(response, "text", "") or ""
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _search_via_curl(self, payload: dict[str, str]) -> dict[str, Any]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {
                "all_proxy",
                "ALL_PROXY",
                "http_proxy",
                "HTTP_PROXY",
                "https_proxy",
                "HTTPS_PROXY",
            }
        }
        header_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        header_path = header_file.name
        try:
            header_file.write(f"X-API-KEY: {self.api_key}\n")
            header_file.write("Content-Type: application/json\n")
            header_file.close()

            command = [
                "curl",
                "-sS",
                "--http1.1",
                "-X",
                "POST",
                self.endpoint,
                "-H",
                f"@{header_path}",
                "--data",
                json.dumps(payload, ensure_ascii=False),
            ]
            completed = self.curl_runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=env,
            )
        finally:
            try:
                os.unlink(header_path)
            except FileNotFoundError:
                pass
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "curl search failed").strip())
        return self._normalize_response_payload(json.loads(completed.stdout))
