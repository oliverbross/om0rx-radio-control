import base64
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import _bootstrap  # noqa: F401

from backend.core.security import authorize_control
from radio_control.settings_store import SECRET_KEYS, public_config_from_module


def test_local_same_origin_request_is_allowed():
    allowed, reason = authorize_control(
        {"host": "127.0.0.1:8080", "origin": "http://127.0.0.1:8080"},
        "127.0.0.1",
        "POST",
    )
    assert allowed is True
    assert reason == ""


def test_remote_command_is_denied_by_default():
    allowed, reason = authorize_control(
        {"host": "station.example", "origin": "https://station.example"},
        "192.0.2.10",
        "POST",
    )
    assert allowed is False
    assert "disabled" in reason.lower()


def test_cross_origin_local_command_is_denied():
    allowed, reason = authorize_control(
        {"host": "127.0.0.1:8080", "origin": "https://attacker.example"},
        "127.0.0.1",
        "POST",
    )
    assert allowed is False
    assert "origin" in reason.lower()


def test_public_config_never_contains_secret_values():
    values = {key: f"secret-{key}" for key in SECRET_KEYS}
    values["BACKEND_PORT"] = 8080
    public = public_config_from_module(SimpleNamespace(**values))
    for key in SECRET_KEYS:
        assert key not in public
        assert public[f"{key}_CONFIGURED"] is True
    serialized = repr(public)
    assert "secret-" not in serialized


def test_csp_does_not_allow_arbitrary_inline_scripts():
    from fastapi.testclient import TestClient
    from backend.main import app

    response = TestClient(app).get("/spots-database.html")
    csp = response.headers["content-security-policy"]
    script_policy = csp.split("script-src", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in script_policy

    page = (Path(__file__).parents[2] / "frontend" / "spots-database.html").read_text(encoding="utf-8")
    inline_script = re.search(r"<script>([\s\S]*?)</script>\s*</body>", page).group(1)
    digest = base64.b64encode(hashlib.sha256(inline_script.encode("utf-8")).digest()).decode("ascii")
    assert f"'sha256-{digest}'" in script_policy
