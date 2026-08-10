"""Provider-neutral MCP (Model Context Protocol) tool gateway.

See ``base.py`` for the protocol/error/result types, ``config.py`` for the
read-only secrets-file loader, ``provider.py`` for the official-SDK-backed
Streamable HTTP implementation, and ``gateway.py`` for the synchronous facade
used by workers and FastAPI dependencies.
"""

from __future__ import annotations
