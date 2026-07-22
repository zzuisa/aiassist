"""Aggregate model imports so Alembic sees a single, complete metadata.

Every feature module's models are imported here as they are added. Importing
``app.models`` yields all mapped tables via ``Base.metadata``.
"""

from app.db.base import Base
from app.models import foundation as foundation

metadata = Base.metadata

__all__ = ["Base", "metadata"]
