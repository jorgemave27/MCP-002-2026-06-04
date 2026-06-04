from __future__ import annotations

import pytest

import adr_mcp.server as server


@pytest.mark.asyncio
async def test_server_tool_wrappers_delegate_to_service(service, monkeypatch) -> None:
    async def fake_get_service():
        return service

    monkeypatch.setattr(server, "get_service", fake_get_service)

    created = await server.create_adr(
        raw_text="We chose PostgreSQL for billing database transactions.",
        project_id="billing",
        author="team",
    )
    adr_id = created["id"]

    fetched = await server.get_adr(adr_id)
    assert fetched["id"] == adr_id

    listed = await server.list_adrs(project_id="billing", page=1, page_size=10)
    assert listed["total"] == 1

    searched = await server.search_decisions(
        query="database decision",
        top_k=5,
        filter_tags=["database"],
        status="ACCEPTED",
    )
    assert len(searched["results"]) == 1

    conflicts = await server.check_conflicts(adr_id)
    assert "conflicts" in conflicts

    summary = await server.summarize_project(project_id="billing")
    assert summary["adr_count"] == 1

    reindexed = await server.reindex_embeddings(project_id="billing", batch_size=1, concurrency=1)
    assert reindexed["reindexed"] == 1

    deprecated = await server.deprecate_adr(adr_id, reason="No longer preferred.")
    assert deprecated["status"] == "DEPRECATED"


def test_server_main_calls_mcp_run(monkeypatch) -> None:
    called = {"run": False}

    def fake_run() -> None:
        called["run"] = True

    monkeypatch.setattr(server.mcp, "run", fake_run)

    server.main()

    assert called["run"] is True
