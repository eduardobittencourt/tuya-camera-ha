"""LAN connectivity and fresh detection events, without cloud polling."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CAMERAS
from .entity import LocalEntity


async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    for camera in entry.data[CONF_CAMERAS]:
        local = entry.runtime_data.local_cameras[camera["camera_id"]]
        entities.append(CameraBinarySensor(entry, camera, "lan_connection", "LAN connection"))
        for code, name in (("movement_detect_pic", "Motion"), ("decibel_upload", "Sound")):
            if code in local.schema:
                entities.append(CameraBinarySensor(entry, camera, code, name))
    async_add_entities(entities)


class CameraBinarySensor(LocalEntity, BinarySensorEntity):
    def __init__(self, entry, camera, code, name):
        super().__init__(entry, camera, code, name)
        if code == "lan_connection":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif code == "movement_detect_pic":
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        else:
            self._attr_device_class = BinarySensorDeviceClass.SOUND

    @property
    def available(self) -> bool:
        return self.code == "lan_connection" or self.local.connected

    @property
    def is_on(self) -> bool:
        if self.code == "lan_connection":
            return self.local.connected
        return self.local.motion if self.code == "movement_detect_pic" else self.local.sound

    @property
    def extra_state_attributes(self) -> dict:
        return {"transport": "lan", "connection_status": self.local.status}
