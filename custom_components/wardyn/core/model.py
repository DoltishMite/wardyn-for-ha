"""What the parser hands to Home Assistant: devices and the things (entities) on them. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SENSOR, BINARY, BUTTON, EVENT = "sensor", "binary_sensor", "button", "event"
COUNT, TIMESTAMP, LATENCY = "count", "timestamp", "latency"          # SENSOR kinds (LATENCY: milliseconds)
PROBLEM, PRESENCE, CONNECTIVITY = "problem", "presence", "connectivity"   # BINARY kinds
PRESS, ALERTS = "press", "alerts"                                    # BUTTON, EVENT


@dataclass
class Device:
    key: str                       # unique within the config entry, e.g. "wardyn", "node.<id>", "net.<router>"
    name: str
    model: str
    via: str | None = None         # the device it hangs off (Wardyn's own)


@dataclass
class Thing:
    key: str                       # unique within the config entry and stable: built from Wardyn's ids, never names
    device: str                    # Device.key
    platform: str
    kind: str
    translation_key: str
    state: Any
    placeholders: dict[str, str] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    icon: str | None = None
    data: Any = None               # BUTTON: the request it makes { node, kind }
    enabled: bool = True           # False: the entity starts disabled (the user can switch it on)


@dataclass
class Parsed:
    devices: dict[str, Device] = field(default_factory=dict)
    things: dict[str, Thing] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)   # what alerts compare (parse.alerts)

    def add_device(self, d: Device) -> None:
        self.devices[d.key] = d

    def add(self, t: Thing) -> None:
        self.things[t.key] = t
