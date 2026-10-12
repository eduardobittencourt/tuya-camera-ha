import asyncio
import json
from unittest.mock import AsyncMock

from custom_components.tuya_camera_bridge.api import CameraInfo, TuyaCameraApi


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


async def test_lan_bootstrap_uses_exact_device_and_product_without_cloud_states():
    client = AsyncMock()
    client._call.side_effect = [
        {"result": {"devId": "camera", "localKey": "test-lan-key1234", "mac": "aa:bb",
                    "dataPointInfo": {"dps": {"108": "2"}}, "secKey": "not-for-HA"}},
        {"result": [{"id": "other", "schemaInfo": {"schema": json.dumps([
            {"id": 105, "code": "basic_private", "mode": "rw", "property": {"type": "bool"}},
        ])}}, {"id": "product", "schemaInfo": {"schema": json.dumps([
            {"id": 108, "code": "basic_nightvision", "mode": "rw", "property": {"type": "enum"}},
        ])}}]},
    ]
    result = await TuyaCameraApi(None).async_local_config(client, CameraInfo("camera", "Camera", "product"))
    assert result == {"local_key": "test-lan-key1234", "mac": "aa:bb", "schema": [
        {"id": 108, "code": "basic_nightvision", "mode": "rw", "property": {"type": "enum"}},
    ]}
    assert "dps" not in result and "secKey" not in result
    assert "test-lan-key1234" not in repr(CameraInfo("camera", "Camera", local_config=result))


async def test_lan_bootstrap_failure_preserves_stream_only_setup():
    client = AsyncMock()
    client._call.side_effect = RuntimeError("private-response")
    assert await TuyaCameraApi(None).async_local_config(client, CameraInfo("camera", "Camera")) is None
