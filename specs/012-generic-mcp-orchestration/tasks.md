# Tasks: LangGraph Generic MCP Orchestration

**Input**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: Setup

- [X] T001 Add locked LangGraph runtime dependencies in `backend/pyproject.toml`, `backend/requirements.lock.txt`, and `backend/requirements-dev.lock.txt`.
- [X] T002 Add Graph Runtime module boundaries under `backend/app/modules/agent/` without exposing MCP clients to the planning model.

## Phase 2: Foundational

- [X] T003 [P] Add unit coverage for Graph state, fixed graph topology, and `thread_id` configuration in `backend/tests/unit/test_agent_graph_runtime.py`.
- [X] T004 Add the LangGraph runtime and fixed safe graph in `backend/app/modules/agent/graph_runtime.py`.
- [X] T005 Replace the plan Celery coordinator with one Graph invoke/resume task in `backend/app/workers/tasks/agent.py`.

## Phase 3: User Story 1 - Execute bounded MCP plans (Priority: P1)

- [X] T006 [US1] Route accepted plans through Graph Runtime while preserving ToolRegistry, ownership, confirmation, idempotency, and verification gates in `backend/app/modules/agent/graph_runtime.py`.
- [X] T007 [US1] Persist Graph run/thread references and runtime state in `backend/app/models/agent.py` and the matching Alembic migration.
- [X] T008 [US1] Update retry, cancel, confirmation resume, and stalled-plan repair paths to issue Graph resume commands in `backend/app/modules/agent/router.py`, `backend/app/modules/agent/scheduler.py`, and `backend/app/modules/agent/status.py`.
- [X] T009 [US1] Add integration coverage for worker redelivery, confirmation resume, and no duplicate operator effects in `backend/tests/integration/test_agent_graph_runtime.py`.

## Phase 4: Polish

- [X] T010 [P] Update Graph deployment/checkpointer setup and operator runbook in `specs/012-generic-mcp-orchestration/quickstart.md` and `docs/operations.md`.
- [X] T011 Run focused agent tests, contract validation, and lint; record migration risks in `specs/012-generic-mcp-orchestration/quickstart.md`.

## Dependencies

`T001 -> T002 -> T003/T004 -> T005 -> T006/T007 -> T008 -> T009 -> T010/T011`

## MVP

T001-T006 and T009 provide the first demonstrable LangGraph execution path. T007-T008 are required before production rollout.
