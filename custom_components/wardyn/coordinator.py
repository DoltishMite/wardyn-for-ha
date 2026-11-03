"""Keeps Wardyn's entities up to date from its link copy, raises alerts, and sends the buttons' requests.

Changes arrive over the live link (wss /api/live) the moment a node writes; a pull every 5 minutes is the safety net, and the
entities are worked out again every minute so a node that stops writing goes "not connected" without a new save.
A button adds a request ({ id, t, node, kind }) to the copy (by: 'ha'), against the version just read, again after a clash; the node
takes it within 20 seconds and marks it done. Requests over an hour old are tidied away.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .const import CONF_CODE, DOMAIN, HEADERS, LIVE_URL, LOGGER
from .hpcrypto import SealError, keys_for, open_doc, seal_doc
from .core.model import Parsed
from .core.parse import alerts, is_link, parse

POLL = timedelta(minutes=5)
GRACE = timedelta(minutes=30)   # how long the last copy stands in when the server can't be reached
TICK = timedelta(minutes=1)
KEEP_REQUESTS = 3600 * 1000     # ms


class WardynCoordinator(DataUpdateCoordinator[Parsed]):
    """Fetches, opens and parses; data is a Parsed (devices + things)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=POLL)
        self.session = async_get_clientsession(hass)
        self.keys = keys_for(entry.data[CONF_CODE])
        self.doc: tuple[int, Any] | None = None
        self.live = False
        self.panel: str | None = None
        self.names: dict[str, dict[str, str]] = {}
        self.alert_listeners: list[Callable[[str, dict], None]] = []
        self._snap: dict | None = None
        self._last_ok: float | None = None
        self._away = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    async def _open(self, doc: str) -> Any:
        return await self.hass.async_add_executor_job(open_doc, doc, self.keys)

    async def _async_update_data(self) -> Parsed:
        try:
            v, doc = await api.get_doc(self.session, self.keys)
        except api.Refused as err:
            raise UpdateFailed("The server refused Home Assistant") from err
        except api.ApiError as err:
            # the server is away for a moment (a restart, the PC asleep): keep the last copy, worked out afresh, for up to half an hour
            if self.doc and self._last_ok is not None and time.monotonic() - self._last_ok < GRACE.total_seconds():
                if not self._away:
                    LOGGER.info("Can't reach the server (%s): showing what was fetched last", err)
                    self._away = True
                return self.build()
            raise UpdateFailed(str(err)) from err
        if not v:
            raise UpdateFailed("Wardyn's link copy has gone: connect Home Assistant again in Wardyn (Settings → Home Assistant)")
        if not self.doc or self.doc[0] != v:
            try:
                self.doc = (v, await self._open(doc))
            except SealError as err:
                raise UpdateFailed(f"Wardyn's link copy {err}") from err
        self._last_ok, self._away = time.monotonic(), False
        return self.build()

    @callback
    def build(self) -> Parsed:
        p = parse(self.doc[1] if self.doc else None, dt_util.now())
        for kind, details in alerts(self._snap, p.snapshot):
            for f in self.alert_listeners:
                f(kind, details)
            self.hass.bus.async_fire(f"{DOMAIN}_alert", {"type": kind, **details})
        self._snap = p.snapshot
        return p

    # ---------- a button ----------
    async def async_request(self, node: str, kind: str) -> None:
        v, doc = await api.get_doc(self.session, self.keys)
        for _ in range(5):
            if not v:
                raise HomeAssistantError("Wardyn's link copy has gone")
            obj = await self._open(doc)
            if not is_link(obj):
                raise HomeAssistantError("Wardyn's link copy can't be read")
            if obj.get("controls") is not True:
                raise HomeAssistantError("Wardyn doesn't let Home Assistant control the nodes (Settings → Home Assistant)")
            now = int(time.time() * 1000)
            reqs = [r for r in obj.get("requests") or [] if isinstance(r, dict) and now - int(r.get("t") or 0) < KEEP_REQUESTS]
            reqs.append({"id": "h" + format(now, "x") + secrets.token_hex(2), "t": now, "node": node, "kind": kind})
            obj["requests"], obj["by"] = reqs, "ha"
            sealed = await self.hass.async_add_executor_job(seal_doc, obj, self.keys)
            try:
                status, nv, cur = await api.put_doc(self.session, self.keys, v, sealed)
            except api.ApiError as err:
                raise HomeAssistantError(str(err)) from err
            if status == 200:
                self.doc = (nv, obj)
                return
            v, doc = nv, cur   # a node saved first: add the request to its version
        raise HomeAssistantError("Kept clashing with the nodes' saves: try again")

    # ---------- the live link ----------
    async def run_live(self) -> None:
        """Runs for as long as the entry is loaded (a background task). Reconnects from 1 s up to 5 minutes apart."""
        wait = 1
        while True:
            try:
                async with self.session.ws_connect(LIVE_URL, headers=HEADERS, heartbeat=60) as ws:
                    self._ws = ws
                    await ws.send_str(json.dumps({"op": "sub", "ids": [self.keys.id]}))
                    self.live, wait = True, 1
                    await self.async_request_refresh()   # catch anything missed while it was down
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._on_message(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 — any failure just means "try again later"; the poll keeps things going
                if self.live:
                    LOGGER.debug("Live link down (%s)", type(err).__name__)
            self._ws, self.live = None, False
            await asyncio.sleep(wait)
            wait = min(wait * 2, 300)

    async def _on_message(self, text: str) -> None:
        try:
            m = json.loads(text)
        except ValueError:
            return
        if m.get("id") != self.keys.id or m.get("op") != "changed":
            return
        v = int(m.get("v") or 0)
        if not v or (self.doc and self.doc[0] == v):
            return
        try:
            if isinstance(m.get("doc"), str):
                self.doc = (v, await self._open(m["doc"]))
            else:
                await self.async_request_refresh()
                return
        except SealError:
            return
        self.async_set_updated_data(self.build())

    @callback
    def start_tick(self) -> None:
        """Work the states out again every minute (a node that stopped writing goes not connected), with no new data needed."""
        @callback
        def _tick(_now) -> None:
            if self.last_update_success and self.doc:
                self.data = self.build()          # not async_set_updated_data: that would keep pushing the 5-minute pull back
                self.async_update_listeners()
        self.config_entry.async_on_unload(async_track_time_interval(self.hass, _tick, TICK))
