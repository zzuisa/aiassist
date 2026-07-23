"""Idempotent search-document refresh/delete tasks.

The derived index accelerates cross-entity ranking. Refresh upserts a document
by (user, entity_type, entity_id); delete removes it. Because search also queries
committed data directly, these tasks are never on the critical read path.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from app.db.session import session_scope
from app.models.search import SearchDocument
from app.workers.celery_app import celery


def _upsert_document(
    user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    title: str,
    body: str,
    tags_text: str = "",
    category_text: str = "",
) -> None:
    with session_scope() as s:
        doc = s.scalar(
            select(SearchDocument).where(
                SearchDocument.user_id == user_id,
                SearchDocument.entity_type == entity_type,
                SearchDocument.entity_id == entity_id,
            )
        )
        if doc is None:
            doc = SearchDocument(
                id=uuid.uuid4(),
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            s.add(doc)
        doc.title = title
        doc.body = body
        doc.tags_text = tags_text
        doc.category_text = category_text
        s.flush()
        # Recompute tsvector from the text columns.
        s.execute(
            text(
                "UPDATE search_documents SET document_tsv = "
                "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,'') "
                "|| ' ' || coalesce(tags_text,'') || ' ' || coalesce(category_text,'')), "
                "indexed_at = now() WHERE id = :id"
            ),
            {"id": doc.id},
        )


@celery.task(name="app.workers.tasks.search.refresh_document")
def refresh_document(
    user_id: str, entity_type: str, entity_id: str, title: str, body: str = ""
) -> str:
    _upsert_document(uuid.UUID(user_id), entity_type, uuid.UUID(entity_id), title, body)
    return "refreshed"


@celery.task(name="app.workers.tasks.search.delete_document")
def delete_document(user_id: str, entity_type: str, entity_id: str) -> str:
    with session_scope() as s:
        s.execute(
            text(
                "DELETE FROM search_documents WHERE user_id = :u AND entity_type = :t "
                "AND entity_id = :e"
            ),
            {"u": uuid.UUID(user_id), "t": entity_type, "e": uuid.UUID(entity_id)},
        )
    return "deleted"
