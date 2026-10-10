"""Native station-widget window lifecycle checks."""

from types import SimpleNamespace

import scripts.launch.launch_windows as launcher


class FakeEvent:
    def __init__(self):
        self.handler = None
        self.closed = False

    def __iadd__(self, handler):
        self.handler = handler
        return self

    def is_set(self):
        return self.closed

    def fire(self, window):
        self.closed = True
        self.handler(window=window)


class FakeWindow:
    def __init__(self):
        self.events = SimpleNamespace(closed=FakeEvent())
        self.restore_calls = 0
        self.show_calls = 0

    def restore(self):
        self.restore_calls += 1

    def show(self):
        self.show_calls += 1

    def evaluate_js(self, _source):
        return None


def test_closed_station_widget_is_created_again(monkeypatch):
    created = []

    def create_window(_config, **_kwargs):
        window = FakeWindow()
        created.append(window)
        return window

    monkeypatch.setattr(launcher, "create_managed_window", create_window)
    api = launcher.DesktopApi()

    first = api.open_station_widget("vertical", 430, 690)
    assert first == {"success": True, "reused": False, "native": True}
    assert api._station_widget_window is created[0]

    created[0].events.closed.fire(created[0])
    assert api._station_widget_window is None

    second = api.open_station_widget("vertical", 430, 690)
    assert second == {"success": True, "reused": False, "native": True}
    assert len(created) == 2
    assert api._station_widget_window is created[1]


def test_open_station_widget_reuses_a_live_native_window(monkeypatch):
    created = []

    def create_window(_config, **_kwargs):
        window = FakeWindow()
        created.append(window)
        return window

    monkeypatch.setattr(launcher, "create_managed_window", create_window)
    api = launcher.DesktopApi()

    api.open_station_widget("horizontal", 1120, 250)
    reused = api.open_station_widget("horizontal", 1120, 250)

    assert reused == {"success": True, "reused": True, "native": True}
    assert len(created) == 1
    assert created[0].restore_calls == 1
    assert created[0].show_calls == 1
