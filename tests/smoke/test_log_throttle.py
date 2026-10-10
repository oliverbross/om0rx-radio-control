from radio_control import log_throttle


class _Logger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args):
        self.messages.append(message % args)


def test_first_warning_emits_even_near_monotonic_origin(monkeypatch):
    logger = _Logger()
    log_throttle._LAST.clear()
    monkeypatch.setattr(log_throttle.time, "monotonic", lambda: 1.0)
    assert log_throttle.warning(logger, "same", 300, "failure: %s", "one") is True
    assert log_throttle.warning(logger, "same", 300, "failure: %s", "one") is False
    assert logger.messages == ["failure: one"]


def test_changed_failure_key_emits_immediately(monkeypatch):
    logger = _Logger()
    log_throttle._LAST.clear()
    monkeypatch.setattr(log_throttle.time, "monotonic", lambda: 10.0)
    assert log_throttle.warning(logger, "feed:Timeout:a", 300, "a") is True
    assert log_throttle.warning(logger, "feed:ValueError:b", 300, "b") is True
    assert logger.messages == ["a", "b"]
