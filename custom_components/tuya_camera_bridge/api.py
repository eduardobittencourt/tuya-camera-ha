"""Small, typed facade over the vendored Tuya mobile client."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .region import endpoint_for_country_code
from .vendor.tuya_mobile import TuyaMobileApp, TuyaPasswordClient, get_mobile_app_profile

CAMERA_CATEGORIES = {"sp", "dghsxj"}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


@dataclass(frozen=True)
class CameraInfo:
    device_id: str
    name: str
    product_id: str = ""


@dataclass(frozen=True)
class LoginResult:
    username: str
    sid: str
    ecode: str
    uid: str
    partner_identity: str
    endpoint: str
    api_host: str
    phone_device_id: str
    application: str
    country_code: str
    cameras: tuple[CameraInfo, ...]


class TuyaCameraApi:
    """Authenticate and discover devices using one explicit app namespace."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_login(
        self,
        username: str,
        password: str,
        country_code: str,
        application: str,
    ) -> LoginResult:
        selected = TuyaMobileApp(application)
        profile = get_mobile_app_profile(selected)
        client = TuyaPasswordClient.for_application(
            selected,
            self._session,
            username=username,
            endpoint=endpoint_for_country_code(country_code),
            max_login_attempts=1,
        )
        mobile_session = await client.login_with_password(password, country_code)
        user_info = await client._call("smartlife.m.user.info.get", {})
        login_data = client.login_result or {}
        partner = next(
            (
                str(item.get("partnerIdentity") or item.get("partnerId"))
                for item in _walk([login_data, user_info])
                if item.get("partnerIdentity") or item.get("partnerId")
            ),
            "",
        )
        cameras = await self._async_discover_devices(client)
        return LoginResult(
            username=username.strip(),
            sid=mobile_session.sid,
            ecode=mobile_session.ecode or "",
            uid=mobile_session.uid or "",
            partner_identity=partner,
            endpoint=mobile_session.endpoint,
            api_host=urlsplit(mobile_session.endpoint).hostname or "",
            phone_device_id=profile.stable_device_id(username),
            application=selected.value,
            country_code=country_code,
            cameras=tuple(cameras),
        )

    async def _async_discover_devices(self, client) -> list[CameraInfo]:
        homes = await client._call("m.life.home.space.list", {})
        gids = {
            str(item.get("gid") or item.get("groupId") or item.get("homeId"))
            for item in _walk(homes)
            if item.get("gid") or item.get("groupId") or item.get("homeId")
        }
        devices: dict[str, CameraInfo] = {}
        for gid in gids:
            response = await client._call(
                "m.life.my.group.device.list", {"gid": gid}, version="2.2"
            )
            for item in _walk(response):
                category = str(item.get("category") or item.get("categoryCode") or "")
                device_id = item.get("devId") or item.get("deviceId")
                name = item.get("name") or item.get("deviceName")
                if not device_id or not name:
                    continue
                if category:
                    if category not in CAMERA_CATEGORIES:
                        continue
                elif not await self._async_supports_webrtc(client, str(device_id)):
                    continue
                devices[str(device_id)] = CameraInfo(
                    device_id=str(device_id),
                    name=str(name),
                    product_id=str(item.get("productId") or item.get("productKey") or ""),
                )
        return sorted(devices.values(), key=lambda item: item.name.casefold())

    async def _async_supports_webrtc(self, client, device_id: str) -> bool:
        """Probe RTC capability when the device-list response omits category."""
        try:
            response = await client._call(
                "smartlife.m.rtc.config.get", {"devId": device_id}
            )
        except RuntimeError:
            return False
        if not isinstance(response, dict):
            return False
        if response.get("success") is True and isinstance(response.get("result"), dict):
            return True
        return "p2pConfig" in response or "skill" in response


def bridge_app_material(application: str) -> dict[str, str]:
    """Return public, versioned APK identity material needed by the bridge."""
    profile = get_mobile_app_profile(TuyaMobileApp(application))
    from .vendor.tuya_mobile.signer import PurePythonTuyaSigner

    signer = PurePythonTuyaSigner(
        profile.app_id,
        profile.app_secret,
        profile.cert_sha256_hex,
        profile.app_key,
        profile.package,
    )
    return {
        "signing_key": signer.global_material(),
        "app_key": profile.app_key,
        "ch_key": signer.channel_key(),
        "package_name": profile.package,
        "app_version": profile.app_version,
        "sdk_version": profile.sdk_version,
        "device_core_version": profile.device_core_version,
        "ttid": profile.ttid,
        "channel": profile.channel,
        "os_system": profile.os_system,
        "platform": profile.platform,
        "app_rn_version": profile.app_rn_version,
        "et": profile.et,
    }
