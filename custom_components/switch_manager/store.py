from __future__ import annotations

from .const import LOGGER
from .models import ManagedSwitchConfig
import attr
import copy

from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_ID = "switch_manager"


@attr.s
class SwitchManagerManagedSwitchData:
    name = attr.ib(type=str, default='')
    enabled = attr.ib(type=bool, default=True)
    blueprint = attr.ib(type=str, default=None)
    identifier = attr.ib(type=str, default=None)
    variables = attr.ib(type=dict, default=None)
    rotate = attr.ib(type=int, default=0)
    buttons = attr.ib(type=list, default=[])

    def set_from_managed_switch_config( self, config: ManagedSwitchConfig ):
        # Take a detached copy of the persisted fields only. Keeping references to the
        # live objects meant later changes (variables merged by set_variables, runtime
        # state) were written out whenever any other switch got saved.
        self.name = config.name
        self.enabled = config.enabled
        self.blueprint = config.blueprint.id if config.valid_blueprint else config.blueprint
        self.identifier = config.identifier
        self.variables = copy.deepcopy(config.saved_variables)
        self.rotate = config.rotate
        if config.valid_blueprint:
            self.buttons = [
                { 'actions': [ copy.deepcopy(action.as_dict()) for action in button.actions ] }
                for button in config.buttons
            ]
        else:
            # Nothing was built without a blueprint, store what was loaded unchanged
            self.buttons = copy.deepcopy(config.buttons_config)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def asdict(self):
        return attr.asdict(self)


@attr.s
class SwitchManagerStoreData:
    version = attr.ib(type=str, default="0")
    managed_switches = attr.ib(type=dict, factory=dict)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def asdict(self):
        return attr.asdict(self)

class SwitchManagerStore:
    
    def __init__(self, hass):
        self.store = Store(hass, STORAGE_VERSION, STORAGE_ID)
        
        self.data = None
        self.dirty = False

    async def save(self):
        await self.store.async_save(attr.asdict(self.data))

    async def load(self):
        stored = await self.store.async_load()
        if stored:
            self.data = SwitchManagerStoreData.from_dict(stored)
            
        # We assume either the stored data was deleteed or is a new install
        if self.data is None:
            self.data = SwitchManagerStoreData()
            await self.save()
        self.dirty = False

    async def updated(self):
        self.dirty = True
        await self.save()

    async def get_managed_switches(self):
        return self.data.managed_switches

    def compare_version(self, version):
        return self.data.version == str(version)

    async def update_version(self, version):
        self.data.version = str(version)
        await self.updated()

    async def delete_managed_switch(self, _id: str):
        del self.data.managed_switches[_id]
        await self.updated()

    def asdict(self):
        return self.data.asdict()

    def get_available_id( self ) -> str:
        ids = [ int(_id) for _id in self.data.managed_switches if str(_id).isdigit() ]
        return str( max(ids) + 1 ) if ids else '0'
            
    async def set_managed_switch( self, config_data: ManagedSwitchConfig ):        
        config = SwitchManagerManagedSwitchData()
        config.set_from_managed_switch_config( config_data )

        self.data.managed_switches[config_data.id] = config
        await self.updated()
        