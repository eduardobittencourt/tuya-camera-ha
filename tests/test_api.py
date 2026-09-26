import asyncio
import sys
from pathlib import Path
from types import ModuleType

package = ModuleType("custom_components.tuya_camera_bridge")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "tuya_camera_bridge")
]
sys.modules["custom_components.tuya_camera_bridge"] = package

from custom_components.tuya_camera_bridge.api import TuyaCameraApi  # noqa: E402


class FakeClient:
    async def _call(self, action, payload, version=None):
        if action == "m.life.home.space.list":
            return {"result": [{"gid": 123}]}
        if action == "m.life.my.group.device.list":
            assert payload == {"gid": "123"}
            assert version == "2.2"
            return {
                "result": [
                    {
                        "deviceId": "camera-1",
                        "deviceName": "Kitchen",
                        "productId": "camera-product",
                    },
                    {
                        "devId": "camera-2",
                        "name": "Doorbell",
                    },
                    {
                        "deviceId": "light-1",
                        "deviceName": "Hall light",
                    },
                ]
            }
        assert action == "smartlife.m.rtc.config.get"
        if payload["devId"].startswith("camera-"):
            return {"success": True, "result": {"skill": "video"}}
        return {"success": False, "errorCode": "NOT_SUPPORTED"}


def test_discovery_returns_only_camera_categories():
    api = TuyaCameraApi(None)
    cameras = asyncio.run(api._async_discover_devices(FakeClient()))
    assert [(camera.device_id, camera.name) for camera in cameras] == [
        ("camera-2", "Doorbell"),
        ("camera-1", "Kitchen"),
    ]
