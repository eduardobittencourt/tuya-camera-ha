"""Numeric camera controls with schema-derived limits, scale and step."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CAMERAS
from .entity import NUMBERS, LocalEntity, supported


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        CameraNumber(entry, camera, code, name)
        for camera in entry.data[CONF_CAMERAS]
        for code, name in NUMBERS.items()
        if supported(entry.runtime_data.local_cameras[camera["camera_id"]], code, "value", writable=True)
    ])


class CameraNumber(LocalEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, entry, camera, code, name):
        super().__init__(entry, camera, code, name)
        prop = self.local.schema[code]["property"]
        self._factor = 10 ** prop.get("scale", 0)
        self._attr_native_min_value = prop["min"] / self._factor
        self._attr_native_max_value = prop["max"] / self._factor
        self._attr_native_step = prop.get("step", 1) / self._factor
        self._attr_native_unit_of_measurement = prop.get("unit") or None

    @property
    def native_value(self) -> float | None:
        value = self.local.values.get(self.code)
        return value / self._factor if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    async def async_set_native_value(self, value: float) -> None:
        raw = value * self._factor
        if abs(raw - round(raw)) > 1e-6:
            raise HomeAssistantError("Invalid camera value")
        await self.local.write(self.code, round(raw))
