"""Account-scoped Python media sessions and private RTSP listener."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from contextlib import suppress

from .cloud import CloudAccount, CloudSession, MediaAuthenticationError, MediaError
from .lan import LanSession, resolve_host
from .rtsp import MediaSource, RtspServer


class MediaRuntime:
    """Own every socket/task; a failed camera can reconnect on the next request."""

    def __init__(self, session, data: dict, on_change, on_auth_required):
        self.data, self.on_change, self.on_auth_required = data, on_change, on_auth_required
        self.ready = self.auth_required = False
        self.sources: dict = {}
        self.camera_status: dict = {}
        self.media: dict[str, MediaSource] = {}
        self.server = None
        self.configs = {}
        self.account = CloudAccount(session, data, self._reauth)

    def _reauth(self):
        self.auth_required = True
        self.on_auth_required()
        self.on_change()

    def state(self, camera_id, state):
        previous = self.camera_status.get(camera_id, {})
        self.camera_status[camera_id] = {
            "state": state, "cloud_wakes": previous.get("cloud_wakes", 0) + (state == "waking_cloud"),
            "last_video": time.time() if state == "video" else previous.get("last_video")}
        self.on_change()

    async def start(self):
        for camera in self.data["cameras"]:
            cid = camera["camera_id"]
            local = camera.get("local", {})
            use_lan = bool(local.get("host") and local.get("version") == "3.3" and local.get("media_password"))
            path = "/" + secrets.token_urlsafe(24)
            hevc = False
            if not use_lan:
                config = await self.account.call("smartlife.m.rtc.config.get", {"devId": cid})
                self.configs[cid] = config
                skill = config.get("skill") or {}
                if isinstance(skill, str):
                    skill = json.loads(skill)
                video = max(skill.get("videos", []), key=lambda v: v.get("width", 0) * v.get("height", 0), default={})
                hevc = video.get("codecType") == 4
            self.sources[cid] = {"path": path, "hevc": hevc, "transport": "lan" if use_lan else "cloud"}
            self.media[cid] = MediaSource(
                lambda packet, c=camera, lan=use_lan: self._open(c, lan, packet),
                lambda camera_id=cid: self.state(camera_id, "video"),
                lambda failed, camera_id=cid: self.state(camera_id, "error" if failed else "standby"))
        self.server = RtspServer({self.sources[cid]["path"]: source for cid, source in self.media.items()})
        await self.server.start()
        self.ready = True
        self.on_change()

    def source_url(self, camera_id):
        return f"rtsp://127.0.0.1:{self.server.port}{self.sources[camera_id]['path']}"

    async def _open(self, camera, lan, packet):
        cid = camera["camera_id"]
        session = None
        broker = wake = None
        try:
            async with asyncio.timeout(65):
                if lan:
                    host = await asyncio.to_thread(resolve_host, camera["local"])
                    camera = {**camera, "local": {**camera["local"], "host": host}}
                    self.state(cid, "connecting_lan")
                    session = LanSession(camera, self.data["uid"], packet)
                    try:
                        await session.connect()
                    except (OSError, TimeoutError):
                        await session.close()
                        self.state(cid, "waking_cloud")
                        self.state(cid, "wake_mqtt")
                        broker = await self.account.broker()
                        await broker.wake(camera)
                        end = time.monotonic() + 12
                        while True:
                            session = LanSession(camera, self.data["uid"], packet)
                            try:
                                await session.connect()
                                break
                            except (OSError, TimeoutError):
                                await session.close()
                                if time.monotonic() >= end:
                                    self.state(cid, "wake_media")
                                    wake = CloudSession(self.account, camera, lambda *_: None)
                                    await wake.start()
                                    await asyncio.wait_for(wake.first_video.wait(), 20)
                                    session = LanSession(camera, self.data["uid"], packet)
                                    await session.connect()
                                    await wake.close()
                                    wake = None
                                    break
                                await asyncio.sleep(.3)
                    self.state(cid, "connecting_lan")
                    await session.start()
                    if broker:
                        owner, broker = broker, None
                        async def finish_wake():
                            try:
                                await asyncio.sleep(10)
                            finally:
                                await owner.close()
                        session.task(finish_wake())
                else:
                    session = CloudSession(self.account, camera, packet, self.configs.get(cid))
                    await session.start()
                    self.sources[cid]["hevc"] = session.hevc
            return session
        except BaseException as err:
            if session:
                await session.close()
            self.state(cid, "error")
            if isinstance(err, (asyncio.CancelledError, MediaAuthenticationError)):
                raise
            raise MediaError("The camera media connection failed") from None
        finally:
            if wake:
                await wake.close()
            if broker:
                # Keep the wake connection alive until LAN negotiation has completed.
                await broker.close()

    async def local_request(self, camera_id, operation, **payload):
        source = self.media.get(camera_id)
        session = source.session if source else None
        if not isinstance(session, LanSession) or session.failed.is_set():
            raise MediaError("Local media is inactive")
        if operation == "status":
            return {"dps": dict(session.values)}
        if operation == "receive":
            with suppress(TimeoutError):
                return {"dps": await asyncio.wait_for(session.reports.get(), .1)}
            return {"dps": {}}
        if operation == "set":
            await session.set_dp(payload["index"], payload["value"])
            return {"dps": {}}
        if operation == "stats":
            return {"dps": dict(session.stats)}
        raise MediaError("Unsupported local operation")

    async def stop(self):
        self.ready = False
        if self.server:
            await self.server.stop()
            self.server = None
        self.on_change()
