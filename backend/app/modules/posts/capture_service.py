"""Content capture: blank / clipboard / URL / quick paths (spec 005, US1).

Each capture persists the raw content and a first ``capture`` revision before any
extraction or AI runs, so nothing is lost when the network or Workers are down. URL
capture saves the Post (``content_status=pending_parse``), a ``PostSource``
(``status=pending``) and an extraction Job in one transaction and returns without
waiting on the network. Implementation lands in T037.
"""

from __future__ import annotations
