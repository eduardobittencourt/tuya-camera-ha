"""Private stdin configuration contract for the managed Go executable."""
from __future__ import annotations

from .const import (
    CONF_API_HOST,
    CONF_APPLICATION,
    CONF_CAMERA_ID,
    CONF_CAMERA_NAME,
    CONF_CAMERAS,
    CONF_ECODE,
    CONF_PARTNER,
    CONF_PHONE_DEVICE_ID,
    CONF_PRODUCT_ID,
    CONF_SID,
    CONF_TIMEZONE,
)

PREFIX = "tuya_camera_bridge_"


def bridge_config_filename(entry_id: str) -> str:
    return f"{PREFIX}{entry_id}.json"


def sanitize_rtsp_path(name: str, device_id: str) -> str:
    value = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return value if value not in {"", "_"} else device_id


def build_bridge_config(data: dict) -> dict:
    from .api import bridge_app_material

    app = bridge_app_material(data[CONF_APPLICATION])
    cameras = data.get(CONF_CAMERAS) or [{"camera_id": data[CONF_CAMERA_ID], "camera_name": data[CONF_CAMERA_NAME], "product_id": data.get(CONF_PRODUCT_ID, "")}]
    return {
        **app,
        "sid": data[CONF_SID],
        "uid": data.get("uid", ""),
        "ecode": data[CONF_ECODE],
        "partner": data[CONF_PARTNER],
        "device_id": data[CONF_PHONE_DEVICE_ID],
        "api_host": data[CONF_API_HOST],
        "talkback": False,
        "bridge_port": 0,
        "timezone": data.get(CONF_TIMEZONE, "UTC"),
        "cameras": [_media_camera(camera) for camera in cameras],
    }


def _media_camera(camera: dict) -> dict:
    result = {key: camera[key] for key in ("camera_id", "camera_name", "product_id") if key in camera}
    local = camera.get("local") or {}
    # Only the verified protocol is enabled. No raw schema or DP values cross
    # this boundary. Session material travels on the managed process's stdin.
    if local.get("media_password") and local.get("version") == "3.3" and local.get("host"):
        result["local_media"] = {key: local[key] for key in
                                 ("local_key", "media_password", "host", "mac") if key in local}
        result["local_media"]["dp_ids"] = [int(item["id"]) for item in local.get("schema", [])
                                               if item.get("property", {}).get("type") in ("bool", "enum", "value")]
    return result
