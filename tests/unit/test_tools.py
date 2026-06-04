from __future__ import annotations

import pytest

from adr_mcp.tools.create_adr import create_adr_handler
from adr_mcp.tools.get_adr import get_adr_handler


@pytest.mark.asyncio
async def test_create_adr_handler_serializes_success(service) -> None:
    response = await create_adr_handler(
        service,
        raw_text="We chose PostgreSQL for billing database transactions.",
        project_id="billing",
    )
    assert response["title"] == "Use PostgreSQL"
    assert response["status"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_get_adr_handler_serializes_structured_error(service) -> None:
    response = await get_adr_handler(service, adr_id="missing")
    assert response["error"]["code"] == "adr_not_found"
