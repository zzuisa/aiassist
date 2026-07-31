"""Bounded, authenticated HTTP client for Radio's existing task APIs.

The client never logs credentials, cookies, response bodies or source media.
Transport failures are reduced to stable diagnostics suitable for structured
logs, while callers receive a safe Chinese user message.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings

RADIO_UNAVAILABLE = "RADIO_SERVICE_UNAVAILABLE"
RADIO_UNAVAILABLE_MESSAGE = "B站音视频处理服务当前不可用，请稍后重试。"


class RadioServiceError(Exception):
    def __init__(
        self,
        code: str,
        public_message: str,
        *,
        diagnostic: str,
        retryable: bool = True,
    ) -> None:
        self.code = code
        self.public_message = public_message
        self.diagnostic = diagnostic
        self.retryable = retryable
        super().__init__(public_message)


@dataclass(frozen=True)
class RadioTask:
    id: str
    status: str
    progress: int
    message: str | None
    result: dict[str, Any] | None
    error: str | None


@dataclass(frozen=True)
class RadioTranscriptPage:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None


class RadioClient:
    def __init__(
        self,
        *,
        base_url: str,
        password: str | None,
        connect_timeout: float,
        read_timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._password = password
        self._authenticated = False
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=connect_timeout,
                pool=connect_timeout,
            ),
            transport=transport,
        )

    def _unavailable(self, diagnostic: str) -> RadioServiceError:
        return RadioServiceError(
            RADIO_UNAVAILABLE,
            RADIO_UNAVAILABLE_MESSAGE,
            diagnostic=diagnostic,
        )

    def _raw_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.ConnectTimeout as exc:
            raise self._unavailable("connect_timeout") from exc
        except httpx.ReadTimeout as exc:
            raise self._unavailable("read_timeout") from exc
        except httpx.ConnectError as exc:
            raise self._unavailable("connect_error") from exc
        except httpx.NetworkError as exc:
            raise self._unavailable("network_error") from exc
        except httpx.HTTPError as exc:
            raise self._unavailable("http_client_error") from exc

    def _authenticate(self) -> None:
        if not self._password:
            raise self._unavailable("credentials_unconfigured")
        response = self._raw_request("POST", "/api/auth/verify", json={"password": self._password})
        if response.status_code >= 500:
            raise self._unavailable(f"auth_http_{response.status_code}")
        if response.status_code != 200:
            raise self._unavailable("auth_rejected")
        self._authenticated = True

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._authenticated:
            self._authenticate()
        response = self._raw_request(method, path, **kwargs)
        if response.status_code == 401:
            # Radio keeps auth sessions in memory; transparently re-authenticate
            # once after a Radio restart.
            self._authenticated = False
            self._authenticate()
            response = self._raw_request(method, path, **kwargs)
        if response.status_code >= 500:
            raise self._unavailable(f"http_{response.status_code}")
        return response

    def _json_object(self, response: httpx.Response, *, operation: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise self._unavailable(f"{operation}_invalid_json") from exc
        if not isinstance(data, dict):
            raise self._unavailable(f"{operation}_invalid_shape")
        return data

    def submit_bilibili_transcription(self, url: str) -> str:
        response = self._request(
            "POST", "/api/tasks/speech2text/bilibili", json={"url": url}
        )
        if response.status_code in {400, 404, 422}:
            raise RadioServiceError(
                "BILIBILI_LINK_UNAVAILABLE",
                "无法解析该 B 站链接，视频可能已失效、需要登录或存在访问限制。",
                diagnostic=f"submit_http_{response.status_code}",
                retryable=False,
            )
        if response.status_code != 200:
            raise self._unavailable(f"submit_http_{response.status_code}")
        data = self._json_object(response, operation="submit")
        task_id = data.get("task_id")
        if data.get("ok") is not True or not isinstance(task_id, str) or not task_id.strip():
            raise self._unavailable("submit_invalid_response")
        return task_id.strip()

    def get_task(self, task_id: str) -> RadioTask:
        response = self._request("GET", f"/api/tasks/{task_id}")
        if response.status_code == 404:
            raise RadioServiceError(
                "RADIO_TASK_NOT_FOUND",
                "B站音视频处理任务已失效，请重新导入。",
                diagnostic="task_not_found",
                retryable=True,
            )
        if response.status_code != 200:
            raise self._unavailable(f"task_http_{response.status_code}")
        data = self._json_object(response, operation="task")
        task = data.get("task")
        if data.get("ok") is not True or not isinstance(task, dict):
            raise self._unavailable("task_invalid_response")
        status = task.get("status")
        task_id_value = task.get("id")
        if not isinstance(status, str) or not isinstance(task_id_value, str):
            raise self._unavailable("task_missing_fields")
        result = task.get("result")
        if result is not None and not isinstance(result, dict):
            raise self._unavailable("task_invalid_result")
        return RadioTask(
            id=task_id_value,
            status=status,
            progress=max(0, min(100, int(task.get("progress") or 0))),
            message=task.get("message") if isinstance(task.get("message"), str) else None,
            result=result,
            error=task.get("error") if isinstance(task.get("error"), str) else None,
        )

    def optimize_text(self, text: str, *, instruction: str | None = None) -> str:
        response = self._request(
            "POST",
            "/api/text/optimize",
            json={"text": text, "instruction": instruction},
        )
        if response.status_code in {400, 413, 422}:
            raise RadioServiceError(
                "RADIO_OPTIMIZATION_INVALID",
                "当前文章无法使用 Radio 优化，请检查正文内容。",
                diagnostic=f"optimize_http_{response.status_code}",
                retryable=False,
            )
        if response.status_code != 200:
            raise self._unavailable(f"optimize_http_{response.status_code}")
        data = self._json_object(response, operation="optimize")
        optimized = data.get("optimized_text")
        if data.get("ok") is not True or not isinstance(optimized, str) or not optimized.strip():
            raise self._unavailable("optimize_invalid_response")
        return optimized.strip()

    def list_transcripts(self, *, limit: int, offset: int) -> RadioTranscriptPage:
        response = self._request(
            "GET",
            "/api/speech2text/records",
            params={"limit": limit, "offset": offset},
        )
        if response.status_code != 200:
            raise self._unavailable(f"records_http_{response.status_code}")
        data = self._json_object(response, operation="records")
        items = data.get("items")
        required = ("total", "limit", "offset", "has_more", "next_offset")
        if (
            data.get("ok") is not True
            or not isinstance(items, list)
            or any(key not in data for key in required)
        ):
            raise self._unavailable("records_pagination_unsupported")
        if any(not isinstance(item, dict) for item in items):
            raise self._unavailable("records_invalid_items")
        try:
            return RadioTranscriptPage(
                items=items,
                total=int(data["total"]),
                limit=int(data["limit"]),
                offset=int(data["offset"]),
                has_more=bool(data["has_more"]),
                next_offset=int(data["next_offset"])
                if data["next_offset"] is not None
                else None,
            )
        except (TypeError, ValueError) as exc:
            raise self._unavailable("records_invalid_pagination") from exc


@lru_cache
def get_radio_client() -> RadioClient:
    settings = get_settings()
    if not settings.radio_service_base_url:
        raise RadioServiceError(
            RADIO_UNAVAILABLE,
            RADIO_UNAVAILABLE_MESSAGE,
            diagnostic="base_url_unconfigured",
        )
    return RadioClient(
        base_url=settings.radio_service_base_url,
        password=settings.resolved_radio_service_password,
        connect_timeout=settings.radio_service_connect_timeout_seconds,
        read_timeout=settings.radio_service_read_timeout_seconds,
    )
