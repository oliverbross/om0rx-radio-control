import asyncio
from datetime import UTC, datetime
import json

import httpx

from activity_intelligence.adapters import SourceAdapter
from activity_intelligence.models import RawFetchResult, SourceSyncState
from activity_intelligence.repository import ActivityRepository
from activity_intelligence.services import ActivityIntelligenceService
from radio_control.persistence import atomic_write_json


class EmptyContestAdapter(SourceAdapter):
    source_id = "TEST_HTTP"
    url = "https://example.invalid/feed.json"
    poll_seconds = 60

    def parse(self, raw: RawFetchResult):
        payload = json.loads(raw.body or "[]")
        if not isinstance(payload, list):
            raise RuntimeError("schema changed: expected list")
        return {"contests": []}


def run_refresh(handler, tmp_path, state=None, adapter=None):
    selected_adapter = adapter or EmptyContestAdapter()

    async def _run():
        repo = ActivityRepository(tmp_path / "ai.duckdb")
        service = ActivityIntelligenceService(repository=repo)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(0.1), follow_redirects=True) as client:
            result = await service._refresh_adapter(
                client, selected_adapter, state or SourceSyncState(selected_adapter.source_id),
            )
        return result, repo.get_source_state(selected_adapter.source_id)

    return asyncio.run(_run())


def test_http_refresh_honors_etag_and_304(tmp_path):
    def handler(request):
        assert request.headers["if-none-match"] == '"abc"'
        return httpx.Response(304, headers={"etag": '"abc"'})

    result, state = run_refresh(handler, tmp_path, SourceSyncState("TEST_HTTP", etag='"abc"'))

    assert result["ok"] is True
    assert result["notModified"] is True
    assert state.consecutive_failures == 0
    assert state.last_error is None


def test_trusted_304_renews_dxpedition_watch_freshness(tmp_path, monkeypatch):
    class TrustedAdapter(EmptyContestAdapter):
        source_id = "NG3K_ADXO"

    runtime = tmp_path / "runtime"
    watch_path = runtime / "settings/database/dxpedition_watch.json"
    old_generated = "2026-10-01T00:00:00Z"
    atomic_write_json(watch_path, {
        "schema": 1, "generated_at_utc": old_generated,
        "watch_max_age_seconds": 86400, "spot_max_age_seconds": 120, "entries": [],
    })
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))

    def handler(request):
        return httpx.Response(304, headers={"etag": '"trusted"'})

    result, _ = run_refresh(
        handler, tmp_path, SourceSyncState("NG3K_ADXO", etag='"trusted"'), TrustedAdapter(),
    )
    renewed = json.loads(watch_path.read_text(encoding="utf-8"))
    assert result["ok"] is True and result["notModified"] is True
    assert result["dxpeditionWatch"]["path"] == str(watch_path)
    assert renewed["generated_at_utc"] != old_generated
    assert datetime.fromisoformat(renewed["generated_at_utc"].replace("Z", "+00:00")) <= datetime.now(UTC)


def test_untrusted_304_does_not_publish_dxpedition_watch(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))

    def handler(request):
        return httpx.Response(304)

    result, _ = run_refresh(handler, tmp_path, SourceSyncState("TEST_HTTP"))
    assert result["ok"] is True and result["notModified"] is True
    assert result["dxpeditionWatch"] is None
    assert not (runtime / "settings/database/dxpedition_watch.json").exists()


def test_http_refresh_records_500_with_backoff(tmp_path):
    def handler(request):
        return httpx.Response(500, text="server error")

    result, state = run_refresh(handler, tmp_path)

    assert result["ok"] is False
    assert "HTTP 500" in result["error"]
    assert state.consecutive_failures == 1
    assert state.next_allowed_at_utc


def test_http_refresh_records_schema_change_as_single_source_error(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    result, state = run_refresh(handler, tmp_path)

    assert result["ok"] is False
    assert "schema changed" in result["error"]
    assert state.last_error == result["error"]


def test_http_refresh_records_timeout_without_crashing(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("slow response")

    result, state = run_refresh(handler, tmp_path)

    assert result["ok"] is False
    assert "slow response" in result["error"]
    assert state.consecutive_failures == 1
