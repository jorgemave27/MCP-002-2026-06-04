from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_audit_log_is_append_only(service) -> None:
    result = await service.create_adr("We chose PostgreSQL for billing.", project_id="core")
    record = await service.get_adr(result.id)
    audit_id = record.audit_log[0].id

    with pytest.raises(Exception, match="append-only"):
        async with service.db.write_lock:
            try:
                await service.db.conn.execute(
                    "UPDATE adr_audit_log SET payload = '{}' WHERE id = ?",
                    (audit_id,),
                )
                await service.db.conn.commit()
            finally:
                await service.db.conn.rollback()

    with pytest.raises(Exception, match="append-only"):
        async with service.db.write_lock:
            try:
                await service.db.conn.execute("DELETE FROM adr_audit_log WHERE id = ?", (audit_id,))
                await service.db.conn.commit()
            finally:
                await service.db.conn.rollback()
