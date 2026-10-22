"""Camera switches, written and confirmed exclusively over LAN."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CAMERAS
from .entity import SWITCHES, LocalEntity, async_setup_confirmed_entities, supported


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_confirmed_entities(hass, entry, async_add_entities, "switch", [
        CameraSwitch(entry, camera, code, name)
        for camera in entry.data[CONF_CAMERAS]
        for code, name in SWITCHES.items()
        if supported(entry.runtime_data.local_cameras[camera["camera_id"]], code, "bool", writable=True)
    ])


class CameraSwitch(LocalEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool | None:
        value = self.local.values.get(self.code)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.local.write(self.code, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.local.write(self.code, False)

    def restored_value(self, value: str):
        return {"on": True, "off": False}.get(value)
