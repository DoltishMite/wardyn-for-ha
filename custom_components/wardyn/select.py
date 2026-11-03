"""Selects from Wardyn's catalogue: a node's group, its speed test length, Wardyn's thresholds, issue levels, speed test server and
the like. The options are Wardyn's own words."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import SELECT


class WardynSelect(WardynEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        t = self.thing
        return [str(o) for o in (t.meta.get("o") or [])] if t else []

    @property
    def current_option(self) -> str | None:
        t = self.thing
        return t.state if t and t.state in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_request("*", "set", key=self.thing.data["key"], value=option)


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, SELECT, WardynSelect, async_add_entities))
