"""Bridge configuration contract shared with the add-on."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    DEFAULT_BRIDGE_PORT,
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
        "ecode": data[CONF_ECODE],
        "partner": data[CONF_PARTNER],
        "device_id": data[CONF_PHONE_DEVICE_ID],
        "api_host": data[CONF_API_HOST],
        "talkback": False,
        "bridge_port": DEFAULT_BRIDGE_PORT,
        "timezone": data.get(CONF_TIMEZONE, "UTC"),
        "cameras": cameras,
    }


def write_bridge_config_file(path: Path, config: dict) -> None:
    payload = json.dumps(config, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
