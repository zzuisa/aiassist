"""Agent read results are normalized without mutating source data."""

from __future__ import annotations

import pytest
from app.modules.agent.service import clean_result_items

pytestmark = [pytest.mark.unit]


def test_clean_result_items_deduplicates_and_marks_anomalies() -> None:
    cleaned, anomalies = clean_result_items(
        [
            {"id": "1", "name": "  技术  "},
            {"id": "2", "name": "技术"},
            {"id": "3", "name": ""},
            {"id": "4", "name": None},
            {"id": "5", "name": "生活", "usage_count": -1},
        ],
        name_field="name",
    )

    assert [item["name"] for item in cleaned] == ["技术", "生活"]
    assert cleaned[0]["id"] == "1"
    assert any(item["reason"] == "empty_name" for item in anomalies)
    assert any(item["reason"] == "duplicate_name" for item in anomalies)
    assert any(item["reason"] == "negative_count" for item in anomalies)
