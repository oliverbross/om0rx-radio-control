"""Regression checks for the Windows/Python PortAudio safety latch."""

import _bootstrap  # noqa: F401

import services.sounddevice_loader as loader


def test_windows_python_314_skips_sounddevice_probe_without_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(loader, "_checked", False)
    monkeypatch.setattr(loader, "_module", None)
    monkeypatch.setattr(loader, "_reason", "not checked")
    monkeypatch.setattr(loader, "_unsafe_windows_runtime", lambda: True)
    monkeypatch.delenv("FT8_DISABLE_SOUNDDEVICE", raising=False)
    monkeypatch.delenv("FT8_ENABLE_SOUNDDEVICE_PROBE", raising=False)
    monkeypatch.setattr(
        loader.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PortAudio child probe must not run by default")
        ),
    )

    assert loader.get_sounddevice() is None
    assert "skipped on Windows with Python 3.14+" in loader.sounddevice_unavailable_reason()
