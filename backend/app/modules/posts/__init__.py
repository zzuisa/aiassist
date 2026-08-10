"""Posts / blog content-management module (spec 005).

The blog extension keeps the existing publication surface (``router``, ``service``,
``rendering``) and layers content capture, versioning, taxonomy, versioned Skills
and asynchronous AI runs on top. Responsibilities are split across sibling service
modules so each user story can land independently:

- ``capture_service``  — blank/clipboard/URL/quick capture, first revision + Job.
- ``skill_service``    — mutable Skill identity, immutable versions, scoped defaults.
- ``taxonomy_service`` — category tree, tags, keywords, alias resolution, merges.
- ``ai_service``       — AI run submission, candidate derivation, field-level apply.
- ``query_service``    — cursor listing, triage, search, timeline, word-cloud.

All queries begin from ``user_id``; the AI never mutates a Post's current revision
directly — it only produces reviewable candidates.
"""
