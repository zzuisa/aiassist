"""Contract checks for the repository's continuous-integration quality gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.contract]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_PATH = ROOT / "deploy" / "scripts" / "deploy.sh"


def _workflow() -> dict[str, Any]:
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    # PyYAML still applies YAML 1.1 boolean coercion to GitHub's top-level
    # ``on`` key. Normalize that parser quirk after using the safe loader.
    if True in parsed and "on" not in parsed:
        parsed["on"] = parsed.pop(True)
    return parsed


def _commands(job: dict[str, Any]) -> str:
    steps = job.get("steps", [])
    assert isinstance(steps, list)
    return "\n".join(str(step.get("run", "")) for step in steps if isinstance(step, dict))


def test_ci_runs_for_feature_branch_pushes_and_pull_requests() -> None:
    triggers = _workflow()["on"]
    assert isinstance(triggers, dict)
    assert "pull_request" in triggers
    assert "push" in triggers
    push = triggers["push"]
    assert push is None or not isinstance(push, dict) or "branches" not in push


def test_ci_enforces_backend_frontend_security_coverage_and_e2e_gates() -> None:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)
    assert {"backend-quality", "backend-tests", "frontend", "e2e-smoke"} <= set(jobs)

    backend_commands = _commands(jobs["backend-tests"])
    assert "pytest" in backend_commands
    assert "security" in backend_commands
    assert "reliability" in backend_commands
    assert "--cov=app" in backend_commands
    assert "--cov-fail-under=70" in backend_commands

    frontend_commands = _commands(jobs["frontend"])
    assert "npm run lint" in frontend_commands
    assert "npm run typecheck" in frontend_commands
    assert "npm test" in frontend_commands
    assert "npm run build" in frontend_commands

    e2e_commands = _commands(jobs["e2e-smoke"])
    assert "radio_service_password" in e2e_commands
    assert "docker compose up" in e2e_commands
    assert "npm run test:e2e" in e2e_commands


def test_deployment_waits_for_the_pushed_commit_ci_result() -> None:
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    assert "wait_for_ci_gate" in deploy
    assert "gh run watch" in deploy
    assert "[skip ci]" in deploy
    assert deploy.index("prepare_release_commit") < deploy.index("wait_for_ci_gate")
    assert deploy.index("wait_for_ci_gate") < deploy.index('log "Building application images..."')


def test_restart_reuses_existing_images_without_release_side_effects() -> None:
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    restart_body = deploy.split("cmd_restart() {", maxsplit=1)[1].split(
        "\n}\n\ncmd_down()", maxsplit=1
    )[0]

    assert "restart) cmd_restart ;;" in deploy
    assert 'docker compose restart "${APP_SERVICES[@]}"' in restart_body
    assert "verify_application_health" in restart_body
    assert "prepare_release_commit" not in restart_body
    assert "wait_for_ci_gate" not in restart_body
    assert "docker compose pull" not in restart_body
    assert "docker compose build" not in restart_body
    assert "docker compose run --rm migrate" not in restart_body


def test_fast_deploy_updates_code_without_waiting_for_ci_or_restarting_infrastructure() -> None:
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    fast_body = deploy.split("cmd_fast_up() {", maxsplit=1)[1].split(
        "\n}\n\ncmd_restart()", maxsplit=1
    )[0]

    assert "fast-up) cmd_fast_up ;;" in deploy
    assert "prepare_fast_deploy_commit" in fast_body
    assert "docker compose build backend frontend" in fast_body
    assert "docker compose run --rm --no-deps migrate" in fast_body
    assert 'docker compose up -d --no-deps --force-recreate "${REDEPLOY_SERVICES[@]}"' in fast_body
    assert "verify_application_health" in fast_body
    assert "wait_for_ci_gate" not in fast_body
    assert "docker compose pull" not in fast_body
    assert "postgres redis rabbitmq" not in fast_body.split("docker compose up", maxsplit=1)[-1]
