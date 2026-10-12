"""Only expose enum choices declared by the camera's schema."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CAMERAS
from .entity import SELECTS, LocalEntity, supported


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        CameraSelect(entry, camera, code, name)
        for camera in entry.data[CONF_CAMERAS]
        for code, (name, _) in SELECTS.items()
        if supported(entry.runtime_data.local_cameras[camera["camera_id"]], code, "enum", writable=True)
    ])


class CameraSelect(LocalEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry, camera, code, name):
        super().__init__(entry, camera, code, name)
        labels = SELECTS[code][1]
        self._choices = {str(value): labels.get(str(value), str(value))
                         for value in self.local.schema[code]["property"].get("range", [])}
        self._attr_options = list(self._choices.values())

    @property
    def current_option(self) -> str | None:
        return self._choices.get(str(self.local.values.get(self.code)))

    async def async_select_option(self, option: str) -> None:
        value = next((value for value, label in self._choices.items() if label == option), None)
        if value is None:
            raise HomeAssistantError("Invalid camera option")
        await self.local.write(self.code, value)
