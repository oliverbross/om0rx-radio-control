#!/usr/bin/env python3
"""Smoke checks for explicit service dependency state."""

from types import SimpleNamespace

import _bootstrap  # noqa: F401

from services import background_tasks, radio


async def noop_status(_payload):
    return None


async def noop_spots(_spots):
    return None


def test_radio_control_dependency_state():
    sentinel_radio = object()
    original_flex = radio.radio_control_state.flex
    original_broadcast = radio.radio_control_state.broadcast_func
    try:
        state = radio.configure_radio_control(sentinel_radio, noop_status)

        assert state is radio.radio_control_state
        assert radio.get_radio_instance() is sentinel_radio
        assert radio.radio_control_state.broadcast_func is noop_status
    finally:
        radio.radio_control_state.flex = original_flex
        radio.radio_control_state.broadcast_func = original_broadcast


def test_background_task_dependency_state():
    context = SimpleNamespace(
        flex=None,
        dx_spots_cache=[],
        cluster_client=None,
        cluster_connected=False,
        cty_resolver=None,
        classifier=None,
        wavelog_sync_manager=None,
        sync_status={},
    )
    service = background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    status = background_tasks.get_background_task_status()

    assert background_tasks.get_background_task_service() is service
    assert service.context is context
    assert status["total_tasks"] == 0
    assert status["running_tasks"] == 0


if __name__ == "__main__":
    test_radio_control_dependency_state()
    test_background_task_dependency_state()
    print("Service dependency state smoke checks passed")
