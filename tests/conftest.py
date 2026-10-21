"""Fixtures for Switch Manager tests."""
import os
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.switch_manager import async_setup, async_setup_entry
from custom_components.switch_manager.const import DOMAIN

TEST_BLUEPRINT = """
name: Test Remote
service: Test
event_type: switch_manager_test_event
identifier_key: device
buttons:
  - actions:
      - title: press
        conditions:
          - key: command
            value: press
"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def stored_switches():
    """Switches present in .storage/switch_manager before setup."""
    return {}


@pytest.fixture
async def setup_integration(hass: HomeAssistant, hass_storage, stored_switches, tmp_path):
    """Set up Switch Manager with a test blueprint, without the frontend panel."""
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "blueprints" / DOMAIN
    folder.mkdir(parents=True)
    (folder / "test-remote.yaml").write_text(TEST_BLUEPRINT)

    hass_storage[DOMAIN] = {
        "version": 1,
        "key": DOMAIN,
        "data": {"version": "0", "managed_switches": stored_switches},
    }

    assert await async_setup_component(hass, "websocket_api", {})
    with (
        patch("custom_components.switch_manager.deploy_blueprints"),
        patch("custom_components.switch_manager.async_setup_view"),
        patch("custom_components.switch_manager.async_bind_blueprint_images"),
    ):
        assert await async_setup(hass, {})
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        assert await async_setup_entry(hass, entry)
        await hass.async_block_till_done()
        yield entry
