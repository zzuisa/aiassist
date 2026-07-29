"""Taxonomy: category tree, tags, keywords, aliases and merges (spec 005, US8).

Categories form a bounded-depth tree; tags carry alias profiles; keywords track
synonyms and stop-words. Small merges run in one transaction; large merges run as
an idempotent background job writing a ``TaxonomyMerge`` audit row. Disabled items
stay resolvable for history. Implementation lands in T146–T149.
"""

from __future__ import annotations
