"""Constants for Wardyn for HA."""
from __future__ import annotations

import logging

DOMAIN = "wardyn"
LOGGER = logging.getLogger(__package__)
VERSION = "0.3.0"   # keep in step with manifest.json

HUB = "https://launcher.hedgepig.uk"
SYNC_URL = f"{HUB}/api/sync"
LIVE_URL = "wss://launcher.hedgepig.uk/api/live"
PANEL_URL = "https://wardyn.hedgepig.uk/?hp=ha"
# The server lets a Home Assistant client read and save an existing copy (GET/PUT /api/sync) and watch it (the live link) when it
# sends no Origin and names itself here (the same rule as Appline for HA's).
HEADERS = {"X-Appline-Client": f"ha/{VERSION}"}

CONF_CODE = "code"     # Wardyn's Home Assistant link code (a secret: never log it)
CONF_PANEL = "panel"   # Wardyn in the sidebar (options; on unless false)
PANEL_PATH = "wardyn"
