"""Switches from Wardyn's catalogue: a node's parts, a check or a maintenance plan on or off, a device known, hidden or tracked, and
Wardyn's on/off settings. Each change goes to the node that keeps the catalogue, which makes it in Wardyn (within 20 seconds)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import SWITCH


class WardynSwitch(WardynEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        t = self.thing
        return None if not t or t.state is None else bool(t.state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_request("*", "set", key=self.thing.data["key"], value=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_request("*", "set", key=self.thing.data["key"], value=False)


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, SWITCH, WardynSwitch, async_add_entities))
