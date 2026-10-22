"""Read camera telemetry from the local DP connection."""
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CAMERAS
from .entity import SENSORS, LocalEntity, async_setup_confirmed_entities


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_confirmed_entities(hass, entry, async_add_entities, "sensor", [
        CameraSensor(entry, camera, code, name)
        for camera in entry.data[CONF_CAMERAS]
        for code, name in SENSORS.items()
        if entry.runtime_data.local_cameras[camera["camera_id"]].schema.get(code, {}).get("property", {}).get("type")
        in ("value", "enum")
    ])


class CameraSensor(LocalEntity, RestoreSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry, camera, code, name):
        super().__init__(entry, camera, code, name)
        prop = self.local.schema[code]["property"]
        self._factor = 10 ** prop.get("scale", 0)
        self._attr_native_unit_of_measurement = prop.get("unit") or None
        if code == "wireless_electricity":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        value = self.local.values.get(self.code)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value / self._factor
        return value

    def restored_value(self, value: str):
        if self.local.schema[self.code]["property"]["type"] == "enum":
            return value
        return float(value) * self._factor
