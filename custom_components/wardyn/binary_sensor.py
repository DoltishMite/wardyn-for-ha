"""Binary sensors: connected (a network's internet, a node checking in), a problem (anything serious; a restart needed), and a
tracked device at home."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import BINARY, CONNECTIVITY, PRESENCE, PROBLEM

CLASSES = {PROBLEM: BinarySensorDeviceClass.PROBLEM, PRESENCE: BinarySensorDeviceClass.PRESENCE, CONNECTIVITY: BinarySensorDeviceClass.CONNECTIVITY}


class WardynBinarySensor(WardynEntity, BinarySensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_device_class = CLASSES.get(self.thing.kind)

    @property
    def is_on(self) -> bool | None:
        t = self.thing
        return None if not t or t.state is None else bool(t.state)


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, BINARY, WardynBinarySensor, async_add_entities))
