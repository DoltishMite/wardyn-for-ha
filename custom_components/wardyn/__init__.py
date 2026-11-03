"""Wardyn for HA: Wardyn (wardyn.hedgepig.uk, the network monitor) in Home Assistant.

Set up with Wardyn's own Home Assistant link code (Wardyn → Settings → Home Assistant), separate from your sync code and from Appline's
link, so it can be given to a Home Assistant on its own. Each Wardyn Agent writes its state into the sealed link copy; this turns it
into a device per network and per node with their sensors, tracked devices home or away, alerts (an event entity, and wardyn_alert on
the bus) and, when Wardyn allows it, buttons that ask a node to update, restart, install updates or scan. Wardyn is also offered as a
sidebar panel.
"""
from __future__ import annotations

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_PANEL, DOMAIN, LOGGER, PANEL_PATH, PANEL_URL
from .coordinator import WardynCoordinator
from .entity import device_identifier

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT]
type WardynConfigEntry = ConfigEntry[WardynCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WardynConfigEntry) -> bool:
    coordinator = WardynCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_add_listener(lambda: _tidy(hass, entry)))
    _tidy(hass, entry)
    coordinator.start_tick()
    entry.async_create_background_task(hass, coordinator.run_live(), f"{DOMAIN} live link")
    _panel(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_changed(hass: HomeAssistant, entry: WardynConfigEntry) -> None:
    _panel(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: WardynConfigEntry) -> bool:
    if entry.runtime_data.panel:
        frontend.async_remove_panel(hass, entry.runtime_data.panel, warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _panel(hass: HomeAssistant, entry: WardynConfigEntry) -> None:
    """Wardyn in the sidebar (Configure; on unless switched off)."""
    c = entry.runtime_data
    want = entry.options.get(CONF_PANEL, True)
    if c.panel and not want:
        frontend.async_remove_panel(hass, c.panel, warn_if_unknown=False)
        c.panel = None
    elif want and not c.panel:
        try:
            frontend.async_register_built_in_panel(hass, "iframe", sidebar_title="Wardyn", sidebar_icon="mdi:shield-check",
                                                   frontend_url_path=PANEL_PATH, config={"url": PANEL_URL}, require_admin=False)
            c.panel = PANEL_PATH
        except ValueError:
            LOGGER.warning("Wardyn is already in the sidebar (from another entry, or Appline for HA's Sidebar apps)")


@callback
def _tidy(hass: HomeAssistant, entry: WardynConfigEntry) -> None:
    """Remove entities and devices that are gone from Wardyn; keep device names in step with renames."""
    coordinator = entry.runtime_data
    data = coordinator.data
    if not coordinator.last_update_success or data is None:
        return   # never tidy from a failed update: that would wipe everything while the server is away
    prefix = f"{entry.entry_id}_"
    ents = er.async_get(hass)
    for e in er.async_entries_for_config_entry(ents, entry.entry_id):
        if e.unique_id.startswith(prefix) and e.unique_id[len(prefix):] not in data.things:
            ents.async_remove(e.entity_id)
    devs = dr.async_get(hass)
    want = {device_identifier(entry.entry_id, k): d for k, d in data.devices.items()}
    for d in dr.async_entries_for_config_entry(devs, entry.entry_id):
        ident = next((i for i in d.identifiers if i[0] == DOMAIN), None)
        if ident not in want:
            devs.async_update_device(d.id, remove_config_entry_id=entry.entry_id)
        elif d.name != want[ident].name:
            devs.async_update_device(d.id, name=want[ident].name)
    # Home Assistant keeps an entity's name once worked out: a tracked device renamed in Wardyn needs a reload to show (rare)
    names = {k: t.placeholders for k, t in data.things.items() if t.placeholders}
    if any(k in names and names[k] != v for k, v in coordinator.names.items()):
        hass.config_entries.async_schedule_reload(entry.entry_id)
    coordinator.names = names
