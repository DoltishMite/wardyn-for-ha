"""Diagnostics: counts and link state only. Never the code, ids, names or anything from Wardyn's data."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import WardynConfigEntry
from .const import CONF_CODE

REDACT = {CONF_CODE, "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WardynConfigEntry) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data
    doc = c.doc[1] if c.doc else {}
    return {
        "entry": async_redact_data(entry.as_dict(), REDACT),
        "live": c.live,
        "last_update_success": c.last_update_success,
        "controls": doc.get("controls") if isinstance(doc, dict) else None,
        "devices": len(data.devices) if data else 0,
        "entities": {p: sum(1 for t in data.things.values() if t.platform == p) for p in ("sensor", "binary_sensor", "button", "event")} if data else {},
    }
