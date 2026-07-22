"""Controlled RRULE subset evaluation for habits and recurring tasks.

Supports a small, safe grammar (no arbitrary RRULE parsing):
  FREQ=DAILY
  FREQ=WEEKLY;BYDAY=MO,TU,...   (default: every day of week if BYDAY absent)
  FREQ=MONTHLY;BYMONTHDAY=1,15
An interval INTERVAL=n applies to DAILY/WEEKLY as a stride from active_from.
Occurrences are evaluated in the user's local date, never in UTC.
"""

from __future__ import annotations

from datetime import date

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse(rule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for token in rule.replace("RRULE:", "").split(";"):
        if "=" in token:
            k, v = token.split("=", 1)
            parts[k.strip().upper()] = v.strip().upper()
    return parts


def occurs_on(rule: str, local_date: date, *, anchor: date | None = None) -> bool:
    """Return True if the recurrence produces an occurrence on local_date."""
    parts = _parse(rule)
    freq = parts.get("FREQ", "DAILY")
    interval = int(parts.get("INTERVAL", "1") or "1")
    anchor = anchor or local_date

    if freq == "DAILY":
        if interval <= 1:
            return True
        return (local_date - anchor).days % interval == 0

    if freq == "WEEKLY":
        byday = parts.get("BYDAY")
        if byday:
            allowed = {_WEEKDAYS[d] for d in byday.split(",") if d in _WEEKDAYS}
            if local_date.weekday() not in allowed:
                return False
        if interval > 1:
            weeks = (local_date - anchor).days // 7
            if weeks % interval != 0:
                return False
        return True

    if freq == "MONTHLY":
        bymonthday = parts.get("BYMONTHDAY")
        if bymonthday:
            days = {int(x) for x in bymonthday.split(",") if x.strip().isdigit()}
            return local_date.day in days
        return local_date.day == anchor.day

    return False


def is_valid_rule(rule: str) -> bool:
    parts = _parse(rule)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY", "MONTHLY"):
        return False
    if "BYDAY" in parts and any(d not in _WEEKDAYS for d in parts["BYDAY"].split(",")):
        return False
    return not (
        "BYMONTHDAY" in parts
        and any(not x.strip().isdigit() for x in parts["BYMONTHDAY"].split(","))
    )
