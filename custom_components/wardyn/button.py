"""Buttons: ask a node to do something, as Wardyn's own buttons do (update or restart Wardyn Agent, look for and install updates, run
its checks, a quick antivirus scan, a speed test, scan for devices). Only while Wardyn lets Home Assistant control the nodes
(Settings → Home Assistant), and only for the parts a node has on. The node takes the request within 20 seconds."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import BUTTON


class WardynButton(WardynEntity, ButtonEntity):
    async def async_press(self) -> None:
        t = self.thing
        if t and t.data and "key" in t.data:   # Wardyn's catalogue: the keeper node does it
            await self.coordinator.async_request("*", "press", key=t.data["key"])
        elif t and t.data:
            await self.coordinator.async_request(t.data["node"], t.data["kind"])


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, BUTTON, WardynButton, async_add_entities))
