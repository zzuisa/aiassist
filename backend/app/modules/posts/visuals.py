"""Execution and normalization for blog visual enhancements.

Mermaid and ECharts are local, deterministic capabilities: the model proposes
the source/data and this module validates it before it reaches a candidate.
Image capabilities are deliberately adapter-based and disabled until an
operator registers an allow-listed HTTP endpoint in BLOG_CAPABILITIES_JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

_MAX_MERMAID = 20_000
_MAX_CHART_POINTS = 100
_MAX_IMAGE_RESPONSE = 64 * 1024
_DANGEROUS_MERMAID = re.compile(r"<\s*script|javascript:|data:text/html|on\w+\s*=", re.I)


def _configured_capability(name: str) -> dict[str, Any] | None:
    raw = get_settings().blog_capabilities_json.strip()
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _safe_image_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return value


def _as_mermaid(content: dict[str, Any]) -> str | None:
    source = content.get("mermaid") or content.get("code") or content.get("source")
    if not isinstance(source, str):
        return None
    source = source.strip()
    if not source or len(source) > _MAX_MERMAID or _DANGEROUS_MERMAID.search(source):
        return None
    diagram_start = (
        r"^(?:flowchart|graph|mindmap|sequenceDiagram|stateDiagram|timeline|classDiagram)\b"
    )
    if not re.match(diagram_start, source):
        return None
    return source


def _as_chart(content: dict[str, Any]) -> dict[str, Any] | None:
    chart_type = content.get("chart_type") or content.get("type")
    if chart_type not in {"bar", "line", "pie", "scatter", "table"}:
        return None
    data = content.get("data")
    if not isinstance(data, list) or not (2 <= len(data) <= _MAX_CHART_POINTS):
        return None
    normalized: list[dict[str, Any]] = []
    for point in data:
        if not isinstance(point, dict) or not isinstance(point.get("label"), str):
            return None
        value = point.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        normalized.append({"label": point["label"][:120], "value": value})
    return {
        "chart_type": chart_type,
        "data": normalized,
        "unit": str(content.get("unit", ""))[:40],
        "source": [str(item)[:500] for item in content.get("source", [])[:10]]
        if isinstance(content.get("source"), list)
        else [],
    }


def _image_request(name: str, enhancement: Any) -> dict[str, Any]:
    content = enhancement.content if isinstance(enhancement.content, dict) else {}
    return {
        "request_type": "image_generation" if name == "imagegen" else "image_search",
        "model": str(content.get("model", ""))[:160],
        "prompt": str(content.get("prompt", ""))[:4000],
        "query": str(content.get("query", ""))[:500],
        "purpose": enhancement.reason[:500],
        "alt_text": enhancement.alt_text[:500],
    }


def _call_image_capability(name: str, enhancement: Any) -> tuple[str | None, dict[str, Any]]:
    capability = _configured_capability(name)
    if not capability or not capability.get("enabled") or capability.get("type") != "http-api":
        return None, {"code": "CAPABILITY_UNAVAILABLE", "message": f"{name} 未配置 http-api"}
    endpoint = capability.get("endpoint")
    parsed = urlparse(endpoint if isinstance(endpoint, str) else "")
    if parsed.scheme != "https" or not parsed.netloc:
        return None, {"code": "INVALID_ENDPOINT", "message": f"{name} endpoint 无效"}

    headers = {"Accept": "application/json"}
    token_file = capability.get("token_file")
    if isinstance(token_file, str) and token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if token:
            headers[str(capability.get("auth_header", "Authorization"))] = (
                f"Bearer {token}" if capability.get("auth_scheme", "Bearer") == "Bearer" else token
            )
    try:
        response = httpx.post(
            endpoint,
            json={
                **_image_request(name, enhancement),
                **({"model": str(capability["model"])[:160]} if capability.get("model") else {}),
            },
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        if len(response.content) > _MAX_IMAGE_RESPONSE:
            return None, {"code": "RESPONSE_TOO_LARGE", "message": "图片能力响应过大"}
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return None, {
            "code": "CAPABILITY_FAILED",
            "message": f"{name} 调用失败: {type(exc).__name__}",
        }

    candidates: list[Any] = [payload.get("url")] if isinstance(payload, dict) else []
    if isinstance(payload, dict):
        for key in ("data", "images", "results"):
            values = payload.get(key)
            if isinstance(values, list):
                candidates.extend(
                    item.get("url") for item in values if isinstance(item, dict)
                )
    for value in candidates:
        url = _safe_image_url(value)
        if url:
            return url, {"provider": name}
    # A data URI is intentionally not embedded in Markdown. It can be enormous,
    # bypass the normal media policy, and is not a stable review asset.
    if isinstance(payload, dict) and any(
        isinstance(item, dict) and item.get("b64_json") for item in payload.get("data", [])
    ):
        return None, {
            "code": "BASE64_IMAGE_UNSUPPORTED",
            "message": "图片服务仅返回 base64，未写入候选",
        }
    return None, {"code": "INVALID_RESPONSE", "message": f"{name} 未返回安全图片 URL"}


def execute_enhancements(result: Any, *, max_visual_items: int = 2) -> list[dict[str, Any]]:
    """Validate local visuals and execute configured image adapters in place."""
    executed: list[dict[str, Any]] = []
    for enhancement in result.enhancements:
        if enhancement.status != "executed":
            continue
        if len(executed) >= max(1, min(10, max_visual_items)):
            enhancement.status = "skipped"
            enhancement.reason = "超过本次视觉内容数量上限"
            continue
        content = enhancement.content if isinstance(enhancement.content, dict) else {}
        if enhancement.capability == "visualize":
            source = _as_mermaid(content)
            if source is None:
                enhancement.status = "failed"
                enhancement.reason = "Mermaid 内容未通过安全或语法门控"
                continue
            enhancement.content = {"format": "mermaid", "mermaid": source}
        elif enhancement.capability == "answers-charts":
            chart = _as_chart(content)
            if chart is None:
                enhancement.status = "failed"
                enhancement.reason = "图表数据缺少统一标签/数值，或未达到最小比较点数"
                continue
            enhancement.content = chart
        elif enhancement.capability in {"imagegen", "answers-images"}:
            url, metadata = _call_image_capability(enhancement.capability, enhancement)
            if url is None:
                enhancement.status = (
                    "unavailable"
                    if metadata.get("code") == "CAPABILITY_UNAVAILABLE"
                    else "failed"
                )
                enhancement.reason = str(metadata.get("message", "图片能力不可用"))
                continue
            enhancement.content = {"format": "image", "image_url": url, **metadata}
        else:
            enhancement.status = "unavailable"
            enhancement.reason = f"未注册的视觉能力：{enhancement.capability}"
            continue
        executed.append(enhancement.model_dump(mode="json"))
    return executed


def enhancements_markdown(enhancements: list[dict[str, Any]]) -> str:
    """Turn validated enhancements into reviewable Markdown blocks."""
    parts: list[str] = []
    for item in enhancements:
        content = item.get("content") or {}
        caption = str(item.get("caption") or "可视化增强")[:500]
        alt_text = str(item.get("alt_text") or caption)[:500]
        if item.get("capability") == "visualize" and content.get("mermaid"):
            parts.append(f"\n\n> {caption}\n\n```mermaid\n{content['mermaid']}\n```")
        elif item.get("capability") == "answers-charts" and content.get("data"):
            chart_payload = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"\n\n> {caption}\n\n```echarts\n{chart_payload}\n```")
        elif content.get("image_url"):
            parts.append(f"\n\n> {caption}\n\n![{alt_text}]({content['image_url']})")
    return "".join(parts)
