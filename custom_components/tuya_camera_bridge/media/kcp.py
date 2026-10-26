"""Bounded KCP message transport for the camera's authenticated LAN channel.

Wire format follows skywind3000/kcp (MIT); implementation is independent Python.
The camera uses message mode, no FEC, and a 512-segment receive window. UDP and
HMAC are owned by the caller. All methods execute on the asyncio event loop.
"""
from __future__ import annotations

import struct
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

HEADER = struct.Struct("<IBBHIIII")
WINDOW = 512
MSS = 1376


def diff(a: int, b: int) -> int:
    return ((a - b + 0x80000000) & 0xFFFFFFFF) - 0x80000000


@dataclass
class Segment:
    data: bytes
    fragment: int
    timestamp: int = 0
    resend: int = 0
    retries: int = 0
    fastacks: int = 0


class KCP:
    """Message reassembly, immediate ACKs and bounded reliable transmission."""

    def __init__(self, conversation: int, output: Callable[[bytes], None], receive: Callable[[bytes], None]):
        self.conversation, self.output, self.receive = conversation, output, receive
        self.next_receive = self.next_send = 0
        self.pending: dict[int, tuple[int, bytes]] = {}
        self.sending: dict[int, Segment] = {}
        self.queue: deque[Segment] = deque()
        self.fragments: list[bytes] = []
        self.fragment_remaining: int | None = None
        self.remote_window = WINDOW
        self.rto = 200
        self.srtt = self.rttvar = 0
        self.probe_at = 0
        self.closed = False

    def _packet(self, cmd: int, sn: int = 0, ts: int = 0, fragment: int = 0, data: bytes = b"") -> bytes:
        return HEADER.pack(self.conversation, cmd, fragment, max(0, WINDOW - len(self.pending)),
                           ts & 0xFFFFFFFF, sn, self.next_receive, len(data)) + data

    def send(self, data: bytes) -> None:
        count = max(1, (len(data) + MSS - 1) // MSS)
        if count > 255 or len(self.queue) + len(self.sending) + count > WINDOW:
            raise BufferError("Camera send window exceeded")
        for index in range(count):
            self.queue.append(Segment(data[index * MSS:(index + 1) * MSS], count - index - 1))

    def input(self, packet: bytes, now: int) -> None:
        """Consume complete wire segments; reject malformed lengths before mutation."""
        parts = []
        while packet:
            if len(packet) < HEADER.size:
                raise ValueError("Short KCP header")
            conv, cmd, frg, wnd, ts, sn, una, size = HEADER.unpack_from(packet)
            if conv != self.conversation or cmd not in (81, 82, 83, 84) or size > len(packet) - HEADER.size:
                raise ValueError("Invalid KCP segment")
            parts.append((cmd, frg, wnd, ts, sn, una, packet[24:24 + size]))
            packet = packet[24 + size:]
        for cmd, frg, wnd, ts, sn, una, data in parts:
            self.remote_window = wnd
            for sent in list(self.sending):
                if diff(sent, una) < 0:
                    del self.sending[sent]
            if cmd == 82:
                segment = self.sending.pop(sn, None)
                if segment is not None:
                    rtt = diff(now, ts)
                    if rtt >= 0:
                        if not self.srtt:
                            self.srtt, self.rttvar = rtt, rtt // 2
                        else:
                            self.rttvar = (3 * self.rttvar + abs(rtt - self.srtt)) // 4
                            self.srtt = (7 * self.srtt + rtt) // 8
                        self.rto = max(30, min(60000, self.srtt + max(10, 4 * self.rttvar)))
                    for earlier, item in self.sending.items():
                        if diff(earlier, sn) < 0:
                            item.fastacks += 1
            elif cmd == 83:
                self.output(self._packet(84))
            elif cmd == 81 and diff(sn, self.next_receive + WINDOW) < 0:
                self.output(self._packet(82, sn, ts))
                if diff(sn, self.next_receive) >= 0:
                    self.pending.setdefault(sn, (frg, data))
                self._deliver()

    def _deliver(self) -> None:
        while self.next_receive in self.pending:
            fragment, data = self.pending.pop(self.next_receive)
            self.next_receive = (self.next_receive + 1) & 0xFFFFFFFF
            if self.fragment_remaining is not None and fragment != self.fragment_remaining:
                raise ValueError("Invalid KCP fragment sequence")
            self.fragments.append(data)
            self.fragment_remaining = fragment - 1 if fragment else None
            if sum(map(len, self.fragments)) > 4 * 1024 * 1024:
                raise BufferError("Camera message exceeded limit")
            if not fragment:
                message = b"".join(self.fragments)
                self.fragments.clear()
                self.receive(message)

    def update(self, now: int) -> None:
        if self.closed:
            return
        while self.queue and len(self.sending) < min(WINDOW, self.remote_window):
            self.sending[self.next_send] = self.queue.popleft()
            self.next_send = (self.next_send + 1) & 0xFFFFFFFF
        if not self.remote_window and diff(now, self.probe_at) >= 0:
            self.output(self._packet(83))
            self.probe_at = (now + 5000) & 0xFFFFFFFF
        for sn, segment in self.sending.items():
            if not segment.retries or diff(now, segment.resend) >= 0 or segment.fastacks >= 2:
                segment.retries += 1
                if segment.retries > 20:
                    raise TimeoutError("Camera transport did not acknowledge data")
                segment.timestamp = now
                segment.resend = (now + min(60000, self.rto * (1 + segment.retries // 2))) & 0xFFFFFFFF
                segment.fastacks = 0
                self.output(self._packet(81, sn, now, segment.fragment, segment.data))
