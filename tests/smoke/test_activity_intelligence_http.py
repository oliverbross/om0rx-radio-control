import asyncio
import json

import httpx

from activity_intelligence.adapters import SourceAdapter
from activity_intelligence.models import RawFetchResult, SourceSyncState
from activity_intelligence.repository import ActivityRepository
from activity_intelligence.services import ActivityIntelligenceService


class EmptyContestAdapter(SourceAdapter):
    source_id = "TEST_HTTP"
    url = "https://example.invalid/feed.json"
    poll_seconds = 60

    def parse(self, raw: RawFetchResult):
        payload = json.loads(raw.body or "[]")
        if not isinstance(payload, list):
            raise RuntimeError("schema changed: expected list")
        return {"contests": []}


def run_refresh(handler, tmp_path, state=None):
    async def _run():
        repo = ActivityRepository(tmp_path / "ai.duckdb")
        service = ActivityIntelligenceService(repository=repo)
        adapter = EmptyContestAdapter()
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(0.1), follow_redirects=True) as client:
            result = await service._refresh_adapter(client, adapter, state or SourceSyncState(adapter.source_id))
        return result, repo.get_source_state(adapter.source_id)

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
