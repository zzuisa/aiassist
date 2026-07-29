"""Skill configuration: mutable identity, immutable versions, scoped defaults.

A Skill has a stable identity and an append-only chain of ``SkillVersion`` rows;
saving assigns an incrementing ``version_number`` and updates ``current_version_id``.
Exactly one default may exist per scope (global / content_class / content_type).
Resolution tries manual → content-type default → class default → global default,
validating enabled/applicable/complete at each step. Implementation lands in
T022 / T102 / T103.
"""

from __future__ import annotations
