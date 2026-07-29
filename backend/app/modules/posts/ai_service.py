"""AI runs and candidate review (spec 005, US3/US4).

Submitting an optimization creates an ``AsyncJob(job_type=blog.optimize)``, a
``PostAIRun`` frozen against a base revision + Skill version + field-policy snapshot,
and an Outbox row in one transaction; the idempotency key is derived from
user/post/base_revision/optimization_type/skill_version/request nonce. The run only
produces a ``PostAICandidate``; applying selected fields is a separate locked
transaction that re-checks the version and creates an ``ai_applied`` revision.
Implementation lands in T071 / T087 / T088 / T090.
"""

from __future__ import annotations
