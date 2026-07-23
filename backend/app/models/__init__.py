"""Aggregate model imports so Alembic sees a single, complete metadata.

Every feature module's models are imported here as they are added. Importing
``app.models`` yields all mapped tables via ``Base.metadata``.
"""

from app.db.base import Base
from app.models import foundation as foundation
from app.models import habits as habits
from app.models import notifications as notifications
from app.models import relations as relations
from app.models import scheduling as scheduling
from app.models import tasks as tasks
from app.models import voice as voice

metadata = Base.metadata

__all__ = ["Base", "metadata"]
