from __future__ import annotations

import copy
from typing import Any
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import event_message
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.exceptions import HomeAssistantError

from .schema import SWITCH_MANAGER_CONFIG_SCHEMA
from .helpers import _get_blueprint, _get_switch_config, _remove_switch_config, _set_switch_config
from .const import DOMAIN, CONF_BLUEPRINTS, CONF_MANAGED_SWITCHES, CONF_STORE
from .models import ManagedSwitchConfig, reconcile_buttons_with_blueprint, async_discover_zigbee2mqtt_instances, async_validate_buttons_config

def _get_switch_or_error( hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict, config_id ):
    """Return the switch or answer with not_found.

    A panel left open on a switch that was deleted meanwhile (other tab, reload)
    used to crash the handler with an AttributeError instead of telling the user.
    """
    config = _get_switch_config( hass, str(config_id) ) if config_id is not None else None
    if config is None:
        connection.send_error( msg['id'], websocket_api.ERR_NOT_FOUND, f"Switch {config_id} does not exist" )
    return config

async def async_setup_connections( hass ):
  
    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/blueprints", 
        vol.Optional("blueprint_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_blueprints(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        data = ({ "blueprint": _get_blueprint(hass, msg['blueprint_id'] ) } 
                if msg.get('blueprint_id')
                else { "blueprints": hass.data[DOMAIN].get(CONF_BLUEPRINTS) })

        connection.send_result( msg["id"], data )

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/blueprints/auto_discovery", 
        vol.Optional("blueprint_id"): cv.string,
        # Zigbee2MQTT base topics to listen on instead of the blueprint default
        vol.Optional("base_topics"): [cv.string]
    })
    @websocket_api.async_response
    async def websocket_blueprint_auto_discovery(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        blueprint = _get_blueprint(hass, msg.get('blueprint_id'))
        if isinstance(blueprint, str) or blueprint is None:
            connection.send_error( msg['id'], websocket_api.ERR_NOT_FOUND, f"Blueprint {msg.get('blueprint_id')} is not loaded" )
            return

        @callback
        def send( data ):
            connection.send_message(event_message(msg["id"], data))

        discovery_listener = await blueprint.start_discovery(send, msg.get('base_topics'))
        if not discovery_listener:
            # Nothing to discover (MQTT blueprint without topic format), still answer
            # so the panel doesn't wait forever
            connection.send_result(msg["id"])
            return

        @callback
        def close_connection():
            discovery_listener()
        
        connection.subscriptions[msg["id"]] = close_connection
        connection.send_result(msg["id"])

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/zigbee2mqtt/instances"
    })
    @websocket_api.async_response
    async def websocket_zigbee2mqtt_instances(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """List the base topics of all Zigbee2MQTT instances seen on the broker."""
        instances = await async_discover_zigbee2mqtt_instances(hass)
        connection.send_result(msg["id"], { "instances": instances })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/configs", 
        vol.Optional("config_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_configs(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        if msg.get('config_id'):
            config = _get_switch_or_error( hass, connection, msg, msg['config_id'] )
            if config is None:
                return
            data = { "config": config }
        else:
            data = { "configs": hass.data[DOMAIN].get(CONF_MANAGED_SWITCHES) }

        connection.send_result( msg["id"], data )

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/config/monitor", 
        vol.Optional("config_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_monitor_config(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        config = _get_switch_or_error( hass, connection, msg, msg.get('config_id') )
        if config is None:
            return

        @callback
        def send( data ):
            connection.send_message(event_message(msg["id"], data))

        config_listener = config.add_listener(send)

        @callback
        def close_connection():
            config_listener()
        
        connection.subscriptions[msg["id"]] = close_connection
        connection.send_result(msg["id"])

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/config/save", 
        vol.Required('config'): SWITCH_MANAGER_CONFIG_SCHEMA,
        vol.Optional('fix_mismatch', default=False): bool
    })
    @websocket_api.async_response
    async def websocket_save_config(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        config: ManagedSwitchConfig
        store = hass.data[DOMAIN][CONF_STORE]

        config_id = msg['config'].get('id')
        is_new = config_id is None or config_id == ''
        existing = None
        if not is_new:
            existing = _get_switch_or_error( hass, connection, msg, config_id )
            if existing is None:
                return

        buttons = msg['config'].get('buttons')
        blueprint = existing.blueprint if existing else _get_blueprint( hass, msg['config']['blueprint'] )
        if existing and msg['fix_mismatch'] and existing.valid_blueprint:
            buttons = reconcile_buttons_with_blueprint( existing.blueprint, buttons )
        try:
            await async_validate_buttons_config( hass, blueprint, buttons )
        except vol.Invalid as err:
            connection.send_error( msg['id'], websocket_api.ERR_INVALID_FORMAT, str(err) )
            return

        if not is_new:
            config = existing
            if msg['fix_mismatch']:
                if not config.valid_blueprint:
                    connection.send_error( 
                        msg['id'], 
                        'blueprint_not_loaded', 
                        f"Blueprint {config.blueprint} is not loaded, check the logs" 
                    )
                    return
                # The panel sends the config as it is stored, so the buttons still carry
                # the layout of the blueprint they were created with. Reshaping them here
                # keeps the fix working no matter which panel version asked for it.
                msg['config']['buttons'] = reconcile_buttons_with_blueprint( 
                    config.blueprint, 
                    msg['config'].get('buttons') 
                )
                config.setBlueprint( config.blueprint, msg['config']['buttons'] )
                ir.async_delete_issue(hass, DOMAIN, f"switch_{config.id}_mismatch")
            config.update( msg['config'] )
            await config.start()
        else:
            config = ManagedSwitchConfig( 
                hass, 
                _get_blueprint( hass, msg['config']['blueprint'] ), 
                store.get_available_id(), 
                msg['config'] 
            )
            await _set_switch_config( hass, config )

        await store.set_managed_switch( config )    
        
        connection.send_result( msg['id'], {
            "config_id": config.id,
            "config": config
        })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/config/enabled", 
        vol.Required("config_id"): cv.string,
        vol.Required("enabled"): bool
    })
    @websocket_api.async_response
    async def websocket_toggle_config_enabled(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        store = hass.data[DOMAIN][CONF_STORE]

        config = _get_switch_or_error( hass, connection, msg, msg['config_id'] )
        if config is None:
            return
        config.setEnabled( msg['enabled'] )
        await config.start()

        await store.set_managed_switch( config )

        connection.send_result(msg['id'], {
            "switch_id": config.id,
            "enabled": msg['enabled']
        })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/config/delete", 
        vol.Required("config_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_delete_config(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        store = hass.data[DOMAIN][CONF_STORE]

        if _get_switch_or_error( hass, connection, msg, msg.get('config_id') ) is None:
            return
        await _remove_switch_config( hass, msg['config_id'] )    
        await store.delete_managed_switch( msg['config_id'] )

        ir.async_delete_issue(hass, DOMAIN, f"switch_{msg['config_id']}_mismatch")

        connection.send_result( msg['id'], {
            "deleted": msg['config_id']
        })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/config/duplicate",
        vol.Required("config_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_duplicate_config(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        store = hass.data[DOMAIN][CONF_STORE]
        source = _get_switch_or_error( hass, connection, msg, msg['config_id'] )
        if source is None:
            return

        # Serialize buttons to plain dicts (detached, the copy must not share
        # sequences with its source)
        if source.valid_blueprint:
            buttons = [
                { 'actions': [ copy.deepcopy(action.as_dict()) for action in button.actions ] }
                for button in source.buttons
            ]
        else:
            buttons = copy.deepcopy(source.buttons_config)

        config_data = {
            'name': f"{source.name} (Copy)",
            'identifier': '',
            'blueprint': source.blueprint.id if source.valid_blueprint else source.blueprint,
            'enabled': True,
            'variables': copy.deepcopy(source.saved_variables) if source.saved_variables else None,
            'rotate': source.rotate,
            'buttons': buttons,
        }

        blueprint = _get_blueprint(hass, config_data['blueprint'])
        new_config = ManagedSwitchConfig(
            hass, blueprint, store.get_available_id(), config_data
        )
        await _set_switch_config(hass, new_config)
        await store.set_managed_switch(new_config)

        connection.send_result(msg['id'], {
            "config_id": new_config.id
        })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/copy_from_list",
        vol.Required("blueprint_id"): cv.string,
        vol.Optional("skip_config_id"): cv.string
    })
    @websocket_api.async_response
    async def websocket_copy_from_list(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        if 'skip_config_id' not in msg:
            msg['skip_config_id'] = '';
        # Switches whose blueprint failed to load only carry its id as a string
        data = [s for s in hass.data[DOMAIN][CONF_MANAGED_SWITCHES].values() if s.valid_blueprint and s.blueprint.id == msg['blueprint_id'] and s.id != msg['skip_config_id']];

        connection.send_result( msg['id'], {
            "switches": data
        })

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required("type"): "switch_manager/run_action",
        vol.Required("action"): dict,
    })
    @websocket_api.async_response
    async def websocket_run_action(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        action_data = dict(msg["action"])
        action_data.pop("metadata", None)
        try:
            sequence = await async_validate_actions_config(hass, cv.SCRIPT_SCHEMA(action_data))
        except (vol.Invalid, HomeAssistantError) as err:
            connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
            return
        script_obj = Script(hass, sequence, "Switch Manager Run Action", DOMAIN)
        try:
            await script_obj.async_run(context=connection.context(msg))
        except Exception as err:
            connection.send_error(msg["id"], "action_failed", str(err))
            return
        finally:
            # A throwaway script per click, release it (required from HA 2026.5)
            if hasattr(script_obj, 'async_unload'):
                await script_obj.async_unload()
        connection.send_result(msg["id"])

    websocket_api.async_register_command(hass, websocket_run_action)
    websocket_api.async_register_command(hass, websocket_configs)
    websocket_api.async_register_command(hass, websocket_blueprints)
    websocket_api.async_register_command(hass, websocket_blueprint_auto_discovery)
    websocket_api.async_register_command(hass, websocket_zigbee2mqtt_instances)
    websocket_api.async_register_command(hass, websocket_monitor_config)
    websocket_api.async_register_command(hass, websocket_save_config)
    websocket_api.async_register_command(hass, websocket_toggle_config_enabled)
    websocket_api.async_register_command(hass, websocket_delete_config)
    websocket_api.async_register_command(hass, websocket_duplicate_config)
    websocket_api.async_register_command(hass, websocket_copy_from_list)