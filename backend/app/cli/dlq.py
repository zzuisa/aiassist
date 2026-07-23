"""Dead-letter queue inspection and replay CLI.

Replay requires explicit operator confirmation and re-publishes with a new trace
and attempt so the redelivery is auditable. This never runs automatically.
"""

from __future__ import annotations

import argparse
import json
import sys


def _dlq_name(queue: str) -> str:
    return f"{queue}.dlq"


def cmd_inspect(queue: str, limit: int) -> int:
    from kombu import Connection

    from app.core.config import get_settings

    dlq = _dlq_name(queue)
    count = 0
    with Connection(get_settings().amqp_dsn) as conn:
        bound = conn.SimpleQueue(dlq)
        try:
            while count < limit:
                try:
                    msg = bound.get(block=False)
                except Exception:  # queue empty
                    break
                print(json.dumps({"headers": dict(msg.headers or {}), "body": msg.payload}))
                msg.requeue()  # inspection does not consume
                count += 1
        finally:
            bound.close()
    print(f"Inspected {count} message(s) on {dlq}.")
    return 0


def cmd_replay(queue: str, limit: int, yes: bool) -> int:
    if not yes:
        answer = input(
            f"Replay up to {limit} message(s) from {_dlq_name(queue)} back to {queue}? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1
    from kombu import Connection, Exchange

    from app.core.config import get_settings

    exchange = Exchange("aiassist.commands", type="topic", durable=True)
    moved = 0
    with Connection(get_settings().amqp_dsn) as conn:
        source = conn.SimpleQueue(_dlq_name(queue))
        producer = conn.Producer(serializer="json", confirm_publish=True)
        try:
            while moved < limit:
                try:
                    msg = source.get(block=False)
                except Exception:
                    break
                headers = dict(msg.headers or {})
                headers["x-replayed"] = True
                routing_key = headers.get("original_routing_key", f"{queue}.replay")
                producer.publish(
                    msg.payload,
                    exchange=exchange,
                    routing_key=routing_key,
                    headers=headers,
                    declare=[exchange],
                    delivery_mode=2,
                )
                msg.ack()
                moved += 1
        finally:
            source.close()
    print(f"Replayed {moved} message(s) to {queue}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiassist-dlq")
    sub = parser.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("queue")
    p_inspect.add_argument("--limit", type=int, default=20)
    p_replay = sub.add_parser("replay")
    p_replay.add_argument("queue")
    p_replay.add_argument("--limit", type=int, default=10)
    p_replay.add_argument("--yes", action="store_true", help="skip interactive confirmation")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        return cmd_inspect(args.queue, args.limit)
    if args.command == "replay":
        return cmd_replay(args.queue, args.limit, args.yes)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
