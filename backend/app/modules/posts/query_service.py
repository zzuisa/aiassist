"""Read-side queries: listing, triage, search, timeline, word cloud (spec 005).

Owner-scoped cursor listing with combinable filters and derived AI/source summaries;
triage projections (quick/failed/stale/draft); module search across current Post,
source URL, taxonomy, code and flattened structured fields; occurrence/creation
timelines with an explicit fallback basis; and word-cloud filter-hash lookups with a
last-success fallback. Implementation lands in T116 / T117 / T132 / T135 / T160.
"""

from __future__ import annotations
