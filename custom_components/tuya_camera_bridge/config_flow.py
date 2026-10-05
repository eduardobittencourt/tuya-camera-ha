"""UI-driven account setup and reauthentication without persisting passwords."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig

from .api import LoginResult, TuyaCameraApi
from .const import (
    CONF_API_HOST,
    CONF_APPLICATION,
    CONF_CAMERAS,
    CONF_COUNTRY_CODE,
    CONF_ECODE,
    CONF_PARTNER,
    CONF_PHONE_DEVICE_ID,
    CONF_SID,
    CONF_TIMEZONE,
    CONF_UID,
    DEFAULT_APPLICATION,
    DEFAULT_COUNTRY_CODE,
    DOMAIN,
)
from .vendor.tuya_mobile.errors import (
    TuyaMobileAccountLocked,
    TuyaMobileCaptchaRequired,
    TuyaMobileInvalidAuth,
    TuyaMobileMFARequired,
    TuyaMobileProfileExpired,
    TuyaMobileTransportError,
)


def _credentials_schema(data: dict | None = None) -> vol.Schema:
    defaults = data or {}
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_COUNTRY_CODE, default=defaults.get(CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE)): str,
        vol.Required(CONF_APPLICATION, default=defaults.get(CONF_APPLICATION, DEFAULT_APPLICATION)): SelectSelector(
            SelectSelectorConfig(options=[
                SelectOptionDict(value="tuya_smart", label="Tuya Smart"),
                SelectOptionDict(value="smart_life", label="Smart Life"),
            ])
        ),
    })


def _flow_error(error: Exception) -> str:
    for error_type, key in (
        (TuyaMobileInvalidAuth, "invalid_auth"), (TuyaMobileAccountLocked, "account_locked"),
        (TuyaMobileCaptchaRequired, "captcha_required"), (TuyaMobileMFARequired, "mfa_required"),
        (TuyaMobileProfileExpired, "profile_expired"), (TuyaMobileTransportError, "cannot_connect"),
    ):
        if isinstance(error, error_type):
            return key
    return "unknown"


def entry_data(login: LoginResult) -> dict:
    return {
        CONF_USERNAME: login.username, CONF_COUNTRY_CODE: login.country_code, CONF_APPLICATION: login.application,
        CONF_SID: login.sid, CONF_ECODE: login.ecode, CONF_UID: login.uid,
        CONF_PARTNER: login.partner_identity, CONF_API_HOST: login.api_host,
        CONF_PHONE_DEVICE_ID: login.phone_device_id, CONF_TIMEZONE: login.timezone,
        CONF_CAMERAS: [{"camera_id": item.device_id, "camera_name": item.name, "product_id": item.product_id}
                       for item in login.cameras],
    }


class TuyaCameraBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One entry per Tuya account, with all discovered cameras."""

    VERSION = 2

    async def _login(self, user_input: dict) -> LoginResult:
        api = TuyaCameraApi(async_get_clientsession(self.hass))
        return await api.async_login(
            user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD],
            user_input[CONF_COUNTRY_CODE].strip().lstrip("+"), user_input[CONF_APPLICATION],
        )

    @staticmethod
    def _validate(login: LoginResult) -> str | None:
        if not all((login.partner_identity, login.sid, login.ecode, login.uid)):
            return "incomplete_session"
        if not login.cameras:
            return "no_devices"
        return None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                login = await self._login(user_input)
            except Exception as err:  # noqa: BLE001 - map errors without logging credential-bearing details
                errors["base"] = _flow_error(err)
            else:
                if error := self._validate(login):
                    errors["base"] = error
                else:
                    await self.async_set_unique_id(f"{login.application}_{login.uid}")
                    self._abort_if_unique_id_configured()
                    if any(entry.data.get(CONF_UID) == login.uid and entry.data.get(CONF_APPLICATION) == login.application
                           for entry in self._async_current_entries()):
                        return self.async_abort(reason="already_configured")
                    return self.async_create_entry(title="Tuya cameras", data=entry_data(login))
        return self.async_show_form(step_id="user", data_schema=_credentials_schema(), errors=errors)

    async def async_step_reauth(self, _entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reconfigure(self, user_input=None):
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="incomplete_session")
        errors = {}
        if user_input is not None:
            try:
                login = await self._login(user_input)
            except Exception as err:  # noqa: BLE001 - UI boundary preserves secrets
                errors["base"] = _flow_error(err)
            else:
                if login.uid != entry.data[CONF_UID] or login.application != entry.data[CONF_APPLICATION]:
                    return self.async_abort(reason="wrong_account")
                if error := self._validate(login):
                    errors["base"] = error
                else:
                    return self.async_update_reload_and_abort(entry, data=entry_data(login))
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_credentials_schema(entry.data), errors=errors,
        )
