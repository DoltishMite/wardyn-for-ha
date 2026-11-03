"""Sensors: counts (issues, nodes connected, updates waiting, threats, failing checks, outages, devices online), a network's
internet latency, and a node's last check-in."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import CAT, COUNT, LATENCY, SENSOR, TIMESTAMP


class WardynSensor(WardynEntity, SensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        kind = self.thing.kind
        if kind == COUNT:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif kind == TIMESTAMP:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif kind == LATENCY:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
        elif kind == CAT:   # Wardyn's catalogue: its unit, device class and state class as given
            m = self.thing.meta
            try:
                self._attr_device_class = SensorDeviceClass(m["dc"]) if m.get("dc") else None
            except ValueError:
                pass
            self._attr_native_unit_of_measurement = m.get("u") or None
            self._attr_state_class = SensorStateClass.MEASUREMENT if m.get("sc") == "measurement" else None

    @property
    def native_value(self):
        t = self.thing
        return t.state if t else None


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, SENSOR, WardynSensor, async_add_entities))
