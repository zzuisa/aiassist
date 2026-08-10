"""Execution and normalization for blog visual enhancements.

Visual plans are the preferred format for reader-facing explainers.  The worker
turns the validated plan into a real PNG using a CJK-capable font, stores it as
a private post asset, and inserts a normal Markdown image into the article.
Mermaid remains supported as a backward-compatible format for technical
diagrams.
"""

from __future__ import annotations

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings
from app.services.storage.providers.local import get_storage

_MAX_MERMAID = 20_000
_MAX_CHART_POINTS = 100
_MAX_IMAGE_RESPONSE = 64 * 1024
_DANGEROUS_MERMAID = re.compile(r"<\s*script|javascript:|data:text/html|on\w+\s*=", re.I)
_VISUAL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_FONT_CANDIDATES = (
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 2),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
    ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        (("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2), *_FONT_CANDIDATES)
        if bold
        else _FONT_CANDIDATES
    )
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size=size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Wrap by measured pixels, not character count, so CJK text stays aligned."""
    value = text.strip()
    if not value:
        return []
    lines: list[str] = []
    current = ""
    for char in value:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines
    lines = lines[:max_lines]
    last = lines[-1]
    while last and draw.textlength(last + "…", font=font) > max_width:
        last = last[:-1]
    lines[-1] = (last or "…") + "…"
    return lines


def _draw_arrow(
    draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str
) -> None:
    draw.line([start, end], fill=color, width=4)
    dx, dy = end[0] - start[0], end[1] - start[1]
    if abs(dx) >= abs(dy):
        direction = 1 if dx >= 0 else -1
        tip = end
        points = [tip, (tip[0] - direction * 13, tip[1] - 7), (tip[0] - direction * 13, tip[1] + 7)]
    else:
        direction = 1 if dy >= 0 else -1
        tip = end
        points = [tip, (tip[0] - 7, tip[1] - direction * 13), (tip[0] + 7, tip[1] - direction * 13)]
    draw.polygon(points, fill=color)


def _edge_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ink: str,
) -> None:
    if not text:
        return
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0] + 20
    height = box[3] - box[1] + 10
    x = center[0] - width // 2
    y = center[1] - height // 2
    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=height // 2,
        fill="#ffffff",
        outline="#d8e2e8",
        width=1,
    )
    draw.text((center[0], center[1]), text, font=font, fill=ink, anchor="mm")


def render_visual_plan_png(plan: dict[str, Any]) -> bytes:
    """Render a validated plan as a deterministic, readable PNG.

    The renderer deliberately uses measured text metrics and a generous card
    layout.  This avoids the browser SVG text-baseline/overflow failures that
    motivated replacing the previous client-side download flow.
    """
    palette = {
        "warm": ((255, 249, 242), "#513b2f", "#8d7567", "#d7a17a", "#ee965c"),
        "fresh": ((243, 251, 248), "#173f3c", "#5b7773", "#76aaa2", "#4cae97"),
        "calm": ((246, 248, 255), "#303858", "#68728e", "#96a4d6", "#768be3"),
        "energetic": ((255, 249, 241), "#472b20", "#866658", "#df9078", "#f27148"),
        "neutral": ((248, 249, 251), "#2d3742", "#687583", "#9aa9b7", "#697e94"),
    }
    background, ink, muted, line, accent = palette.get(plan["theme"], palette["fresh"])
    nodes = plan["nodes"]
    layout = plan["layout"]
    columns = 1 if layout == "compact_vertical" else len(nodes) if len(nodes) <= 4 else 3
    card_width, card_height = 330, 220
    gap_x, gap_y = 34, 44
    rows = (len(nodes) + columns - 1) // columns
    width = max(920, columns * card_width + max(0, columns - 1) * gap_x + 72)
    height = 112 + rows * card_height + max(0, rows - 1) * gap_y + 54
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    title_font = _font(34, bold=True)
    label_font = _font(25, bold=True)
    detail_font = _font(18)
    edge_font = _font(16)
    draw.text((36, 32), plan["title"], font=title_font, fill=ink)
    positions: dict[str, tuple[int, int]] = {}
    content_width = columns * card_width + max(0, columns - 1) * gap_x
    start_x = (width - content_width) // 2
    for index, node in enumerate(nodes):
        row, column = divmod(index, columns)
        x = start_x + column * (card_width + gap_x)
        y = 112 + row * (card_height + gap_y)
        positions[node["id"]] = (x, y)
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=24,
            fill="#ffffff",
            outline=accent,
            width=3,
        )
        draw.ellipse((x + 24, y + 28, x + 74, y + 78), fill=accent)
        draw.text(
            (x + 49, y + 53), str(index + 1), font=_font(23, bold=True), fill="#ffffff", anchor="mm"
        )
        label_lines = _wrap_text(draw, node["label"], label_font, card_width - 108, 2)
        draw.multiline_text(
            (x + 92, y + 30), "\n".join(label_lines), font=label_font, fill=ink, spacing=3
        )
        detail_y = y + 104 if len(label_lines) <= 1 else y + 134
        detail_lines = _wrap_text(draw, node.get("detail", ""), detail_font, card_width - 48, 3)
        draw.multiline_text(
            (x + 24, detail_y), "\n".join(detail_lines), font=detail_font, fill=muted, spacing=5
        )

    for edge in plan["edges"]:
        source = positions.get(edge["from"])
        target = positions.get(edge["to"])
        if source is None or target is None:
            continue
        source_row = next(
            i // columns for i, node in enumerate(nodes) if node["id"] == edge["from"]
        )
        target_row = next(i // columns for i, node in enumerate(nodes) if node["id"] == edge["to"])
        source_col = next(i % columns for i, node in enumerate(nodes) if node["id"] == edge["from"])
        target_col = next(i % columns for i, node in enumerate(nodes) if node["id"] == edge["to"])
        if source_row == target_row and target_col > source_col:
            start = (source[0] + card_width, source[1] + card_height // 2)
            end = (target[0], target[1] + card_height // 2)
            _draw_arrow(draw, start, end, line)
            _edge_label(
                draw,
                edge.get("label", ""),
                ((start[0] + end[0]) // 2, start[1] - 24),
                edge_font,
                ink,
            )
        elif source_row == target_row:
            route_y = min(height - 26, source[1] + card_height + 22)
            start = (source[0] + card_width // 2, source[1] + card_height)
            end = (target[0] + card_width // 2, target[1] + card_height)
            draw.line([start, (start[0], route_y), (end[0], route_y), end], fill=line, width=4)
            _draw_arrow(draw, (end[0], route_y), end, line)
            _edge_label(
                draw,
                edge.get("label", ""),
                ((start[0] + end[0]) // 2, route_y - 24),
                edge_font,
                ink,
            )
        else:
            start = (source[0] + card_width // 2, source[1] + card_height)
            end = (target[0] + card_width // 2, target[1])
            mid_y = (start[1] + end[1]) // 2
            draw.line([start, (start[0], mid_y), (end[0], mid_y), end], fill=line, width=4)
            _draw_arrow(draw, (end[0], mid_y), end, line)
            _edge_label(
                draw, edge.get("label", ""), ((start[0] + end[0]) // 2, mid_y - 24), edge_font, ink
            )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


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


def _as_visual_plan(content: dict[str, Any]) -> dict[str, Any] | None:
    """Validate the graph contract used by the visual renderer."""
    raw = content.get("visual_plan") or content.get("plan")
    if not isinstance(raw, dict):
        return None
    visual_type = raw.get("visual_type", "compact_flow")
    layout = raw.get("layout", "compact_horizontal")
    theme = raw.get("theme", "fresh")
    title = raw.get("title", "")
    nodes = raw.get("nodes")
    edges = raw.get("edges", [])
    if (
        not isinstance(visual_type, str)
        or not (1 <= len(visual_type.strip()) <= 80)
        or not isinstance(layout, str)
        or not (1 <= len(layout.strip()) <= 80)
        or not isinstance(theme, str)
        or not (1 <= len(theme.strip()) <= 80)
    ):
        return None
    if not isinstance(title, str) or not (1 <= len(title.strip()) <= 120):
        return None
    if not isinstance(nodes, list) or not nodes:
        return None
    if not isinstance(edges, list):
        return None

    normalized_nodes: list[dict[str, str]] = []
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            return None
        node_id = node.get("id")
        label = node.get("label")
        if (
            not isinstance(node_id, str)
            or not _VISUAL_ID.fullmatch(node_id)
            or node_id in node_ids
            or not isinstance(label, str)
            or not (1 <= len(label.strip()) <= 40)
        ):
            return None
        node_ids.add(node_id)
        normalized_nodes.append(
            {
                "id": node_id,
                "label": label.strip(),
                "detail": str(node.get("detail", "")).strip()[:80],
                "icon": str(node.get("icon", "step")).strip()[:24],
            }
        )

    normalized_edges: list[dict[str, str]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            return None
        source = edge.get("from")
        target = edge.get("to")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in node_ids
            or target not in node_ids
            or source == target
        ):
            return None
        normalized_edges.append(
            {
                "from": source,
                "to": target,
                "label": str(edge.get("label", "")).strip()[:30],
            }
        )
    return {
        "visual_type": visual_type,
        "layout": layout,
        "theme": theme,
        "title": title.strip(),
        "nodes": normalized_nodes,
        "edges": normalized_edges,
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
    endpoint_value = capability.get("endpoint")
    endpoint = endpoint_value if isinstance(endpoint_value, str) else ""
    parsed = urlparse(endpoint)
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
                candidates.extend(item.get("url") for item in values if isinstance(item, dict))
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


def execute_enhancements(
    result: Any,
    *,
    max_visual_items: int = 2,
    user_id: uuid.UUID | None = None,
    post_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Validate visuals and persist reader-facing visual plans as PNG assets.

    The optional IDs keep the pure unit-test path backward compatible. Worker
    calls always provide them, which changes the enhancement into a Markdown
    image backed by a private, ownership-checked post asset.
    """
    return execute_enhancement_items(
        result.enhancements,
        max_visual_items=max_visual_items,
        user_id=user_id,
        post_id=post_id,
    )


def execute_enhancement_items(
    enhancements: list[Any],
    *,
    max_visual_items: int = 2,
    user_id: uuid.UUID | None = None,
    post_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Execute a validated list of enhancements, including deterministic fallbacks."""
    executed: list[dict[str, Any]] = []
    for enhancement in enhancements:
        if enhancement.status != "executed":
            continue
        if len(executed) >= max(1, min(10, max_visual_items)):
            enhancement.status = "skipped"
            enhancement.reason = "超过本次视觉内容数量上限"
            continue
        content = enhancement.content if isinstance(enhancement.content, dict) else {}
        if enhancement.capability == "visualize":
            visual_plan = _as_visual_plan(content)
            if visual_plan is not None:
                if user_id is not None and post_id is not None:
                    asset_id = uuid.uuid4()
                    key = f"posts/{user_id}/visuals/{post_id}/{asset_id}.png"
                    png = render_visual_plan_png(visual_plan)
                    get_storage().put_stream(
                        key,
                        io.BytesIO(png),
                        media_type="image/png",
                        max_bytes=max(len(png), 1),
                    )
                    enhancement.content = {
                        "format": "image",
                        "image_url": f"/api/v1/posts/{post_id}/visual-assets/{asset_id}.png",
                        "asset_id": str(asset_id),
                        "visual_plan": visual_plan,
                    }
                else:
                    enhancement.content = {"format": "visual-plan", "visual_plan": visual_plan}
            else:
                source = _as_mermaid(content)
                if source is None:
                    enhancement.status = "failed"
                    enhancement.reason = "视觉方案未通过安全或结构门控"
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
                    "unavailable" if metadata.get("code") == "CAPABILITY_UNAVAILABLE" else "failed"
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
        if content.get("image_url"):
            parts.append(f"\n\n> {caption}\n\n![{alt_text}]({content['image_url']})")
        elif item.get("capability") == "visualize" and content.get("visual_plan"):
            visual_payload = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"\n\n> {caption}\n\n```visual-plan\n{visual_payload}\n```")
        elif item.get("capability") == "visualize" and content.get("mermaid"):
            parts.append(f"\n\n> {caption}\n\n```mermaid\n{content['mermaid']}\n```")
        elif item.get("capability") == "answers-charts" and content.get("data"):
            chart_payload = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"\n\n> {caption}\n\n```echarts\n{chart_payload}\n```")
    return "".join(parts)


def insert_enhancements(markdown: str, enhancements: list[dict[str, Any]]) -> str:
    """Place visual material after the article introduction.

    ``insert_after=body`` is the model's semantic request for reader-facing
    body content.  The first prose paragraph is the most stable location: it
    gives the reader context before the image and keeps the image beside the
    section that explains it.
    """
    block = enhancements_markdown(enhancements)
    if not block:
        return markdown
    lines = markdown.splitlines(keepends=True)
    in_intro = False
    insert_at: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if in_intro:
                insert_at = index + 1
                break
            continue
        if stripped.startswith("#"):
            continue
        if not in_intro:
            in_intro = True
    if insert_at is None:
        return markdown.rstrip() + block + "\n"
    return "".join(lines[:insert_at]) + block.lstrip("\n") + "\n\n" + "".join(lines[insert_at:])
