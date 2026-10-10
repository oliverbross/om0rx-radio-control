"""Suite-wide isolation for operator-owned digital-engine state.

Most smoke tests exercise the legacy OM0RX planner/WSJT-Z adapter.  They must
not inherit whichever provider the operator has selected in the live station
settings.  Individual lifecycle tests remain free to replace this temporary
state path with their own fixture.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_digital_provider(tmp_path, monkeypatch):
    """Give every smoke test an explicit, disposable WSJT-Z provider state."""
    import services.digital_engine as digital_engine

    state_path = tmp_path / "digital_engine.json"
    digital_engine.atomic_write_json(state_path, {"provider": "wsjtz"})
    monkeypatch.setattr(digital_engine, "STATE_PATH", state_path)
