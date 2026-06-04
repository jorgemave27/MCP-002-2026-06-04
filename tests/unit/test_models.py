from __future__ import annotations

from adr_mcp.models.adr import ADRStructure, CreateADRInput, SearchDecisionsInput


def test_tags_are_normalized() -> None:
    structure = ADRStructure(
        title="Use PostgreSQL",
        context="context",
        decision="decision",
        consequences="consequence",
        tags=["Database", " database ", "PostgreSQL"],
    )
    assert structure.tags == ["database", "postgresql"]


def test_tool_schemas_are_json_schema_objects() -> None:
    for model in [CreateADRInput, SearchDecisionsInput]:
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
