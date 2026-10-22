from custom_components.tuya_camera_bridge.payload import (
    bridge_config_filename,
    build_bridge_config,
    sanitize_rtsp_path,
)


def test_bridge_config_filename_is_entry_scoped():
    assert bridge_config_filename("abc") == "tuya_camera_bridge_abc.json"


def test_rtsp_path_matches_go_bridge_contract():
    assert sanitize_rtsp_path("Kitchen camera", "device") == "Kitchen_camera"
    assert sanitize_rtsp_path("/", "device") == "device"


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
    assert len(config["app_key"]) == 20
    assert config["app_version"] == "7.8.6"
    assert config["ttid"] == "international"
    assert config["et"] == "3"
    assert config["cameras"] == [
        {
            "camera_id": "camera",
            "camera_name": "Kitchen",
            "product_id": "product",
        }
    ]


def test_lan_credentials_do_not_change_the_go_contract():
    from custom_components.tuya_camera_bridge.config_flow import entry_data

    from .test_config_flow import LOGIN

    data = entry_data(LOGIN)
    data["cameras"][0]["local"] = {"local_key": "private-key", "schema": [{"id": 108}]}
    config = build_bridge_config(data)
    assert all(set(camera) == {"camera_id", "camera_name", "product_id"} for camera in config["cameras"])
    assert "private-key" not in str(config)


def test_local_media_contract_carries_only_provisioned_secrets_on_stdin():
    from custom_components.tuya_camera_bridge.config_flow import entry_data

    from .test_config_flow import LOGIN

    data = entry_data(LOGIN)
    local = {"local_key": "test-lan-key1234", "media_password": "test-p2p", "host": "192.168.0.81",
             "version": "3.3", "mac": "aa:bb", "schema": [{"id": 108}], "dps": {"108": "1"}}
    data["cameras"][0]["local"] = local
    config = build_bridge_config(data)
    assert config["uid"] == data["uid"]
    assert config["cameras"][0]["local_media"] == {
        "local_key": "test-lan-key1234", "media_password": "test-p2p", "host": "192.168.0.81", "mac": "aa:bb", "dp_ids": [],
    }
    local["version"] = "3.5"
    assert "local_media" not in build_bridge_config(data)["cameras"][0]
