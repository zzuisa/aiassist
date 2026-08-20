"""Immutable, user-scoped capability snapshots for Agent planning."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import (
    AgentCapabilitySnapshot,
    AgentCapabilitySnapshotItem,
    AgentTask,
)
from app.models.agent_conversation import McpConnection, McpToolSnapshot
from app.modules.agent.registry import ToolDefinition, tool_registry

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


def safe_capability_name(namespace: str, provider_name: str) -> str:
    """Return a stable Anthropic-compatible public tool name (max 64 chars)."""
    base = _UNSAFE_NAME.sub("-", f"{namespace}-{provider_name}").strip("-_") or "tool"
    if len(base) <= 64:
        return base
    digest = hashlib.sha256(f"{namespace}\0{provider_name}".encode()).hexdigest()[:10]
    return f"{base[:53].rstrip('-_')}-{digest}"


def safe_name_for_tool(tool: ToolDefinition) -> str:
    if tool.safe_name:
        return tool.safe_name
    if tool.source == "mcp":
        namespace = str(tool.connection_id or "mcp")[:12]
        return safe_capability_name(namespace, tool.name)
    return safe_capability_name("internal", tool.name)


def create_snapshot(session: Session, *, task: AgentTask) -> AgentCapabilitySnapshot:
    existing = session.scalar(
        select(AgentCapabilitySnapshot).where(AgentCapabilitySnapshot.task_id == task.id)
    )
    if existing is not None:
        return existing

    manifest = tool_registry.safe_manifest_v2(session=session, user_id=task.user_id)
    available_entries = [item for item in manifest["tools"] if item.get("available")][:100]
    canonical = json.dumps(
        available_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    snapshot = AgentCapabilitySnapshot(
        task_id=task.id,
        user_id=task.user_id,
        schema_version="capability-snapshot.v1",
        manifest_version=str(manifest.get("schema_version") or "safe-tool-manifest.v2"),
        content_digest=hashlib.sha256(canonical.encode()).hexdigest(),
        capability_count=len(available_entries),
    )
    session.add(snapshot)
    session.flush()

    for entry in available_entries:
        public_name = str(entry["key"])
        tool = tool_registry.get(public_name)
        catalog_version: str | None = None
        output_schema: dict[str, Any] | None = tool.output_schema
        connection_id = tool.connection_id
        if tool.source == "mcp":
            provider_snapshot = session.scalar(
                select(McpToolSnapshot)
                .join(McpConnection, McpConnection.id == McpToolSnapshot.connection_id)
                .where(
                    McpToolSnapshot.tool_key == tool.name,
                    McpConnection.user_id == task.user_id,
                )
                .order_by(McpToolSnapshot.discovered_at.desc())
            )
            if provider_snapshot is not None:
                connection_id = provider_snapshot.connection_id
                catalog_version = provider_snapshot.catalog_version
                output_schema = provider_snapshot.output_schema_json
        session.add(
            AgentCapabilitySnapshotItem(
                snapshot_id=snapshot.id,
                safe_name=public_name,
                source=tool.source,
                definition_version="tool-definition.v1",
                catalog_version=catalog_version,
                tool_type=tool.type,
                responsibility=tool.responsibility[:500],
                input_schema_json=tool.input_schema,
                output_schema_json=output_schema,
                risk_json=tool.risk,
                required_permission=tool.required_permission,
                available=True,
                unavailable_reason=None,
                connection_id=connection_id,
                provider_tool_key=tool.name,
                timeout_seconds=max(1, int(tool.timeout_seconds)),
                max_retries=tool.max_retries,
                idempotency_mode="required" if tool.type == "write" else "none",
                verification_mode="required" if tool.type == "write" else "none",
            )
        )
    session.flush()
    return snapshot
