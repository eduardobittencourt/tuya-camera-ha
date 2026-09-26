#!/usr/bin/env python3
"""Ingress setup UI and process supervisor for the standalone add-on."""

from __future__ import annotations

import asyncio
import html
import json
import os
import signal
import time
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from tuya_mobile import TuyaMobileApp, TuyaPasswordClient, get_mobile_app_profile
from tuya_mobile.signer import PurePythonTuyaSigner

DATA_DIR = Path(os.environ.get("TUYA_BRIDGE_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "bridge.json"
PORT = int(os.environ.get("INGRESS_PORT", "8099"))
CAMERA_CATEGORIES = {"sp", "dghsxj"}
TRUSTED_INGRESS_IP = os.environ.get("TRUSTED_INGRESS_IP", "172.30.32.2")
RESTART_MIN_DELAY = 2.0
RESTART_MAX_DELAY = 60.0
STABLE_RUNTIME = 60.0


class CapturingTuyaPasswordClient(TuyaPasswordClient):
    """Retain non-password login metadata omitted by tuya-mobile 1.2.0."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.login_result: dict[str, Any] | None = None

    async def _submit_login(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        result = await super()._submit_login(*args, **kwargs)
        self.login_result = dict(result)
        return result


def endpoint_for_country_code(country_code: str) -> str:
    code = country_code.strip().lstrip("+")
    if code in {
        "1", "7", "51", "52", "53", "54", "55", "56", "57", "58",
        "501", "502", "503", "504", "505", "506", "507", "509", "591",
        "592", "593", "594", "595", "596", "597", "598", "599",
    }:
        return "https://a1.tuyaus.com/api.json"
    if code == "91":
        return "https://a1.tuyain.com/api.json"
    if code == "86":
        return "https://a1.tuyacn.com/api.json"
    if code in {
        "60", "61", "62", "63", "64", "65", "66", "81", "82", "84",
        "852", "853", "855", "856", "880", "886", "960", "961", "962",
        "963", "964", "965", "966", "967", "968", "970", "971", "972",
        "973", "974", "975", "976", "977", "992", "993", "994", "995",
        "996", "998",
    }:
        return "https://a1-sg.iotbing.com/api.json"
    return "https://a1.tuyaeu.com/api.json"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def account_metadata(client: Any, user_info: Any) -> tuple[str, str]:
    sources = [getattr(client, "login_result", None) or {}, user_info]
    partner = next(
        (
            str(item.get("partnerIdentity") or item.get("partnerId"))
            for item in walk(sources)
            if item.get("partnerIdentity") or item.get("partnerId")
        ),
        "",
    )
    timezone = next(
        (
            str(item.get("timezoneId") or item.get("timeZoneId") or item.get("timezone"))
            for item in walk(sources)
            if item.get("timezoneId") or item.get("timeZoneId") or item.get("timezone")
        ),
        os.environ.get("TZ", "UTC"),
    )
    return partner, timezone


async def login_and_build_config(
    username: str, password: str, country_code: str, application: str
) -> dict[str, Any]:
    selected = TuyaMobileApp(application)
    profile = get_mobile_app_profile(selected)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = CapturingTuyaPasswordClient.for_application(
            selected,
            session,
            username=username,
            endpoint=endpoint_for_country_code(country_code),
            max_login_attempts=1,
        )
        mobile_session = await client.login_with_password(password, country_code)
        user_info = await client._call("smartlife.m.user.info.get", {})
        partner, timezone = account_metadata(client, user_info)
        if not partner:
            raise RuntimeError("Tuya login succeeded but returned no partner identity")

        homes = await client._call("m.life.home.space.list", {})
        gids = {
            str(item.get("gid") or item.get("groupId") or item.get("homeId"))
            for item in walk(homes)
            if item.get("gid") or item.get("groupId") or item.get("homeId")
        }
        cameras: dict[str, dict[str, str]] = {}
        for gid in gids:
            response = await client._call(
                "m.life.my.group.device.list", {"gid": gid}, version="2.2"
            )
            for item in walk(response):
                category = str(item.get("category") or item.get("categoryCode") or "")
                device_id = item.get("devId") or item.get("deviceId")
                name = item.get("name") or item.get("deviceName")
                if not device_id or not name or (category and category not in CAMERA_CATEGORIES):
                    continue
                cameras[str(device_id)] = {
                    "camera_id": str(device_id),
                    "camera_name": str(name),
                    "product_id": str(item.get("productId") or item.get("productKey") or ""),
                }
        if not cameras:
            raise RuntimeError("No compatible Tuya cameras were found in this account")

        signer = PurePythonTuyaSigner(
            profile.app_id,
            profile.app_secret,
            profile.cert_sha256_hex,
            profile.app_key,
            profile.package,
        )
        return {
            "signing_key": signer.global_material(),
            "sid": mobile_session.sid,
            "ecode": mobile_session.ecode or "",
            "partner": partner,
            "app_key": profile.app_id,
            "ch_key": signer.channel_key(),
            "device_id": profile.stable_device_id(username),
            "package_name": profile.package,
            "api_host": urlsplit(mobile_session.endpoint).hostname or "",
            "app_version": profile.app_version,
            "sdk_version": profile.sdk_version,
            "device_core_version": profile.device_core_version,
            "ttid": profile.ttid,
            "channel": profile.channel,
            "os_system": profile.os_system,
            "platform": profile.platform,
            "app_rn_version": profile.app_rn_version,
            "et": profile.et,
            "timezone": timezone,
            "talkback": False,
            "bridge_port": 38554,
            "cameras": sorted(cameras.values(), key=lambda item: item["camera_name"].casefold()),
        }


def write_config(config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR, delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            json.dump(config, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CONFIG_PATH)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class BridgeSupervisor:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.monitor: asyncio.Task | None = None
        self.last_error = ""
        self.stopping = False

    async def start(self) -> None:
        if not CONFIG_PATH.exists() or self.monitor is not None:
            return
        self.stopping = False
        self.monitor = asyncio.create_task(self._monitor())

    async def _monitor(self) -> None:
        delay = RESTART_MIN_DELAY
        try:
            while not self.stopping and CONFIG_PATH.exists():
                started = time.monotonic()
                try:
                    self.process = await asyncio.create_subprocess_exec(
                        "tuya-camera-bridge",
                        "addon",
                        "--config",
                        str(CONFIG_PATH),
                        "--onvif",
                        "--onvif-username",
                        "",
                        "--data-dir",
                        str(DATA_DIR),
                    )
                    self.last_error = ""
                    code = await self.process.wait()
                except OSError as exc:
                    code = None
                    self.last_error = f"Could not start bridge: {exc}"
                finally:
                    self.process = None
                if self.stopping:
                    break
                if code is not None:
                    self.last_error = f"Bridge exited with status {code}; retrying"
                runtime = time.monotonic() - started
                if runtime >= STABLE_RUNTIME:
                    delay = RESTART_MIN_DELAY
                await asyncio.sleep(delay)
                delay = min(delay * 2, RESTART_MAX_DELAY)
        finally:
            self.process = None
            self.monitor = None

    async def restart(self) -> None:
        await self.stop_process()
        self.stopping = False
        await self.start()

    async def stop_process(self) -> None:
        self.stopping = True
        if self.process is not None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=15)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.process = None
        if self.monitor is not None:
            monitor = self.monitor
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor
            if self.monitor is monitor:
                self.monitor = None


def page(supervisor: BridgeSupervisor, message: str = "", error: str = "") -> str:
    configured = CONFIG_PATH.exists()
    running = supervisor.process is not None
    restarting = configured and supervisor.monitor is not None and not running
    if running:
        state = "running"
    elif restarting:
        state = "restarting"
    else:
        state = "configured, stopped" if configured else "not configured"
    cameras = []
    if configured:
        with suppress(OSError, KeyError, json.JSONDecodeError):
            cameras = [item["camera_name"] for item in json.loads(CONFIG_PATH.read_text())["cameras"]]
    camera_text = ", ".join(html.escape(item) for item in cameras) or "none"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Tuya Camera Bridge</title><style>
body{{font:16px system-ui;max-width:620px;margin:2rem auto;padding:0 1rem;color:#222}}label{{display:block;margin:.9rem 0 .3rem}}
input,select,button{{box-sizing:border-box;width:100%;padding:.7rem;font:inherit}}button{{margin-top:1.2rem;background:#03a9f4;color:white;border:0;border-radius:4px}}
.ok{{color:#18794e}}.err{{color:#b42318}}small{{color:#666}}</style></head><body>
<h1>Tuya Camera Bridge</h1><p>Status: <strong>{state}</strong><br>Cameras: {camera_text}</p>
<p class="ok">{html.escape(message)}</p><p class="err">{html.escape(error or supervisor.last_error)}</p>
<form method="post" action="setup"><label>Tuya account (email or phone)</label><input name="username" autocomplete="username" required>
<label>Password</label><input name="password" type="password" autocomplete="current-password" required>
<label>International country code</label><input name="country_code" value="55" inputmode="numeric" required>
<label>Application</label><select name="application"><option value="tuya_smart">Tuya Smart</option><option value="smart_life">Smart Life</option></select>
<button type="submit">Authenticate and discover cameras</button></form>
<p><small>The password is used only for this login request and is not written to disk. The resulting Tuya session is stored privately in the add-on data directory.</small></p>
</body></html>"""


async def index(request: web.Request) -> web.Response:
    return web.Response(text=page(request.app["supervisor"]), content_type="text/html")


async def setup(request: web.Request) -> web.Response:
    supervisor: BridgeSupervisor = request.app["supervisor"]
    async with request.app["setup_lock"]:
        form = await request.post()
        try:
            config = await login_and_build_config(
                str(form.get("username", "")).strip(),
                str(form.get("password", "")),
                str(form.get("country_code", "")).strip().lstrip("+"),
                str(form.get("application", "tuya_smart")),
            )
            write_config(config)
            await supervisor.restart()
            names = ", ".join(camera["camera_name"] for camera in config["cameras"])
            return web.Response(text=page(supervisor, f"Configured successfully: {names}"), content_type="text/html")
        except Exception as exc:  # noqa: BLE001 - UI boundary intentionally redacts details
            return web.Response(text=page(supervisor, error=str(exc)), content_type="text/html", status=400)


@web.middleware
async def security_headers(request: web.Request, handler: Any) -> web.StreamResponse:
    if request.remote != TRUSTED_INGRESS_IP:
        raise web.HTTPForbidden(text="This interface is available only through Home Assistant Ingress")
    response = await handler(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


async def run() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    supervisor = BridgeSupervisor()
    app = web.Application(client_max_size=64 * 1024, middlewares=[security_headers])
    app["supervisor"] = supervisor
    app["setup_lock"] = asyncio.Lock()
    app.router.add_get("/", index)
    app.router.add_post("/setup", setup)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await supervisor.start()

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    await stopped.wait()
    await supervisor.stop_process()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run())
