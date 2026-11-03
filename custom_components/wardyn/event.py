"""Alerts: one event entity on the Wardyn device, for automations (trigger on its state, with event_type in the attributes): a node
stopped reporting or came back, a network's internet went down or came back, a new device joined, a threat was found, a check
started failing. Each also goes on the bus as wardyn_alert { type, ... }."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback

from . import WardynConfigEntry
from .entity import WardynEntity, follow
from .core.model import EVENT
from .core.parse import ALERT_TYPES


class WardynAlerts(WardynEntity, EventEntity):
    _attr_event_types = ALERT_TYPES

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.alert_listeners.append(self._alert)
        self.async_on_remove(lambda: self.coordinator.alert_listeners.remove(self._alert))

    @callback
    def _alert(self, kind: str, details: dict) -> None:
        self._trigger_event(kind, details)
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, EVENT, WardynAlerts, async_add_entities))
