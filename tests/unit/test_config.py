from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from adr_mcp.config import Settings


def test_settings_expand_path(tmp_path: Path) -> None:
    settings = Settings(ANTHROPIC_API_KEY="test", ADR_DB_PATH=tmp_path / "adr.db")
    assert settings.adr_db_path.name == "adr.db"
    assert settings.adr_conflict_threshold == 0.72


def test_missing_key_raises_clear_error(tmp_path: Path) -> None:
    settings = Settings(ADR_DB_PATH=tmp_path / "adr.db")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        settings.require_anthropic_api_key()


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(ANTHROPIC_API_KEY="test", ADR_DB_PATH=tmp_path / "adr.db", ADR_CONFLICT_THRESHOLD=2)
