"""Regression tests for the bugs fixed in this clone."""
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events, async_mock_service

from homeassistant.core import HomeAssistant, State

from custom_components.switch_manager import async_unload_entry, async_setup_entry
from custom_components.switch_manager.const import DOMAIN, CONF_MANAGED_SWITCHES, CONF_STORE
from custom_components.switch_manager.models import format_event_entity_state

FIRED = "switch_manager_test_fired"


def _switch(blueprint="test-remote", **kwargs):
    data = {
        "name": "Hallway",
        "enabled": True,
        "blueprint": blueprint,
        "identifier": "remote_1",
        "variables": {"level": 1},
        "rotate": 0,
        "buttons": [{"actions": [{"mode": "single", "sequence": [{"event": FIRED}]}]}],
    }
    data.update(kwargs)
    return data


async def _press(hass: HomeAssistant):
    hass.bus.async_fire("switch_manager_test_event", {"device": "remote_1", "command": "press"})
    await hass.async_block_till_done()


@pytest.mark.parametrize("stored_switches", [{"0": _switch()}])
async def test_switch_runs_action(hass: HomeAssistant, setup_integration):
    fired = async_capture_events(hass, FIRED)
    await _press(hass)
    assert len(fired) == 1


@pytest.mark.parametrize("stored_switches", [{"0": _switch()}])
async def test_switches_survive_entry_reload(hass: HomeAssistant, setup_integration):
    """Reloading the integration used to leave every switch unloaded."""
    fired = async_capture_events(hass, FIRED)
    assert await async_unload_entry(hass, setup_integration)
    with (
        patch("custom_components.switch_manager.async_setup_view"),
        patch("custom_components.switch_manager.async_bind_blueprint_images"),
    ):
        assert await async_setup_entry(hass, setup_integration)
    await hass.async_block_till_done()
    await _press(hass)
    assert len(fired) == 1


@pytest.mark.parametrize("stored_switches", [{"0": _switch(), "1": _switch(name="Kitchen", identifier="remote_2")}])
async def test_set_variables_not_persisted_by_other_switch(hass: HomeAssistant, setup_integration, hass_storage):
    await hass.services.async_call(DOMAIN, "set_variables", {"switch_id": "0", "variables": {"level": 99}}, blocking=True)
    store = hass.data[DOMAIN][CONF_STORE]
    # Saving a different switch writes the whole store
    await store.set_managed_switch(hass.data[DOMAIN][CONF_MANAGED_SWITCHES]["1"])
    await hass.async_block_till_done()
    assert store.asdict()["managed_switches"]["0"]["variables"] == {"level": 1}
    # The running switch still sees the temporary value
    assert hass.data[DOMAIN][CONF_MANAGED_SWITCHES]["0"].variables == {"level": 99}


@pytest.mark.parametrize("stored_switches", [{"0": _switch(blueprint="missing-blueprint")}])
async def test_toggling_switch_without_blueprint_keeps_buttons(hass: HomeAssistant, setup_integration, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "switch_manager/config/enabled", "config_id": "0", "enabled": False})
    assert (await client.receive_json())["success"]
    stored = hass.data[DOMAIN][CONF_STORE].asdict()["managed_switches"]["0"]
    assert stored["buttons"] == _switch()["buttons"]
    assert stored["blueprint"] == "missing-blueprint"


@pytest.mark.parametrize("stored_switches", [{"0": _switch(), "5": _switch(), "2": _switch()}])
async def test_available_id_uses_highest(hass: HomeAssistant, setup_integration):
    assert hass.data[DOMAIN][CONF_STORE].get_available_id() == "6"


async def test_save_rejects_invalid_sequence(hass: HomeAssistant, setup_integration, hass_ws_client):
    client = await hass_ws_client(hass)
    config = _switch()
    config["buttons"] = [{"actions": [{"mode": "single", "sequence": [{"not_an_action": 1}]}]}]
    await client.send_json_auto_id({"type": "switch_manager/config/save", "config": config})
    msg = await client.receive_json()
    assert not msg["success"]
    assert 'Button 1, action "press"' in msg["error"]["message"]
    assert hass.data[DOMAIN][CONF_MANAGED_SWITCHES] == {}


async def test_save_new_switch(hass: HomeAssistant, setup_integration, hass_ws_client):
    client = await hass_ws_client(hass)
    config = _switch()
    # Shape the HA action editor produces, including its metadata key
    config["buttons"][0]["actions"][0]["sequence"].append(
        {"action": "test.dummy", "metadata": {}, "data": {}, "target": {"entity_id": "light.hallway"}}
    )
    calls = async_mock_service(hass, "test", "dummy")
    await client.send_json_auto_id({"type": "switch_manager/config/save", "config": config})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["config_id"] == "0"
    await hass.async_block_till_done()
    fired = async_capture_events(hass, FIRED)
    await _press(hass)
    assert len(fired) == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    "command",
    [
        {"type": "switch_manager/config/enabled", "config_id": "42", "enabled": True},
        {"type": "switch_manager/config/delete", "config_id": "42"},
        {"type": "switch_manager/config/duplicate", "config_id": "42"},
        {"type": "switch_manager/configs", "config_id": "42"},
        {"type": "switch_manager/config/monitor", "config_id": "42"},
        {"type": "switch_manager/config/save", "config": {**_switch(), "id": "42"}},
    ],
)
async def test_unknown_switch_returns_not_found(hass: HomeAssistant, setup_integration, hass_ws_client, command):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(command)
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


@pytest.mark.parametrize("stored_switches", [{"0": _switch(blueprint="missing-blueprint")}])
async def test_copy_from_list_with_unloaded_blueprint(hass: HomeAssistant, setup_integration, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "switch_manager/copy_from_list", "blueprint_id": "test-remote"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["switches"] == []


async def test_event_entity_attribute_only_change_is_not_a_press(hass: HomeAssistant):
    attrs = {"event_type": "initial_press", "event_types": ["initial_press"]}
    old = State("event.remote_button_1", "2026-10-21T10:00:00.000+00:00", attrs)
    renamed = State("event.remote_button_1", "2026-10-21T10:00:00.000+00:00", {**attrs, "friendly_name": "New"})
    pressed = State("event.remote_button_1", "2026-10-21T10:00:05.000+00:00", attrs)

    class _Event:
        def __init__(self, old_state, new_state):
            self.data = {"old_state": old_state, "new_state": new_state}

    assert format_event_entity_state(hass, _Event(old, renamed)) is None
    assert format_event_entity_state(hass, _Event(old, pressed)) is not None
