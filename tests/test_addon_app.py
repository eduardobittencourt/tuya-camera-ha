from __future__ import annotations

import asyncio
import json
import stat

import addon_app
import pytest


@pytest.mark.parametrize(
    ("country_code", "host"),
    [
        ("+55", "a1.tuyaus.com"),
        ("91", "a1.tuyain.com"),
        ("86", "a1.tuyacn.com"),
        ("351", "a1.tuyaeu.com"),
        ("61", "a1-sg.iotbing.com"),
    ],
)
def test_endpoint_for_country_code(country_code: str, host: str) -> None:
    assert host in addon_app.endpoint_for_country_code(country_code)


def test_walk_yields_nested_mappings() -> None:
    values = list(addon_app.walk({"outer": [{"camera": "one"}, {"camera": "two"}]}))
    assert {item.get("camera") for item in values} == {None, "one", "two"}


def test_compatible_cameras_probes_devices_without_category() -> None:
    class FakeClient:
        async def _call(self, action, payload):
            assert action == "smartlife.m.rtc.config.get"
            if payload["devId"] == "uncategorized-camera":
                return {"p2pConfig": {}}
            raise RuntimeError("not a camera")

    response = {
        "result": [
            {"devId": "camera", "name": "Kitchen", "category": "sp"},
            {"devId": "light", "name": "Hall light", "category": "dj"},
            {"devId": "uncategorized-camera", "name": "Nursery"},
            {"devId": "uncategorized-light", "name": "Desk light"},
        ]
    }

    assert asyncio.run(addon_app.compatible_cameras(FakeClient(), response)) == {
        "camera": {
            "camera_id": "camera",
            "camera_name": "Kitchen",
            "product_id": "",
        },
        "uncategorized-camera": {
            "camera_id": "uncategorized-camera",
            "camera_name": "Nursery",
            "product_id": "",
        },
    }


def test_account_metadata_supports_released_client_without_login_result() -> None:
    client = object()
    user_info = {
        "result": {
            "partnerIdentity": "partner",
            "timezoneId": "America/Sao_Paulo",
        }
    }

    assert addon_app.account_metadata(client, user_info) == (
        "partner",
        "America/Sao_Paulo",
    )


def test_account_metadata_prefers_captured_login_metadata() -> None:
    client = type(
        "Client",
        (),
        {"login_result": {"partnerIdentity": "login-partner", "timezone": "UTC"}},
    )()
    user_info = {"partnerIdentity": "user-partner"}

    assert addon_app.account_metadata(client, user_info) == ("login-partner", "UTC")


def test_write_config_is_atomic_and_private(tmp_path, monkeypatch) -> None:
    path = tmp_path / "bridge.json"
    monkeypatch.setattr(addon_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(addon_app, "CONFIG_PATH", path)

    config = {"sid": "secret", "cameras": [{"camera_name": "Kitchen"}]}
    addon_app.write_config(config)

    assert json.loads(path.read_text()) == config
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_page_escapes_camera_names_and_messages(tmp_path, monkeypatch) -> None:
    path = tmp_path / "bridge.json"
    path.write_text(json.dumps({"cameras": [{"camera_name": "<camera>"}]}))
    monkeypatch.setattr(addon_app, "CONFIG_PATH", path)

    rendered = addon_app.page(addon_app.BridgeSupervisor(), message="<saved>")

    assert "&lt;camera&gt;" in rendered
    assert "&lt;saved&gt;" in rendered
    assert "<camera>" not in rendered


def test_default_ingress_proxy_is_restricted() -> None:
    assert addon_app.TRUSTED_INGRESS_IP == "172.30.32.2"


def test_supervisor_stop_interrupts_restart_backoff(tmp_path, monkeypatch) -> None:
    config = tmp_path / "bridge.json"
    config.write_text("{}")
    monkeypatch.setattr(addon_app, "CONFIG_PATH", config)
    attempted = asyncio.Event()

    async def fail_to_start(*args, **kwargs):
        attempted.set()
        raise OSError("test failure")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_to_start)

    async def scenario() -> None:
        supervisor = addon_app.BridgeSupervisor()
        await supervisor.start()
        await asyncio.wait_for(attempted.wait(), timeout=1)
        await asyncio.sleep(0)
        await asyncio.wait_for(supervisor.stop_process(), timeout=1)
        assert supervisor.monitor is None
        assert supervisor.process is None

    asyncio.run(scenario())
