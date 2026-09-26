"""Config flow for Tuya Camera Bridge."""
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
    CONF_CAMERA_ID,
    CONF_CAMERA_NAME,
    CONF_COUNTRY_CODE,
    CONF_ECODE,
    CONF_PARTNER,
    CONF_PHONE_DEVICE_ID,
    CONF_PRODUCT_ID,
    CONF_SID,
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


def _credentials_schema(
    default_username: str = "",
    default_country_code: str = DEFAULT_COUNTRY_CODE,
    default_application: str = DEFAULT_APPLICATION,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=default_username): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_COUNTRY_CODE, default=default_country_code): str,
            vol.Required(CONF_APPLICATION, default=default_application): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value="tuya_smart", label="Tuya Smart"),
                        SelectOptionDict(value="smart_life", label="Smart Life"),
                    ]
                )
            ),
        }
    )


def _flow_error(error: Exception) -> str:
    if isinstance(error, TuyaMobileInvalidAuth):
        return "invalid_auth"
    if isinstance(error, TuyaMobileAccountLocked):
        return "account_locked"
    if isinstance(error, TuyaMobileCaptchaRequired):
        return "captcha_required"
    if isinstance(error, TuyaMobileMFARequired):
        return "mfa_required"
    if isinstance(error, TuyaMobileProfileExpired):
        return "profile_expired"
    if isinstance(error, TuyaMobileTransportError):
        return "cannot_connect"
    return "unknown"


class TuyaCameraBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Tuya account and one camera."""

    VERSION = 1

    def __init__(self) -> None:
        self._login: LoginResult | None = None
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                api = TuyaCameraApi(async_get_clientsession(self.hass))
                self._login = await api.async_login(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_COUNTRY_CODE].lstrip("+"),
                    user_input[CONF_APPLICATION],
                )
                if not self._login.partner_identity:
                    errors["base"] = "incomplete_session"
                elif not self._login.cameras:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_camera()
            except Exception as error:  # noqa: BLE001 - config-flow boundary maps typed errors
                errors["base"] = _flow_error(error)
        return self.async_show_form(
            step_id="user", data_schema=_credentials_schema(), errors=errors
        )

    async def async_step_camera(self, user_input=None):
        if self._login is None:
            return self.async_abort(reason="incomplete_session")
        choices = [
            SelectOptionDict(value=item.device_id, label=item.name)
            for item in self._login.cameras
        ]
        if user_input is not None:
            selected = next(
                item for item in self._login.cameras if item.device_id == user_input[CONF_CAMERA_ID]
            )
            await self.async_set_unique_id(self._login.uid)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=selected.name,
                data={
                    CONF_USERNAME: self._login.username,
                    CONF_COUNTRY_CODE: self._login.country_code,
                    CONF_APPLICATION: self._login.application,
                    CONF_SID: self._login.sid,
                    CONF_ECODE: self._login.ecode,
                    CONF_UID: self._login.uid,
                    CONF_PARTNER: self._login.partner_identity,
                    CONF_API_HOST: self._login.api_host,
                    CONF_PHONE_DEVICE_ID: self._login.phone_device_id,
                    CONF_CAMERA_ID: selected.device_id,
                    CONF_CAMERA_NAME: selected.name,
                    CONF_PRODUCT_ID: selected.product_id,
                },
            )
        return self.async_show_form(
            step_id="camera",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CAMERA_ID): SelectSelector(
                        SelectSelectorConfig(options=choices)
                    )
                }
            ),
        )

    async def async_step_reauth(self, entry_data):
        """Start reauthentication without retaining the submitted password."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reconfigure(self, user_input=None):
        """Allow a user-initiated session refresh from the config entry UI."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(self, user_input=None):
        """Replace only session and app-routing fields for the existing camera."""
        if self._reauth_entry is None:
            return self.async_abort(reason="incomplete_session")
        errors = {}
        if user_input is not None:
            try:
                api = TuyaCameraApi(async_get_clientsession(self.hass))
                login = await api.async_login(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_COUNTRY_CODE].lstrip("+"),
                    user_input[CONF_APPLICATION],
                )
                if login.uid != self._reauth_entry.data[CONF_UID]:
                    return self.async_abort(reason="wrong_account")
                updated = {
                    **self._reauth_entry.data,
                    CONF_USERNAME: login.username,
                    CONF_COUNTRY_CODE: login.country_code,
                    CONF_APPLICATION: login.application,
                    CONF_SID: login.sid,
                    CONF_ECODE: login.ecode,
                    CONF_PARTNER: login.partner_identity,
                    CONF_API_HOST: login.api_host,
                    CONF_PHONE_DEVICE_ID: login.phone_device_id,
                }
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=updated
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")
            except Exception as error:  # noqa: BLE001 - config-flow boundary
                errors["base"] = _flow_error(error)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(
                self._reauth_entry.data.get(CONF_USERNAME, ""),
                self._reauth_entry.data.get(
                    CONF_COUNTRY_CODE, DEFAULT_COUNTRY_CODE
                ),
                self._reauth_entry.data.get(CONF_APPLICATION, DEFAULT_APPLICATION),
            ),
            errors=errors,
        )
