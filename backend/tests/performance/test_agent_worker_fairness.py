"""Bounded Agent fan-out leaves scheduling capacity for independent work."""

from __future__ import annotations

import threading
import time

from app.modules.agent.runner import WorkItem, run_bounded


def test_bounded_io_fanout_does_not_starve_independent_probe() -> None:
    started = threading.Event()

    def work(_item: WorkItem) -> str:
        started.set()
        time.sleep(0.04)
        return "ok"

    worker = threading.Thread(
        target=lambda: run_bounded(
            [WorkItem(key=str(index), input_scope={}) for index in range(25)],
            work,
            max_concurrency=4,
        )
    )
    worker.start()
    assert started.wait(timeout=0.2)
    probe_started = time.monotonic()
    time.sleep(0)
    probe_latency = time.monotonic() - probe_started
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert probe_latency < 0.1
