import asyncio

import _bootstrap  # noqa: F401
from radio_control.qrz_api import QRZClient


def test_qrz_auth_failure_is_not_reported_as_callsign_not_found(monkeypatch):
    client = QRZClient()
    client.profile_cache = {}

    async def fake_lookup(callsign, *, retry_session=True):
        return {
            "success": False,
            "message": "QRZ authentication failed: Username/password incorrect",
            "error_type": "auth",
            "retryable": False,
        }

    monkeypatch.setattr(client, "_lookup_profile_internal", fake_lookup)

    result = asyncio.run(client.get_profile_picture("A61DI"))

    assert result["success"] is False
    assert result["error_type"] == "auth"
    assert "authentication failed" in result["message"].lower()
    assert "callsign not found" not in result["message"].lower()


def test_qrz_all_variant_not_found_still_reports_not_found(monkeypatch):
    client = QRZClient()
    client.profile_cache = {}

    async def fake_lookup(callsign, *, retry_session=True):
        return {
            "success": False,
            "message": f"Not found: {callsign}",
            "error_type": "not_found",
            "retryable": False,
        }

    monkeypatch.setattr(client, "_lookup_profile_internal", fake_lookup)

    result = asyncio.run(client.get_profile_picture("A61DI"))

    assert result["success"] is False
    assert result["error_type"] == "not_found"
    assert result["message"] == "Callsign not found (tried: A61DI)"
