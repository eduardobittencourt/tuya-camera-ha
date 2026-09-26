import sys
from pathlib import Path
from types import ModuleType

package = ModuleType("custom_components.tuya_camera_bridge")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "tuya_camera_bridge")
]
sys.modules["custom_components.tuya_camera_bridge"] = package

from custom_components.tuya_camera_bridge.payload import (  # noqa: E402
    bridge_config_filename,
    build_bridge_config,
    sanitize_rtsp_path,
    write_bridge_config_file,
)


def test_bridge_config_filename_is_entry_scoped():
    assert bridge_config_filename("abc") == "tuya_camera_bridge_abc.json"


def test_rtsp_path_matches_go_bridge_contract():
    assert sanitize_rtsp_path("Kitchen camera", "device") == "Kitchen_camera"
    assert sanitize_rtsp_path("/", "device") == "device"


def test_bridge_config_is_owner_only(tmp_path: Path):
    path = tmp_path / "bridge.json"
    write_bridge_config_file(path, {"sid": "test"})
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text() == '{"sid":"test"}'


def test_bridge_config_replaces_an_existing_file_atomically(tmp_path: Path):
    path = tmp_path / "bridge.json"
    path.write_text("old")
    write_bridge_config_file(path, {"sid": "new"})
    assert path.read_text() == '{"sid":"new"}'
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_bridge_config_carries_the_selected_mobile_app_profile():
    config = build_bridge_config(
        {
            "application": "tuya_smart",
            "sid": "sid",
            "ecode": "ecode",
            "partner_identity": "partner",
            "phone_device_id": "phone",
            "api_host": "a1.tuyaus.com",
            "camera_id": "camera",
            "camera_name": "Kitchen",
            "product_id": "product",
        }
    )
    assert config["package_name"] == "com.tuya.smart"
    assert config["app_version"] == "7.8.6"
    assert config["sdk_version"] == "5.24.0"
    assert config["ttid"] == "international"
    assert config["cameras"] == [
        {
            "camera_id": "camera",
            "camera_name": "Kitchen",
            "product_id": "product",
        }
    ]
