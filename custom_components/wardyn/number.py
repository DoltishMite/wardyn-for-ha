"""Numbers from Wardyn's catalogue: how often a node scans or tests, your package's speeds, loss levels, uptime check intervals. Wardyn
keeps each within its own limits."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import NUMBER


class WardynNumber(WardynEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        m = self.thing.meta
        self._attr_native_min_value = float(m.get("min", 0))
        self._attr_native_max_value = float(m.get("max", 100))
        self._attr_native_step = float(m.get("step", 1))
        self._attr_native_unit_of_measurement = m.get("u") or None

    @property
    def native_value(self) -> float | None:
        t = self.thing
        return float(t.state) if t and isinstance(t.state, (int, float)) and not isinstance(t.state, bool) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_request("*", "set", key=self.thing.data["key"], value=value)


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, NUMBER, WardynNumber, async_add_entities))
