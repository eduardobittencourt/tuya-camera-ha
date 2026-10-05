from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_camera_bridge.api import CameraInfo, LoginResult
from custom_components.tuya_camera_bridge.const import DOMAIN
from custom_components.tuya_camera_bridge.vendor.tuya_mobile.errors import TuyaMobileInvalidAuth

LOGIN = LoginResult(
    username="example@example.invalid", sid="test-session", ecode="test-ecode", uid="account",
    partner_identity="partner", endpoint="https://a1.tuyaus.com/api.json", api_host="a1.tuyaus.com",
    phone_device_id="phone", application="tuya_smart", country_code="55",
    cameras=(CameraInfo("one", "Kitchen"), CameraInfo("two", "Doorbell")), timezone="America/Sao_Paulo",
)
INPUT = {"username": LOGIN.username, "password": "never-persist-this", "country_code": "+55",
         "application": "tuya_smart"}


async def test_login_creates_all_cameras_and_never_stores_password(hass):
    with patch("custom_components.tuya_camera_bridge.config_flow.TuyaCameraApi.async_login", return_value=LOGIN), \
         patch("custom_components.tuya_camera_bridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(result["data"]["cameras"]) == 2
    assert result["data"]["timezone"] == "America/Sao_Paulo"
    assert "password" not in result["data"]
    assert INPUT["password"] not in str(result["data"])


async def test_invalid_authentication_is_shown_without_error_details(hass):
    with patch("custom_components.tuya_camera_bridge.config_flow.TuyaCameraApi.async_login",
               side_effect=TuyaMobileInvalidAuth("private response body")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert "private response" not in str(result)


async def test_existing_account_is_not_created_twice(hass):
    existing = MockConfigEntry(domain=DOMAIN, unique_id="tuya_smart_account", data={})
    existing.add_to_hass(hass)
    with patch("custom_components.tuya_camera_bridge.config_flow.TuyaCameraApi.async_login", return_value=LOGIN):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER}, data=INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauthentication_replaces_session_and_reloads_without_password(hass):
    from dataclasses import replace

    from custom_components.tuya_camera_bridge.config_flow import entry_data
    existing = MockConfigEntry(domain=DOMAIN, version=2, unique_id="tuya_smart_account", data=entry_data(LOGIN))
    existing.add_to_hass(hass)
    refreshed = replace(LOGIN, sid="new-session", ecode="new-ecode")
    with patch("custom_components.tuya_camera_bridge.config_flow.TuyaCameraApi.async_login", return_value=refreshed), \
         patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": existing.entry_id}, data=existing.data,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert existing.data["sid"] == "new-session"
    assert "password" not in existing.data
    reload.assert_awaited_once_with(existing.entry_id)


async def test_reauthentication_rejects_a_different_account(hass):
    from dataclasses import replace

    from custom_components.tuya_camera_bridge.config_flow import entry_data
    existing = MockConfigEntry(domain=DOMAIN, version=2, unique_id="tuya_smart_account", data=entry_data(LOGIN))
    existing.add_to_hass(hass)
    with patch("custom_components.tuya_camera_bridge.config_flow.TuyaCameraApi.async_login",
               return_value=replace(LOGIN, uid="different")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": existing.entry_id}, data=existing.data,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["reason"] == "wrong_account"
    assert existing.data["sid"] == LOGIN.sid
